#!/usr/bin/env python3
"""Wire the actual LSU to the actual host boundary; verify faults before RAM access."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/memory-boundary';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');a=p.parse_args()
def ports(top):
 s=(ROOT/f'build/rtl/{top}.sv').read_text().split('module '+top+'(')[1].split(');')[0];out=[];direction=None;width=''
 for part in s.split(','):
  part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
  if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
  else:name=part
  out.append((direction,width,name))
 return out
bp=ports('VpuHostBoundary');ep=ports('VectorMemoryEngine');lines=['module tb;']
for direction,width,name in bp:
 fromEngine=name=='io_command_ready' or name.startswith(('io_completion_','io_memoryStatus_'))
 reg=direction=='input' and not fromEngine
 lines.append(f'{"reg" if reg else "wire"} {width} {name}'+('=0;' if reg else ';'))
for direction,width,name in ep:
 reg=name in ['io_vl','io_vtype','io_vstart']
 lines.append(f'{"reg" if reg else "wire"} {width} e_{name}'+('=0;' if reg else ';'))
 if direction=='input' and not reg:
  if name in ['clock','reset']:rhs=name
  elif name.startswith('io_command_') or name=='io_completion_ready':rhs=name
  elif name=='io_stop':rhs='io_vpuFlush'
  elif name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready']:rhs="1'b1"
  else:rhs="'0"
  lines.append(f'assign e_{name}={rhs};')
for direction,width,name in bp:
 if direction!='input':continue
 if name=='io_command_ready' or name.startswith('io_completion_'):lines.append(f'assign {name}=e_{name};')
 elif name=='io_memoryStatus_valid':lines.append('assign io_memoryStatus_valid=e_io_completion_valid;')
 elif name.startswith('io_memoryStatus_bits_'):lines.append(f'assign {name}=e_io_status_{name.removeprefix("io_memoryStatus_bits_")};')
lines.append('VpuHostBoundary host('+','.join(f'.{n}({n})' for _,_,n in bp)+');')
lines.append('VectorMemoryEngine lsu('+','.join(f'.{n}(e_{n})' for _,_,n in ep)+');')
lines.append('''integer cycles=0,cases=0;
always @(posedge clock)if(!reset)begin
 if(e_io_commit_valid && e_io_commit_ready)e_io_vstart<=e_io_commit_bits;
 if(e_io_context_valid || e_io_memoryRequest_valid)$fatal(1,"fault escaped before RAM/context");
end
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>10000)$fatal(1,"timeout");end endtask
task run(input [31:0] inst,input [63:0] address,typ,input integer vl,cause);
reg [79:0] tag;reg [63:0] tval;integer raw;begin
 reset=1;tick();tick();reset=0;tick();
 e_io_vtype=typ;e_io_vl=vl;e_io_vstart=0;tag=80'hf1230000000000000000+cases;
 io_headValid=1;io_headToken=tag;io_olderMemoryDrained=1;io_olderFpDrained=1;
 io_offer_bits_instruction=inst;io_offer_bits_token=tag;io_offer_bits_scalar=address;io_offer_bits_scalar2=64'hdeadbeef;
 io_offer_valid=1;#1;if(!io_offer_ready)$fatal(1,"admit");tick();io_offer_valid=0;
 while(!io_reply_valid)tick();
 raw=cause==2?0:cause;tval=cause==2?{32'h0,inst}:address;
 repeat(4)begin
  #1;if(!io_reply_valid || !io_active || io_protocolError || !io_reply_bits_memory || !io_reply_bits_exception ||
   io_reply_bits_stopped || io_reply_bits_cause!==cause || io_reply_bits_rawMemoryCause!==raw ||
   io_reply_bits_tval!==tval || io_reply_bits_element!==0 || io_reply_bits_completion_token!==tag ||
   io_reply_bits_completion_instruction!==inst || io_reply_bits_completion_writesScalar || e_io_vstart!==0)
   $fatal(1,"actual LSU/host case=%0d raw=%0d cause=%0d/%0d valid=%b active=%b proto=%b memory=%b ex=%b stop=%b tval=%h/%h element=%d token=%h/%h inst=%h/%h wr=%b start=%d",cases,io_reply_bits_rawMemoryCause,io_reply_bits_cause,cause,io_reply_valid,io_active,io_protocolError,io_reply_bits_memory,io_reply_bits_exception,io_reply_bits_stopped,io_reply_bits_tval,tval,io_reply_bits_element,io_reply_bits_completion_token,tag,io_reply_bits_completion_instruction,inst,io_reply_bits_completion_writesScalar,e_io_vstart);
  tick();
 end
 io_reply_ready=1;tick();io_reply_ready=0;
 if(io_active || e_io_busy || io_protocolError)$fatal(1,"undrained fault owner");cases=cases+1;
end endtask
initial begin reset=1;tick();tick();reset=0;tick();
''')
BASE=0x80000000;specs=[]
def issue(inst,addr,typ,vl,cause):
 specs.append(dict(instruction=inst,address=addr,vtype=typ,vl=vl,cause=cause));lines.append(f"run(32'h{inst:x},64'h{addr:x},64'h{typ:x},{vl},{cause});")
for store in [False,True]:
 for ew in range(4):
  inst=(1<<25)|(1<<15)|([0,5,6,7][ew]<<12)|(8<<7)|(0x27 if store else 7)
  if ew:issue(inst,BASE+1,24,1,6 if store else 4)
  issue(inst,0x1234567880000000,24,1,7 if store else 5)
for ew in range(4):
 inst=(7<<29)|(1<<25)|(8<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(8<<7)|7
 if ew:issue(inst,BASE+1,1<<63,0,4)
 issue(inst,0x90000000,1<<63,0,5)
issue(0xe2808427,0x90000000,1<<63,0,7)
for store in [False,True]:
 inst=(1<<25)|(11<<20)|(1<<15)|(0x27 if store else 7)
 issue(inst,0x90000000,3,9,7 if store else 5);issue(inst,BASE,1<<63,0,2)
# New segments fail before any RF or RAM operation; every case is a cold first command.
for store in [False,True]:
 for ew in range(4):
  inst=(2<<29)|(2<<26)|(1<<25)|(2<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(8<<7)|(0x27 if store else 7)
  if ew:issue(inst,BASE+1,ew<<3,1,6 if store else 4)
  issue(inst,0x1234567880000000,ew<<3,1,7 if store else 5)
for mop in [1,3]:
 for ew in range(4):
  inst=(2<<29)|(mop<<26)|(1<<25)|(10<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(8<<7)|7
  issue(inst,BASE,ew<<3,1,2)
 inst=(2<<29)|(mop<<26)|(1<<25)|(10<<20)|(1<<15)|(8<<7)|0x27
 issue(inst,BASE,8,1,2)
lines.append('$display("PASS memory-boundary cases=%0d cycles=%0d",cases,cycles);$finish;end endmodule')
label='mapped' if a.mapped else 'rtl';tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));sources=[ROOT/(f'build/synth/{top}/mapped.v' if a.mapped else f'build/rtl/{top}.sv') for top in ['VectorMemoryEngine','VpuHostBoundary']];files=[tb,*sources]
if a.mapped:files.append(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')
with (OUT/(label+'-compile.log')).open('w') as f:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=f,stderr=f,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
inputs=[tb,*sources,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VpuHostBoundary.scala',ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala'];d=dict(status='PASS',cold_reset_each_case=True,segment_pre_access_fault_cases=24,cases=len(specs),specs=specs,scope='ACTUAL_LSU_AND_HOST_BOUNDARY; FAULTS_BEFORE_RAM_ACCESS; NO_ORBITAL_CPU_OR_TILELINK_MODEL',summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS memory-boundary')),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
