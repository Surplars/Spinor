#!/usr/bin/env python3
"""Reserved mixed-EEW source aliases, with architectural-state checks.

The case table names actual vector data operands rather than reimplementing
the RTL's needsVs2/vectorSource1 decode expressions. Mask-only sources and
scalar register number zero have separate positive coverage in old suites.
"""
import argparse, hashlib, json, random, subprocess
from pathlib import Path
from test_vector import HEADER

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/mask-source-alias';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp')
a=p.parse_args();fp=a.top=='RamVectorFp';rng=random.Random(0x2601)
h=HEADER.replace('wire [4:0] io_vl;', 'wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl')
h=h.replace('reg [31:0] saved;', 'reg [31:0] saved,oldVersions;reg [6:0] oldStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;', 'oldVersions=io_versions;oldStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(illegal && (io_versions!==oldVersions || io_vstart!==oldStart))$fatal(1,"reserved alias changed state");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard,1)
h=h.replace('cmds=cmds+1;',guard+'cmds=cmds+1;',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];case=0;vl=0;typ=1<<63
def cmd(inst,bad=False,result=0,wr=False,scalar=0,avl=0):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar:x},0,{avl},80'h{case:x},{int(bad)},64'h{result:x},{int(wr)},5,8'd{vl},64'h{typ:x});")
 case+=1
def checkregs(write=False):
 for r in range(32):
  for k in range(2):
   v=(regs[r]>>(64*k))&((1<<64)-1)
   lines.append(f"ctx({2*r+k},{int(write)},64'h{v:x},64'h{v:x});")
def enc(f6,f3,vs2,vs1,vm=0):return (f6<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(f3<<12)|(24<<7)|0x57
checkregs(True)
# Nonzero sticky state must survive every rejected instruction.
for address,value in [(9,1),(10,2)]+([(1,21),(2,3)] if fp else []):
 cmd((address<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,wr=True,scalar=value)
cases=[]
for f6 in [0,2,4,5,6,7,9,10,11,0x18,0x19,0x1a,0x1b,0x1c,0x1d,0x25,0x28,0x29,0x17]:
 for form in [0,4]+([3] if f6 not in [2,4,5,6,7,0x1a,0x1b] else []):
  cases.append(('integer-source2',enc(f6,form,0,8)))
  if form==0:cases.append(('integer-source1',enc(f6,form,8,0)))
for f6 in range(0x20,0x28):
 for form in [2,6]:cases.append(('mul-div-source2',enc(f6,form,0,8)))
 cases.append(('mul-div-source1',enc(f6,2,8,0)))
for f6 in range(8):
 cases.extend([('reduction-data',enc(f6,2,0,8)),('reduction-seed',enc(f6,2,8,0))])
for f6 in [0xe,0xf]:
 for form in [3,4,6]:cases.append(('slide',enc(f6,form,0,8)))
if fp:
 for f6 in [0,2,4,6,8,9,10,0x18,0x19,0x1b,0x1c,0x20,0x24,*range(0x28,0x30)]:
  cases.extend([('fp-source2',enc(f6,1,0,8)),('fp-source1',enc(f6,1,8,0)),('fp-vf-data',enc(f6,5,0,0))])
 for f6,selector in [(0x13,0),(0x13,16),*[(0x12,n) for n in [0,1,2,3,6,7]]]:
  cases.append(('fp-unary-data',enc(f6,1,0,selector)))
coverage={}
# Empty VL, all-masked-off and restart beyond VL still require decode checks.
for length,start,mask in [(0,0,0),(4,0,0),(4,127,(1<<128)-1)]:
 regs[0]=mask;checkregs(True)
 typ=16;vl=length
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,wr=True,avl=length)
 if start:cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=start,wr=True)
 for category,inst in cases:
  cmd(inst,bad=True);checkregs();coverage[category]=coverage.get(category,0)+1
  lines.append('if(io_vxrm!==2 || io_vxsat!==1)$fatal(1,"alias fixed CSR");')
  if fp:lines.append('if(io_frm!==3 || io_fflags!==21)$fatal(1,"alias FP CSR");')
# Decoder counterexamples: mask EEW=1 aliases and scalar/unary zero fields
# are legal. VL0 isolates this check from value computation (covered elsewhere).
vl=0
cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=0,wr=True,avl=0)
positive=[(enc(0,4,8,0),False),(enc(0x17,4,0,0,1),False),
          (enc(0x10,2,0,16),True),(enc(0x10,2,0,17),True),
          (enc(0x14,2,0,1),False),(enc(0x14,2,0,16),False),
          (enc(0x14,2,0,17),False)]
if fp:positive += [(enc(0,5,8,0),False),(enc(0x13,1,8,0),False),(enc(0x12,1,8,0),False)]
for inst,wr in positive:cmd(inst,wr=wr,result=(1<<64)-1 if wr and (inst>>15&31)==17 else 0);checkregs()
coverage['legal_zero_fields']=len(positive)
lines.append('$display("PASS mask-source-alias commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule')
label=a.top+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv')
files=[tb,rtl];extra=[]
if a.mapped:
 files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{a.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(a.top+'.','tb.dut.'));files.append(f);extra=['-s',a.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
d=dict(status='PASS',commands=case,reserved_cases=len(cases)*3,coverage=coverage,top=a.top,mapped=a.mapped,
 summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS mask-source-alias')),
 sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/core/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
