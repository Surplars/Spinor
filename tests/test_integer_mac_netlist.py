#!/usr/bin/env python3
"""Bounded RTL/mapped MAC integration vectors; full ISA matrix is test_integer_mac.py.

All eight encodings at each SEW plus alias, mask/restart and cancellation. Small
VL keeps event-driven FPGA primitive simulation useful for every iteration.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/integer-mac-netlist';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;').replace('input [4:0] expectedVl','input [7:0] expectedVl')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;').replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();if(io_versions!==oldVersions)$fatal(1,"early commit");end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\nif(io_versions!==oldVersions)$fatal(1,"held completion committed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;commands=0;macs=0;flushes=0
mask64=(1<<64)-1
coverage={'sew':set(),'encodings':set(),'overlap':0,'mask_restart':0,'cross_register':0,'upper_group':0,'held_flush':0}
def ctx(r,wr=False):
 for k in range(2):
  v=regs[r]>>(k*64)&mask64;lines.append(f"ctx({r*2+k},{int(wr)},64'h{v:x},64'h{v:x});")
def check():
 for r in range(32):ctx(r)
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2 || io_vxsat!==1 || io_frm!==3 || io_fflags!==21)$fatal(1,\"MAC architectural state\");")
def command(inst,scalar=0,result=0,writes=0,stall=2,check_state=True):
 global commands
 lines.append(f"command(32'h{inst:x},64'h{scalar&mask64:x},0,8'd{vl},80'h{0x35000000000000000000+commands:x},0,64'h{result:x},{writes},{stall},8'd{vl},64'h{typ:x});")
 commands+=1
 if check_state:check()
def config(s,m,length):
 global vl,typ,start
 vl=length;typ=(s<<3)|m;start=0
 command((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1)
def restart(n):
 global start
 old=start;start=n;command(0x008091f3,scalar=n,result=old,writes=1)
def seed(s):
 bits=8<<s;mask=(1<<bits)-1
 values=[1,mask,mask//2+1,mask//2,2,3,0x55,0xaa]
 for r in range(32):
  regs[r]=sum((values[(r+r//8+i)%len(values)]&mask)<<(i*bits) for i in range(128//bits));ctx(r,True)
 regs[0]=0b1010;ctx(0,True)
def execute(code,form,s,m=0,vd=8,src=16,other=24,vm=1,scalar=mask64):
 global versions,start,macs
 bits=8<<s;mask=(1<<bits)-1;old=tuple(regs)
 get=lambda base,i:old[base+i*bits//128]>>(i*bits%128)&mask
 for i in range(start,vl):
  if not vm and not (old[0]>>i&1):continue
  x=get(src,i);y=get(other,i) if form==2 else scalar&mask;d=get(vd,i)
  value={0x29:y*d+x,0x2b:x-y*d,0x2d:y*x+d,0x2f:d-y*x}[code]&mask
  row=vd+i*bits//128;shift=i*bits%128;regs[row]=(regs[row]&~(mask<<shift))|(value<<shift)
  coverage['cross_register']+=int(i*bits>=128)
 if start<vl:versions^=((1<<(1<<m))-1)<<vd
 coverage['mask_restart']+=int(not vm and start!=0);start=0
 command((code<<26)|(vm<<25)|(src<<20)|(other<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar)
 macs+=1;coverage['sew'].add(bits);coverage['encodings'].add((code,form));coverage['overlap']+=int(vd==src or form==2 and vd==other);coverage['upper_group']+=int(vd==30)
for r in range(32):ctx(r,True)
for csr,value in [(9,1),(10,2),(1,21),(2,3)]:command((csr<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,writes=1,check_state=False)
for s in range(4):
 config(s,0,2);seed(s)
 for code in [0x29,0x2b,0x2d,0x2f]:
  for form in [2,6]:execute(code,form,s)
# Upper two-register group and odd vstart. Only element 3 writes after masking;
# it lives in the second 128-bit word at SEW64.
config(3,1,4);seed(3)
for code in [0x29,0x2b,0x2d,0x2f]:
 restart(1);execute(code,2,3,m=1,vd=30,src=30,other=24,vm=0)
# Product handoff/ALU and held-completion flush, followed by valid instructions.
config(0,0,2);seed(0)
for code,delay in [(0x29,18),(0x2b,22),(0x2d,26),(0x2f,30)]:
 inst=(code<<26)|(1<<25)|(16<<20)|(24<<15)|(2<<12)|(8<<7)|0x57
 lines.append(f"cancel(32'h{inst:x},{delay},0);");check();flushes+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");check();flushes+=1;coverage['held_flush']+=1
 execute(code,2,0)
lines+=['$display("PASS integer-mac-netlist commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label='mapped' if args.mapped else 'rtl';tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/('build/synth/RamVectorFp/mapped.v' if args.mapped else 'build/rtl/RamVectorFp.sv');files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 f=OUT/(label+'-assert.sv');f.write_text((ROOT/'build/rtl/verification/assert/RamVectorFp_Verification_Assert.sv').read_text().replace('RamVectorFp.','tb.dut.'));files.append(f);extra=['-s','RamVectorFp_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-DTOP=RamVectorFp',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
assert coverage['sew']=={8,16,32,64} and len(coverage['encodings'])==8 and all(coverage.values())
coverage={k:sorted(v) if isinstance(v,set) else v for k,v in coverage.items()}
r=dict(status='PASS',mapped=args.mapped,commands=commands,mac_instructions=macs,flushes=flushes,coverage=coverage,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS integer-mac-netlist')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala',ROOT/'src/main/scala/vpu/PackedElementRead.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
