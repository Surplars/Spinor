#!/usr/bin/env python3
"""Actual RAM VPU/TileLink unit-stride segments, field faults/retry and permitted partial-stop prefixes."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
from test_context_memory import MODEL
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/segment-memory';BIN=ROOT/'tools/oss-cad-suite/bin';BASE=0x80000000;N=8192;U64=(1<<64)-1
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['LishiVpuMemory','LishiVpuMemory16'],default='LishiVpuMemory');a=p.parse_args();assert not a.mapped or a.smoke
OUT.mkdir(parents=True,exist_ok=True);rng=random.Random(0x46b55);regs=[rng.getrandbits(128) for _ in range(32)];mem=bytearray((j*13+7)&255 for j in range(N));typ=vl=start=0;cases=[];stops=[];expectedBus={};stopModels={};encodings=set()
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;').replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','5000000').replace('io_','io_core_')
h=h.replace('integer cycles=0,cmds=0,reads=0;','').replace('module tb;','module tb;\ninteger cycles=0,cmds=0,reads=0;').replace('`TOP dut(.*);',MODEL+'\n'+a.top+' dut(.*);').replace('initial begin\ntick();','initial begin\nfor(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;\ntick();')
dump='''task dumpChunk(input [5:0] addr);begin
 io_core_context_valid=1;io_core_context_bits_write=0;io_core_context_bits_address=addr;io_core_context_bits_data=0;
 #1;if(!io_core_context_ready)$fatal(1,"dump blocked");tick();io_core_context_valid=0;
 while(!io_core_contextResult_valid)tick();$display("RF %0d %0d %016h",caseid,addr,io_core_contextResult_bits);tick();
end endtask
'''
h=h.replace('initial begin\nfor(j=0;j<8192;',dump+'initial begin\nfor(j=0;j<8192;');lines=[h]
def ctx(r,write=False):
 for k in range(2):
  v=regs[r]>>(64*k)&U64;lines.append(f"ctx({2*r+k},1'b{int(write)},64'h{v:x},64'h{v:x});")
def config(t,length):
 global typ,vl,start
 typ=t;vl=length;start=0;inst=(t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57;lines.append(f"command(32'h{inst:x},0,0,{length},80'h460000,0,{length},1,0,{length},64'h{t:x});")
def setstart(n):
 global start
 lines.append(f"command(32'h00809073,{n},0,0,80'h460001,0,{start},0,0,{vl},64'h{typ:x});");start=n
def instruction(ew,n,write,vr=8,masked=False):return ((n-1)<<29)|(int(not masked)<<25)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)
def apply(regs,mem,e,f,addr,w,group,vr,write):
 r=vr+f*group+e*w//16;shift=e*w%16*8;m=(1<<(w*8))-1
 if write:mem[addr-BASE:addr-BASE+w]=((regs[r]>>shift)&m).to_bytes(w,'little')
 else:regs[r]=(regs[r]&~(m<<shift))|(int.from_bytes(mem[addr-BASE:addr-BASE+w],'little')<<shift)
def run(ew,n,write,vr=8,masked=False,base=BASE+1024,illegal=False,bits=0,error=None,kind=0):
 global start
 ident=len(cases);initialStart=start;inst=instruction(ew,n,write,vr,masked)|bits;w=1<<ew;lm=(typ&7) if typ&7<4 else (typ&7)-8;group=1<<max(0,lm+ew-(typ>>3&7));transfers=[];failure=None
 if not illegal:
  for e in range(start,vl):
   if masked and not(regs[0]>>e&1):continue
   for f in range(n):
    addr=(base+(e*n+f)*w)&U64
    if addr&(w-1):failure=(e,6 if write else 4,addr);break
    if addr>>28!=BASE>>28:failure=(e,7 if write else 5,addr);break
    transfers.append(addr)
    if error==(e,f):failure=(e,7 if write else 5,addr);break
    apply(regs,mem,e,f,addr,w,group,vr,write)
   if failure:break
 errorAddr=U64 if error is None else (base+(error[0]*n+error[1])*w)&U64
 lines.append(f"faultAddress=64'h{errorAddr:x};faultKind={kind};latency=2;caseid={ident};")
 e,c,tval=failure or (0,0,0);ns=start if illegal else e if failure else 0
 lines.append(f"memory(32'h{inst:x},64'h{base:x},80'h{(0x46abcd<<48)|ident:x},{int(illegal)},{int(failure is not None)},{c},{e},{ns},{len(transfers)},64'h{tval:x});")
 lines.append(f"if(io_core_vl!==8'd{vl} || io_core_vtype!==64'h{typ:x})$fatal(1,\"segment clobbered configuration\");")
 start=ns
 for r in (range(32) if not a.smoke else sorted({0,16,23,31}|set(range(vr,min(32,vr+n*group))))):ctx(r)
 if write:
  for addr in transfers:
   if failure and addr==failure[2]:continue
   for b in range(w):lines.append(f"if(mem[{addr-BASE+b}]!==8'h{mem[addr-BASE+b]:x})$fatal(1,\"segment store data\");")
 expectedBus[ident]=transfers;cases.append(dict(id=ident,eew=w*8,nfields=n,write=write,vtype=typ,vl=vl,initial_vstart=initialStart,vr=vr,masked=masked,illegal=illegal,fault=failure is not None))
 if not illegal:encodings.add((ew,n,write))
for r in range(32):ctx(r,True)
for n in range(2,9):
 for ew in range(4):
  config(ew<<3,2 if a.smoke else 16//(1<<ew))
  for write in [False,True]:
   if a.smoke:setstart(1)
   run(ew,n,write,vr=32-n if n%2 else 8)
   if not a.smoke:
    regs[0]=0x55555555555555555555555555555555;ctx(0,True);setstart(1);run(ew,n,write,masked=True)
    setstart(vl);run(ew,n,write)
for t,ew,n,vr in [(1,0,4,10),(2,0,2,4),(8,0,8,8),(5,0,8,8),(14,0,8,8),(23,0,8,8)]:
 config(t,1)
 for write in [False,True]:run(ew,n,write,vr)
# Repeat the faulting segment from field zero, preserving already committed fields.
for ew,n in [(0,3),(1,4),(2,2),(3,8)]:
 config(ew<<3,2)
 for write in [False,True]:
  for kind in ([1] if a.smoke else [1,2,3,4]):
   setstart(0);run(ew,n,write,error=(1,n-1),kind=kind);run(ew,n,write)
  if ew:setstart(0);run(ew,n,write,base=BASE+1)
 config(ew<<3,0)
 for write in [False,True]:run(ew,n,write)
for t,ew,n,vr,masked,bits in [(2,0,3,8,False,0),(1,0,8,8,False,0),(1,0,4,9,False,0),(0,0,8,25,False,0),(0,0,2,0,True,0),(0,0,2,8,False,1<<28),(0,0,2,8,False,16<<20)]:
 config(t,0)
 for write in [False,True]:run(ew,n,write,vr,masked,illegal=True,bits=bits)
# Stop can leave a prefix of fields inside the restart segment. Compare against
# the complete set of architecturally permitted prefixes; never infer data from DUT internals.
saved=regs.copy()
for ew,n in [(0,3),(3,2)]:
 for write in [False,True]:
  for delay in ([0,70,150] if a.smoke else range(0,201,10)):
   config(ew<<3,4 if ew==0 else 2)
   regs=saved.copy()
   for r in range(32):ctx(r,True)
   ident=len(cases)+len(stops);w=1<<ew;base=BASE+1024;initialMem=bytearray((j*13+7)&255 for j in range(N));inst=instruction(ew,n,write)
   lines.append(f"for(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;caseid={ident};faultKind=0;faultAddress=64'hffffffffffffffff;latency=5;stopMemory(32'h{inst:x},64'h{base:x},{delay},{vl},0);")
   for chunk in range(64):lines.append(f'dumpChunk({chunk});')
   for b in range(n*vl*w):lines.append(f'$display("BYTE {ident} {1024+b} %02h",mem[{1024+b}]);')
   specs=dict(id=ident,eew=8*w,nfields=n,write=write,delay=delay,vl=vl);stops.append(specs);stopModels[ident]=dict(regs=regs.copy(),mem=initialMem,**specs)
lines.append('$display("PASS segment-memory commands=%0d requests=%0d responses=%0d cycles=%0d",memCommands,requests,responses,cycles);if(requests!=responses)$fatal(1,"undrained bus");$finish;end endmodule')
name=('segment-memory16' if a.top.endswith('16') else 'segment-memory')+('-mapped' if a.mapped else '-smoke' if a.smoke else '-rtl');tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl];assertionTops=[]
if not a.mapped:
 for module,instance in [('VectorMemoryEngine','engine'),('RamVectorFpMemory16' if a.top.endswith('16') else 'RamVectorFpMemory','vpu')]:
  source=ROOT/f'build/rtl/verification/assert/{module}_Verification_Assert.sv';monitor=OUT/(name+'-'+module+'-assert.sv');monitor.write_text(source.read_text().replace(module+'.','tb.dut.'+instance+'.'));files.append(monitor);assertionTops+=['-s',module+'_Verification_Assert']
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv']
with (OUT/(name+'.compile.log')).open('w') as log:subprocess.run([str(BIN/'iverilog'),'-g2012',*(['-DMAPPED'] if a.mapped else []),'-s','tb',*(['-s','glbl'] if a.mapped else []),*assertionTops,'-o',str(OUT/name),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(BIN/'vvp'),str(OUT/name)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
actual={};metrics=[];actualRF={};actualMem={};stopResults={}
for line in r.stdout.splitlines():
 f=line.split()
 if line.startswith('BUS '):actual.setdefault(int(f[1]),[]).append(int(f[2],16))
 elif line.startswith('MEM '):metrics.append(dict(case=int(f[1]),cycles=int(f[2]),requests=int(f[3])))
 elif line.startswith('RF '):actualRF.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif line.startswith('BYTE '):actualMem.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif line.startswith('STOP '):stopResults[int(f[1])]=tuple(map(int,f[2:]))
for ident,want in expectedBus.items():assert actual.get(ident,[])==want,(ident,actual.get(ident,[]),want)
for ident,m in stopModels.items():
 end,count=stopResults[ident];n=m['nfields'];w=m['eew']//8;got=actual.get(ident,[]);assert len(got)==count
 seq=[(e,f,BASE+1024+(e*n+f)*w) for e in range(m['vl']) for f in range(n)];assert got==[x[2] for x in seq[:count]],ident
 candidates=[]
 for fields in ([0] if end==m['vl'] else range(n)):
  completed=end*n+fields
  if m['write'] and count!=completed or not m['write'] and not(completed<=count<=completed+1):continue
  rf=m['regs'].copy();memory=m['mem'].copy()
  for e,f,addr in seq[:completed]:apply(rf,memory,e,f,addr,w,1,8,m['write'])
  chunks={2*r+k:rf[r]>>(64*k)&U64 for r in range(32) for k in range(2)};bytesWant={1024+b:memory[1024+b] for b in range(n*m['vl']*w)}
  candidates.append(actualRF[ident]==chunks and actualMem[ident]==bytesWant)
 assert any(candidates),(ident,end,count,'invalid field prefix')
assert len(encodings)==56
inputs=[Path(__file__).resolve(),ROOT/'tests/test_context_memory.py',ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']
d=dict(status='PASS',memory_cases=len(cases),stop_cases=len(stops),encodings=sorted(encodings),metrics=metrics,case_specs=cases,stop_specs=stops,register_check_scope='ALL_32' if not a.smoke else 'DATA_GROUPS_V0_AND_GUARDS_16_23_31; STOPS_ALL_32',assertions_enabled=not a.mapped,scope='ACTUAL_RAM_CORE_AND_TILELINK; UNIT_STRIDE_SEGMENTS; PARTIAL_FIELD_FAULT_RETRY_AND_STOPS; NO_CPU_OR_VM',rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS segment-memory')))
(OUT/(name+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
