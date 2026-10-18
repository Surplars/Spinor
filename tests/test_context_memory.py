#!/usr/bin/env python3
"""Physical whole-register/mask memory oracle; variable A/D stalls, faults/restart and boundary stop."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/context-memory';BIN=ROOT/'tools/oss-cad-suite/bin'
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
 def config(t,length,invalid=False):
  nonlocal typ,vl,start
  typ=(1<<63) if invalid else t;vl=0 if invalid else length;start=0
  inst=(t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57
  lines.append(f"command(32'h{inst:x},0,0,{length},0,0,{vl},1,0,{vl},64'h{typ:x});")
 def setstart(x):
  nonlocal start
  old=start;start=x;lines.append(f"command(32'h00809073,{x},0,0,0,0,{old},0,0,{vl},64'h{typ:x});")
 def mask(value):regs[0]=value;ctx(0,True)
 def instruction(mode,ew,nregs,write,vr=8,vm=True):
  return ((nregs-1)<<29)|(int(vm)<<25)|((8 if mode=='whole' else 11)<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)
 def run(mode,ew=0,nregs=1,write=False,base=BASE+1024,vr=8,vm=True,illegal=False,bits=0,faultIndex=None,kind=0):
  nonlocal start
  ident=len(cases);initialStart=start;inst=instruction(mode,ew,nregs,write,vr,vm)|bits;width=1<<ew if mode=='whole' else 1;evl=nregs*16//width if mode=='whole' else (vl+7)//8
  transfers=[];failure=None;active=0
  if not illegal:
   for e in range(start,evl):
    addr=(base+e*width)&((1<<64)-1)
    if addr&(width-1):failure=(e,6 if write else 4,addr);break
    if addr>>28!=BASE>>28:failure=(e,7 if write else 5,addr);break
    transfers.append(addr)
    if faultIndex is not None and e==faultIndex:failure=(e,7 if write else 5,addr);break
    active+=1;byte=e*width;r=vr+byte//16;shift=byte%16*8;m=(1<<(width*8))-1
    if write:mem[addr-BASE:addr-BASE+width]=((regs[r]>>shift)&m).to_bytes(width,'little')
    else:regs[r]=(regs[r]&~(m<<shift))|(int.from_bytes(mem[addr-BASE:addr-BASE+width],'little')<<shift)
  lines.append(f"faultAddress=64'h{((base+faultIndex*width)&((1<<64)-1)) if faultIndex is not None else (1<<64)-1:x};faultKind={kind};commandStride=64'hdeadbeef;caseid={ident};")
  cause=failure[1] if failure else 0;element=failure[0] if failure else 0;tval=failure[2] if failure else 0
  nextStart=start if illegal else element if failure else 0;expectedBus[ident]=transfers
  lines.append(f"memory(32'h{inst:x},64'h{base:x},80'h{(0xabcd<<64)|ident:x},{int(illegal)},{int(failure is not None)},{cause},{element},{nextStart},{len(transfers)},64'h{tval:x});")
  lines.append(f"if(io_core_vl!==8'd{vl} || io_core_vtype!==64'h{typ:x})$fatal(1,\"memory clobbered vl/vtype\");")
  start=nextStart;group=nregs if mode=='whole' else 1
  checkedRegs=range(32) if not args.smoke else sorted({0,16,23,31}|set(range(vr,min(32,vr+group))))
  for r in checkedRegs:ctx(r)
  if write and not illegal:
   for addr in transfers:
    if failure and addr==failure[2]:continue
    for k in range(width):lines.append(f"if(mem[{addr-BASE+k}]!==8'h{mem[addr-BASE+k]:x})$fatal(1,\"context store data\");")
  cases.append(dict(id=ident,mode=mode,eew=width*8,nregs=nregs,write=write,vl=vl,vtype=typ,evl=evl,initial_vstart=initialStart,illegal=illegal,fault=failure is not None))
 for r in range(32):ctx(r,True)
 forms=[(ew,n,write) for n in [1,2,4,8] for write in [False,True] for ew in ([0] if write else range(4))]
 combinations=forms
 # Full tests check all 32 registers; smoke keeps all 22 encodings under vill.
 for ew,n,write in forms:
  configs=[(32,0,True)] if args.smoke else [(0,0,False),(3,128,False),(24,2,False),(32,0,True)]
  for t,length,invalid in configs:
   config(t,length,invalid)
   if args.smoke:setstart(n*16//(1<<ew)-1)
   run('whole',ew,n,write,vr=24)
   if not args.smoke:
    setstart(min(127,n*16//(1<<ew)-1));run('whole',ew,n,write,vr=24)
   config(32,0,True);setstart(n*16//(1<<ew)-2 if args.smoke else 1);run('whole',ew,n,write,vr=0)
 # Mask EVL boundaries independent of current SEW/LMUL, including v0.
 types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
 for t in ([3,24,5] if args.smoke else types):
  lm=(t&7) if t&7<4 else (t&7)-8;maximum=(16>>(t>>3&7))*(1<<lm) if lm>=0 else (16>>(t>>3&7))//(1<<-lm)
  for length in (sorted({0,1,min(9,maximum),maximum}) if not args.smoke else [maximum]):
   config(t,length)
   for write in [False,True]:
    run('mask',write=write,vr=0)
    if not args.smoke:setstart((vl+7)//8);run('mask',write=write,vr=0)
 # Prefix faults and restart use the existing vstart without reinitializing RF.
 for mode,ew,n in [('mask',0,1),('whole',0,1 if args.smoke else 8),('whole',3,1 if args.smoke else 8)]:
  for write in [False,True]:
   if write and ew:continue
   config(3,9 if args.smoke else 128) if mode=='mask' else config(32,0,True)
   run(mode,ew,n,write,faultIndex=1,kind=1);run(mode,ew,n,write)
   setstart(1);run(mode,ew,n,write,base=BASE-1)
 # Reserved forms and mask vill checks still apply at empty length.
 config(32,0,True);run('mask',illegal=True)
 config(0,0)
 for mode,ew,n,w,vr,vm,bits in [('mask',0,1,False,8,False,0),('mask',1,1,False,8,True,0),('mask',0,2,True,8,True,0),('whole',0,3,False,8,True,0),('whole',0,2,False,9,True,0),('whole',1,1,True,8,True,0),('whole',0,1,False,8,False,0),('whole',0,1,False,8,True,1<<28)]:
  run(mode,ew,n,w,vr=vr,vm=vm,bits=bits,illegal=True)
 # Sparse stop/drain sweep with RF/memory prefix checked from observed vstart.
 initialRegs=regs.copy()
 for mode,ew,n in [('mask',0,1),('whole',0,2),('whole',3,2)]:
  evl=16 if mode=='mask' else n*16//(1<<ew)
  for write in [False,True]:
   if write and ew:continue
   for delay in ([0,60] if args.smoke else range(0,161,8)):
    config(3,128) if mode=='mask' else config(32,0,True)
    for r in range(8,8+n):regs[r]=initialRegs[r];ctx(r,True)
    ident=len(cases)+len(stops);base=BASE+1024;inst=instruction(mode,ew,n,write)
    lines.append("for(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;faultAddress=64'hffffffffffffffff;faultKind=0;latency=5;")
    lines.append(f"caseid={ident};stopMemory(32'h{inst:x},64'h{base:x},{delay},{evl},0);")
    width=1<<ew if mode=='whole' else 1
    if write:
     for b in range(evl*width):
      old=((1024+b)*13+7)&255;value=regs[8+b//16]>>(b%16*8)&255
      lines.append(f"if(mem[{1024+b}]!==(stopIndex>{b//width}?8'h{value:x}:8'h{old:x}))$fatal(1,\"context store prefix\");")
    for r in range(8,8+(n if mode=='whole' else 1)):
     if write:ctx(r)
     else:
      expressions=[]
      for k in range(2):
       parts=[]
       for byte in reversed(range(k*8,k*8+8)):
        b=(r-8)*16+byte;old=regs[r]>>(8*byte)&255;new=((1024+b)*13+7)&255;parts.append(f"(stopIndex>{b//width}?8'h{new:x}:8'h{old:x})")
       expressions.append('{'+','.join(parts)+'}')
      ctx(r,expressions=expressions)
    stops.append(dict(id=ident,mode=mode,eew=width*8,nregs=n,write=write,delay=delay))
 benchmarkCases=[]
 lines.append('$display("PASS context-memory commands=%0d requests=%0d responses=%0d cycles=%0d",memCommands,requests,responses,cycles);if(requests!=responses)$fatal(1,"undrained bus");$finish;end endmodule')
 name=('context-memory16' if args.top.endswith('16') else 'context-memory')+('-mapped' if args.mapped else '-smoke' if args.smoke else '-rtl');tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
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
 result=dict(source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'tests/test_vector_memory.py',ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']},context_reads=contextReads,status='PASS',memory_cases=len(cases),stop_cases=len(stops),eew_emul_combinations=len(combinations),metrics=metrics,case_specs=cases,stop_specs=stops,benchmark_cases=benchmarkCases,
  register_check_scope='ALL_32' if not args.smoke else 'DATA_GROUP_V0_AND_GUARDS_16_23_31',assertions_enabled=not args.mapped,scope='physical normal RAM; registered memory model; no MMIO/PMP/VM/coherence',
  rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),
  summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS context-memory')))
 (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items() if k not in ['metrics','case_specs','stop_specs','benchmark_cases','context_reads']})
if __name__=='__main__':main()
