#!/usr/bin/env python3
"""Live command sequence alternating slides, reductions, streaming ALU, MUL and FP."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/reduction-interleave';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;').replace('input [4:0] expectedVl','input [7:0] expectedVl')
lines=[h];regs=[0]*32;versions=0;count=0;flags=rounding=vxsat=vxrm=0
def ctx(r,write=False):
 for chunk in range(2):
  x=(regs[r]>>(64*chunk))&((1<<64)-1)
  lines.append(f"ctx({2*r+chunk},1'b{int(write)},64'h{x:x},64'h{x:x});")
def setwords(r,words):regs[r]=sum(x<<(32*i) for i,x in enumerate(words));ctx(r,True)
def command(inst,result=0,writes=0,scalar=0):
 global count
 lines.append(f"command(32'h{inst:x},64'h{scalar:x},0,4,80'h{0xcccc0000000000000000+count:x},0,64'h{result:x},1'b{writes},3,8'd4,64'h10);")
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==0 || io_fflags!==5'd{flags} || io_frm!==3'd{rounding} || io_vxsat!==1'd{vxsat} || io_vxrm!==2'd{vxrm})$fatal(1,\"interleave state\");")
 count+=1
def execute(code,form,vd,source,seed,words,scalar=0):
 global versions
 regs[vd]=sum(x<<(32*i) for i,x in enumerate(words));versions^=1<<vd
 command((code<<26)|(1<<25)|(source<<20)|(seed<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar);ctx(vd)
for r in range(32):ctx(r,True)
command(0x0100f1d7,result=4,writes=1)
flags=21;command((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=flags)
rounding=3;command((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=rounding)
vxsat=1;command((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=vxsat)
vxrm=2;command((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=vxrm)
setwords(8,[1,2,3,4]);setwords(16,[10,0,0,0])
execute(0,2,24,8,16,[20,0,0,0])
execute(0,0,8,8,16,[11,2,3,4])
execute(6,2,31,8,16,[11,0,0,0])
execute(0x25,2,24,8,16,[110,0,0,0])
execute(3,2,24,24,31,[101,0,0,0])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
# Slide on FP bit patterns, then return to FP arithmetic: the slide mode,
# private VLMAX scratch and source offset must not leak into old operations.
execute(0x0e,3,24,8,1,[101,0x3f800000,0x3f800000,0x3f800000])
execute(0x0f,3,24,24,1,[0x3f800000,0x3f800000,0x3f800000,0])
execute(0,1,24,8,16,[0x40400000]*4)
execute(0x0f,6,24,24,5,[0x40400000,0x40400000,0x40400000,0x40000000],scalar=0x40000000)
execute(0,1,24,24,16,[0x40a00000,0x40a00000,0x40a00000,0x40800000])
execute(3,2,24,24,31,[0x0020000b,0x40a00000,0x40a00000,0x40800000])
execute(0x0e,6,8,24,5,[7,0x0020000b,0x40a00000,0x40a00000],scalar=7)
execute(0,0,8,8,16,[0x40000007,0x4020000b,0x80a00000,0x80a00000])
for r in range(32):ctx(r)
lines+=['$display("PASS reduction-interleave 13 vector instructions");$finish;end endmodule']
tb=OUT/'tb.sv';tb.write_text('\n'.join(lines));label='mapped' if args.mapped else 'rtl'
rtl=ROOT/('build/synth/RamVectorFp/mapped.v' if args.mapped else 'build/rtl/RamVectorFp.sv')
files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-DTOP=RamVectorFp',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
result=dict(status='PASS',mapped=args.mapped,vector_instructions=13,sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
