#!/usr/bin/env python3
"""Physical unit-stride vector memory oracle; variable A/D stalls, faults/restart and boundary stop."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
BASE=0x80000000;N=8192;MASK=(1<<128)-1
MODEL=r'''
wire io_memoryStatus_valid,io_memoryStatus_bits_fault,io_memoryStatus_bits_interrupted;
wire [5:0] io_memoryStatus_bits_cause;wire [63:0] io_memoryStatus_bits_address;wire [7:0] io_memoryStatus_bits_element;
wire io_tl_a_valid;wire [2:0] io_tl_a_bits_opcode,io_tl_a_bits_param,io_tl_a_bits_size;wire [3:0] io_tl_a_bits_source;
wire [63:0] io_tl_a_bits_address,io_tl_a_bits_data;wire [7:0] io_tl_a_bits_mask;wire io_tl_a_bits_corrupt;
wire io_tl_a_ready;reg io_tl_d_valid=0;wire io_tl_d_ready;reg [2:0] io_tl_d_bits_opcode=0,io_tl_d_bits_param=0,io_tl_d_bits_size=0;
reg [3:0] io_tl_d_bits_source=0;reg io_tl_d_bits_sink=0,io_tl_d_bits_denied=0,io_tl_d_bits_corrupt=0;reg [63:0] io_tl_d_bits_data=0;
reg [7:0] mem[0:8191];integer caseid=-1,latency=0,waits=0,requests=0,responses=0,memCommands=0,completionStall=4;
reg pending=0;reg [63:0] pa,pdata;reg [7:0] pmask;reg [2:0] psz,pop;integer perror;
reg [63:0] faultAddress=64'hffffffffffffffff;integer faultKind=0;
reg [63:0] commandStride=0;integer chunkReads=0;
`ifndef MAPPED
always @(posedge clock)if(!reset && dut.engine.io_context_valid && dut.engine.io_context_ready && !dut.engine.io_context_bits_write)chunkReads=chunkReads+1;
`endif
integer j,beat,stopIndex;reg [63:0] observed;reg [63:0] expectedWord;
assign io_tl_a_ready=!pending && !io_tl_d_valid && cycles%3!=1;
always @(posedge clock)if(!reset)begin
 if(io_tl_a_valid && io_tl_a_ready)begin
  if(pending || io_tl_a_bits_source!==0 || io_tl_a_bits_param!==0 || io_tl_a_bits_corrupt || io_tl_a_bits_size>3)
   $fatal(1,"invalid A");
  if(io_tl_a_bits_address<64'h80000000 || io_tl_a_bits_address>=64'h80002000)$fatal(1,"test memory out of range");
  pa<=io_tl_a_bits_address;pdata<=io_tl_a_bits_data;pmask<=io_tl_a_bits_mask;psz<=io_tl_a_bits_size;pop<=io_tl_a_bits_opcode;
  perror<=(io_tl_a_bits_address==faultAddress)?faultKind:0;pending<=1;waits<=latency;requests=requests+1;
  $display("BUS %0d %h %0d %h %h",caseid,io_tl_a_bits_address,io_tl_a_bits_opcode,io_tl_a_bits_mask,io_tl_a_bits_data);
 end
 if(pending && !io_tl_d_valid)begin
  if(waits>0)waits<=waits-1;
  else begin
   io_tl_d_valid<=1;io_tl_d_bits_opcode<=pop==4?1:0;io_tl_d_bits_size<=psz;io_tl_d_bits_source<=perror==3?3:0;
   io_tl_d_bits_denied<=perror==1;io_tl_d_bits_corrupt<=perror==2;
   if(perror==4)io_tl_d_bits_opcode<=5;
   beat=(pa-64'h80000000)&~7;
   for(j=0;j<8;j=j+1)io_tl_d_bits_data[8*j+:8]<=mem[beat+j];
  end
 end
 if(io_tl_d_valid && io_tl_d_ready)begin
  if(pop!=4 && perror==0)begin
   beat=(pa-64'h80000000)&~7;
   for(j=0;j<8;j=j+1)if(pmask[j])mem[beat+j]<=pdata[8*j+:8];
  end
  io_tl_d_valid<=0;pending<=0;responses=responses+1;
 end
 if(io_memoryStatus_valid && !io_core_completion_valid)$fatal(1,"unowned memory status");
end

task memory(input [31:0] inst,input [63:0] base,input [79:0] token,input integer bad,fault,cause,element,expectedStart,expectedRequests,
 input [63:0] tval);
integer beginCycle,beginRequests,beginReads,k;reg [159:0] held;begin
 io_core_command_bits_instruction=inst;io_core_command_bits_scalar=base;io_core_command_bits_scalar2=commandStride;io_core_command_bits_token=token;
 io_core_command_valid=1;beginCycle=cycles;beginRequests=requests;beginReads=chunkReads;
 #1;if(!io_core_command_ready)$fatal(1,"memory not admitted");tick();io_core_command_valid=0;
 while(!io_core_completion_valid)begin tick();if(io_core_context_ready)$fatal(1,"context arbitration");end
 if(!io_memoryStatus_valid || io_core_completion_bits_illegal!==bad || io_core_completion_bits_token!==token ||
    io_core_completion_bits_instruction!==inst || io_core_completion_bits_writesScalar || io_core_completion_bits_scalar!==0 ||
    io_memoryStatus_bits_fault!==fault || io_memoryStatus_bits_interrupted || io_memoryStatus_bits_cause!==cause ||
    io_memoryStatus_bits_element!==element || io_memoryStatus_bits_address!==tval || io_core_vstart!==expectedStart)
  $fatal(1,"memory status case=%0d fault=%b cause=%d element=%d vstart=%d illegal=%b",caseid,io_memoryStatus_bits_fault,
    io_memoryStatus_bits_cause,io_memoryStatus_bits_element,io_core_vstart,io_core_completion_bits_illegal);
 if(requests-beginRequests!=expectedRequests)$fatal(1,"wrong request count case=%d got=%d expected=%d",caseid,requests-beginRequests,expectedRequests);
 held={io_memoryStatus_bits_fault,io_memoryStatus_bits_interrupted,io_memoryStatus_bits_cause,io_memoryStatus_bits_address,io_memoryStatus_bits_element,io_core_completion_bits_token};
 repeat(completionStall)begin tick();if(!io_core_completion_valid || {io_memoryStatus_bits_fault,io_memoryStatus_bits_interrupted,io_memoryStatus_bits_cause,io_memoryStatus_bits_address,io_memoryStatus_bits_element,io_core_completion_bits_token}!==held)$fatal(1,"completion unstable");end
 io_core_completion_ready=1;tick();io_core_completion_ready=0;memCommands=memCommands+1;
 $display("MEM %0d %0d %0d",caseid,cycles-beginCycle,requests-beginRequests);
 $display("READ %0d %0d",caseid,chunkReads-beginReads);
end endtask

task stopMemory(input [31:0] inst,input [63:0] base,input integer delayCycles,vl,expectFault);
integer beginRequests;begin
 io_core_command_bits_instruction=inst;io_core_command_bits_scalar=base;io_core_command_bits_scalar2=commandStride;io_core_command_bits_token=caseid;
 io_core_command_valid=1;beginRequests=requests;#1;if(!io_core_command_ready)$fatal(1,"stop start blocked");tick();io_core_command_valid=0;
 repeat(delayCycles)tick();io_core_flush=1;tick();io_core_flush=0;
 while(!io_core_completion_valid)tick();
 if(!io_memoryStatus_valid || io_memoryStatus_bits_fault!==expectFault || io_core_completion_bits_token!==caseid || io_core_completion_bits_illegal)$fatal(1,"stop lost completion/fault");
 if(expectFault)begin
  if(io_memoryStatus_bits_cause!==5 || io_memoryStatus_bits_element!==0 || io_core_vstart!==0)$fatal(1,"stop swallowed fault");stopIndex=0;
 end else if(io_memoryStatus_bits_interrupted)begin
  stopIndex=io_memoryStatus_bits_element;if(io_core_vstart!==stopIndex || stopIndex>=vl)$fatal(1,"stop restart index");
 end else begin stopIndex=vl;if(io_core_vstart!==0)$fatal(1,"completed stop vstart");end
 repeat(3)begin tick();if(!io_core_completion_valid)$fatal(1,"stop reply dropped");end
 io_core_completion_ready=1;tick();io_core_completion_ready=0;
 $display("STOP %0d %0d %0d",caseid,stopIndex,requests-beginRequests);
end endtask
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--top',choices=['LishiVpuMemory','LishiVpuMemory16'],default='LishiVpuMemory');p.add_argument('--mapped',action='store_true');args=p.parse_args();assert not args.mapped or args.smoke
 OUT.mkdir(parents=True,exist_ok=True);rng=random.Random(0xa10);regs=[rng.getrandbits(128) for _ in range(32)]
 mem=bytearray((i*13+7)&255 for i in range(N));typ=0;vl=0;start=0;cases=[];expectedBus={};stops=[]
 h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;')
 h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','4000000').replace('io_','io_core_')
 h=h.replace('integer cycles=0,cmds=0,reads=0;','')
 h=h.replace('module tb;','module tb;\ninteger cycles=0,cmds=0,reads=0;')
 h=h.replace('`TOP dut(.*);',MODEL+'\n'+args.top+' dut(.*);')
 h=h.replace('saved=io_core_completion_bits_instruction;', 'if(io_memoryStatus_valid)$fatal(1,"memory status on arithmetic/CSR");saved=io_core_completion_bits_instruction;')
 h=h.replace('initial begin\ntick();','initial begin\nfor(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;\ntick();')
 lines=[h]
 def ctx(r,write=False,expressions=None):
  for k in range(2):
   val=(regs[r]>>(64*k))&((1<<64)-1);exp=f"64'h{val:x}" if expressions is None else expressions[k]
   lines.append(f"ctx({2*r+k},1'b{int(write)},64'h{val:x},{exp});")
 def config(t,length):
  nonlocal typ,vl,start
  typ=t;vl=length;start=0
  inst=(t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57
  lines.append(f"command(32'h{inst:x},0,0,{vl},0,0,{vl},1,0,{vl},64'h{typ:x});")
 def setstart(x):
  nonlocal start
  old=start;start=x;lines.append(f"command(32'h00809073,{x},0,0,0,0,{old},0,0,{vl},64'h{typ:x});")
 def mask(value):regs[0]=value;ctx(0,True)
 def instruction(ew,write,vr=8,masked=False):
  width=[0,5,6,7][ew];return (int(not masked)<<25)|(1<<15)|(width<<12)|(vr<<7)|(0x27 if write else 7)
 def run(ew,write,base,vr=8,masked=False,faultIndex=None,kind=0,illegal=False,reserved=0):
  nonlocal start
  initialStart=start;ident=len(cases);inst=instruction(ew,write,vr,masked)|reserved;width=1<<ew
  emul=((typ&7) if typ&7<4 else (typ&7)-8)+ew-((typ>>3)&7);group=1 if illegal else 1<<max(0,emul)
  transfers=[];failure=None;active=0
  if not illegal:
   for e in range(start,vl):
    if masked and not(regs[0]>>e&1):continue
    addr=(base+e*width)&((1<<64)-1)
    if addr&(width-1):failure=(e,6 if write else 4,addr);break
    if addr>>28!=BASE>>28:failure=(e,7 if write else 5,addr);break
    if faultIndex is not None and e==faultIndex:failure=(e,7 if write else 5,addr);transfers.append(addr);break
    transfers.append(addr);active+=1;byte=e*width;reg=vr+byte//16;shift=(byte%16)*8;m=(1<<(width*8))-1
    if write:mem[addr-BASE:addr-BASE+width]=((regs[reg]>>shift)&m).to_bytes(width,'little')
    else:
     value=int.from_bytes(mem[addr-BASE:addr-BASE+width],'little');regs[reg]=(regs[reg]&~(m<<shift))|(value<<shift)
  if faultIndex is not None:lines.append(f"faultAddress=64'h{base+faultIndex*width:x};faultKind={kind};")
  else:lines.append("faultAddress=64'hffffffffffffffff;faultKind=0;")
  cause=failure[1] if failure else 0;element=failure[0] if failure else 0;tval=failure[2] if failure else 0
  nextStart=start if illegal else element if failure else 0
  expectedBus[ident]=transfers;lines.append(f'caseid={ident};')
  lines.append(f"memory(32'h{inst:x},64'h{base:x},80'h{(0xabcd<<64)|ident:x},{int(illegal)},{int(failure is not None)},{cause},{element},{nextStart},{len(transfers)},64'h{tval:x});")
  start=nextStart
  for r in range(vr,vr+group):ctx(r)
  if write and not illegal:
   for addr in transfers:
    if failure and addr==failure[2]:continue
    for k in range(width):lines.append(f"if(mem[{addr-BASE+k}]!==8'h{mem[addr-BASE+k]:x})$fatal(1,\"store data\");")
  cases.append(dict(masked=masked,initial_vstart=initialStart,id=ident,eew=8<<ew,write=write,vl=vl,vtype=typ,active_successes=active,fault=failure is not None,illegal=illegal))
 for r in range(32):ctx(r,True)
 types=[(s<<3)|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<=3 or s<=m-5]
 combinations=[(t,e) for t in types for e in range(4) if -3<=((t&7) if t&7<4 else (t&7)-8)+e-((t>>3)&7)<=3]
 if args.smoke:combinations=[(0,0),(8,1),(16,2),(24,3),(0,3),(24,0)]
 for i,(t,ew) in enumerate(combinations):
  lm=(t&7) if t&7<4 else (t&7)-8;maximum=(16>>((t>>3)&7))*(1<<lm) if lm>=0 else (16>>((t>>3)&7))//(1<<-lm)
  config(t,maximum);mask(sum(1<<e for e in range(128) if e%3!=1));lines.append(f'latency={i%3*3};')
  if maximum>2 and i%2:setstart(1)
  run(ew,False,BASE+128,masked=bool(i%2));run(ew,True,BASE+2048,masked=bool(i%2))
 # Empty, masked-off misaligned access, and restart beyond vl must not touch memory.
 config(24,2);mask(0);run(3,False,BASE+1,masked=True)
 setstart(7);run(3,True,BASE+1)
 config(0,0);run(0,False,BASE)
 # Access faults after a visible prefix; retry same instruction from architectural vstart.
 for ew in range(4):
  config(ew<<3,min(4,16>>ew));mask((1<<128)-1)
  for write in [False,True]:
   setstart(0);run(ew,write,BASE+512,faultIndex=1,kind=1+(ew%4));run(ew,write,BASE+512)
 # Local alignment and window faults; no bus request on the failing element.
 for ew in [1,2,3]:
  config(ew<<3,2);run(ew,False,BASE+1);setstart(0);run(ew,True,BASE+1)
 config(0,2);run(0,False,BASE-1);setstart(0);run(0,True,BASE-1)
 # Unsupported encodings and EMUL>8 are illegal with no accesses/state changes.
 config(3,1);run(3,False,BASE,illegal=True)
 config(0,4);setstart(2);run(0,False,BASE,vr=0,masked=True,illegal=True)
 # Encoding rejects and v0 source/destination corner cases.
 config(0,4);setstart(2)
 for bits in [1<<29,1<<28,1<<21,1<<20,1<<12]:run(0,False,BASE,illegal=True,reserved=bits)
 config(1,4);run(0,False,BASE,vr=9,illegal=True)
 config(0,16);run(0,False,BASE+768,vr=0);run(0,True,BASE+1024,vr=0,masked=True,illegal=True)
 # Mixed-EEW mask/data aliases are checked before empty/inactive/restart exits.
 for ew in range(4):
  for length,restart,predicate in [(0,0,0),(2,0,0),(2,3,(1<<128)-1)]:
   config(ew<<3,length);mask(predicate);setstart(restart)
   for write in [False,True]:run(ew,write,BASE+1024,vr=0,masked=True,illegal=True)
 # v0 remains a legal unmasked store source.
 config(0,2);run(0,True,BASE+1024,vr=0)
 config(0,2);setstart(1);run(0,False,0xffffffff)
 # Closed loop: load -> integer add -> store, with a real version-map flip.
 config(16,4);run(2,False,BASE+512)
 regs[16]=sum(1<<(32*k) for k in range(4));ctx(16,True)
 addinst=(1<<25)|(8<<20)|(16<<15)|(8<<7)|0x57
 lines.append(f"command(32'h{addinst:x},0,0,0,0,0,0,0,3,{vl},64'h{typ:x});")
 regs[8]=sum((((regs[8]>>(32*k))&0xffffffff)+1 & 0xffffffff)<<(32*k) for k in range(4));ctx(8)
 run(2,True,BASE+4096)
 # Closed loop through FP, preserving seeded FCSR and fixed-point flags.
 lines.append(f"command(32'h00109073,27,0,0,0,0,0,0,0,{vl},64'h{typ:x});")
 lines.append(f"command(32'h00f09073,7,0,0,0,0,0,0,0,{vl},64'h{typ:x});")
 for k in range(4):
  mem[4608+4*k:4612+4*k]=(0x3f800000).to_bytes(4,'little')
 for k in range(16):lines.append(f"mem[{4608+k}]=8'h{mem[4608+k]:x};")
 regs[16]=sum(0x3f800000<<(32*k) for k in range(4));ctx(16,True)
 run(2,False,BASE+4608)
 fpinst=(1<<25)|(8<<20)|(16<<15)|(1<<12)|(8<<7)|0x57
 lines.append(f"command(32'h{fpinst:x},0,0,0,0,0,0,0,3,{vl},64'h{typ:x});")
 regs[8]=sum(0x40000000<<(32*k) for k in range(4));ctx(8);run(2,True,BASE+4700)
 lines.append('if(io_core_fflags!==27 || io_core_frm!==0 || io_core_vxrm!==3 || io_core_vxsat!==1)$fatal(1,"memory clobbered CSR flags");')
 # Throughput reference; no completion backpressure, explicit service wait cycles.
 benchmarkCases=[];lines.append('completionStall=0;')
 for ew in ([0,3] if args.smoke else range(4)):
  for delay in ([0,4] if args.smoke else [0,4,16]):
   config((ew<<3)|3,128>>ew);lines.append(f'latency={delay};')
   for write in [False,True]:
    benchmarkCases.append(dict(case=len(cases),service_wait=delay,eew=8<<ew,vl=vl,write=write))
    run(ew,write,BASE+4096 if write else BASE+128)
 lines.append('completionStall=4;')
 # Boundary faults check complete 64-bit address arithmetic without accessing
 # outside normal RAM: low16, low32, full64 wrap, and an arbitrary high word.
 for ew in range(4):
  width=1<<ew;config(ew<<3,min(4,16>>ew));mask((1<<128)-1)
  for label,base in [('carry16',(1<<16)-width),('carry32',(1<<32)-width),
                     ('wrap64',(1<<64)-width),('high_word',(0x12345678<<32)|((1<<32)-width))]:
   for write in [False,True]:
    setstart(1);run(ew,write,base);cases[-1]['address_boundary']=label

 # M36: each registered high-address prefix crosses independently, plus
 # mixed byte patterns where one prefix must stop propagating the carry.
 for ew in range(4):
  width=1<<ew;config(ew<<3,min(4,16>>ew));mask((1<<128)-1)
  for label,upper in [('carry40',0xff),('carry48',0xffff),('carry56',0xffffff)]:
   for write in [False,True]:
    setstart(1);run(ew,write,(upper<<32)|((1<<32)-width));cases[-1]['address_boundary']=label

 # Boundary stop sweep. Reinitialize RAM/destination between cases for dynamic-prefix checks.
 delays=[0,30,120,1000] if args.smoke else list(range(0,97,3))+[120,200,400,600,1000]
 initialRegs=regs.copy()
 for write in [False,True]:
  for delay in delays:
   config(0,16);mask((1<<128)-1);regs[8]=initialRegs[8];ctx(8,True)
   ident=len(cases)+len(stops);base=BASE+1024;inst=instruction(0,write)
   lines.append('for(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;faultAddress=64\'hffffffffffffffff;faultKind=0;latency=5;')
   lines.append(f'caseid={ident};stopMemory(32\'h{inst:x},64\'h{base:x},{delay},16,0);')
   if write:
    for e in range(16):
     old=((1024+e)*13+7)&255;new=(regs[8]>>(e*8))&255
     lines.append(f"if(mem[{1024+e}]!==(stopIndex>{e}?8'h{new:x}:8'h{old:x}))$fatal(1,\"stopped store prefix\");")
    ctx(8)
   else:
    exp=[]
    for k in range(2):
     parts=[]
     for e in reversed(range(k*8,k*8+8)):
      old=(regs[8]>>(e*8))&255;new=((1024+e)*13+7)&255
      parts.append(f"(stopIndex>{e}?8'h{new:x}:8'h{old:x})")
     exp.append('{'+','.join(parts)+'}')
    ctx(8,expressions=exp)
   stops.append(dict(id=ident,write=write,delay=delay))
 # Retain an issued load error even if a stop arrives while waiting for D.
 config(0,16);ident=len(cases)+len(stops);lines.append(f"caseid={ident};latency=50;faultAddress=64'h{BASE+1024:x};faultKind=1;")
 lines.append(f"stopMemory(32'h{instruction(0,False):x},64'h{BASE+1024:x},30,16,1);");stops.append(dict(id=ident,error_stop=True))
 lines.append('$display("PASS vector-memory commands=%0d requests=%0d responses=%0d cycles=%0d",memCommands,requests,responses,cycles);if(requests!=responses)$fatal(1,"undrained bus");$finish;end endmodule')
 name=('vector-memory16' if args.top.endswith('16') else 'vector-memory')+('-mapped' if args.mapped else '-smoke' if args.smoke else '-rtl');tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
 rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl]
 assertionTops=[]
 if not args.mapped:
  for module,instance in [('VectorMemoryEngine','engine'),('RamVectorFpMemory16' if args.top.endswith('16') else 'RamVectorFpMemory','vpu')]:
   source=ROOT/f'build/rtl/verification/assert/{module}_Verification_Assert.sv'
   monitor=OUT/(name+'-'+module+'-assert.sv')
   monitor.write_text(source.read_text().replace(module+'.','tb.dut.'+instance+'.'))
   files.append(monitor);assertionTops+=['-s',module+'_Verification_Assert']
 if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv']
 with (OUT/(name+'.compile.log')).open('w') as log:
  subprocess.run([str(BIN/'iverilog'),'-g2012',*(['-DMAPPED'] if args.mapped else []),'-s','tb',*(['-s','glbl'] if args.mapped else []),*assertionTops,'-o',str(exe),*map(str,files)],stdout=log,stderr=log,check=True)
 run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 actual={};metrics=[];contextReads={}
 for line in run.stdout.splitlines():
  fields=line.split()
  if line.startswith('BUS '):actual.setdefault(int(fields[1]),[]).append(int(fields[2],16))
  elif line.startswith('READ '):contextReads[int(fields[1])]=int(fields[2])
  elif line.startswith('MEM '):metrics.append(dict(case=int(fields[1]),cycles=int(fields[2]),requests=int(fields[3])))
 for ident,expected in expectedBus.items():assert actual.get(ident,[])==expected,(ident,actual.get(ident,[]),expected)
 if not args.mapped:
  for case in benchmarkCases:assert contextReads[case['case']]==(0 if case['eew']==64 and not case['write'] else 16),(case,contextReads[case['case']])
 result=dict(context_reads=contextReads,status='PASS',memory_cases=len(cases),stop_cases=len(stops),eew_emul_combinations=len(combinations),metrics=metrics,case_specs=cases,stop_specs=stops,benchmark_cases=benchmarkCases,
  assertions_enabled=not args.mapped,scope='physical normal RAM; registered memory model; no MMIO/PMP/VM/coherence',
  rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),
  summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS vector-memory')))
 (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k not in ['metrics','case_specs','stop_specs','benchmark_cases','context_reads']})
if __name__=='__main__':main()
