#!/usr/bin/env python3
"""Independent bit-transfer oracle for vfmerge/vfmv: boxing, restart and flags."""
import argparse
import hashlib
import json
import random
import subprocess
from pathlib import Path
from test_vector import HEADER

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-select';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin';M64=(1<<64)-1
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVectorFp16','RamVector','RamVector16'],default='RamVectorFp');a=p.parse_args()
assert not a.mapped or a.compact
fp=a.top.startswith('RamVectorFp');rng=random.Random(0x50fbe128)
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','8000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart)$fatal(1,"early FP select commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall) begin\n'+guard,1)
lines=[h];regs=[0]*32;vl=0;typ=1<<63;start=0;versions=0;frm=0;flags=0;commands=0;specs=[]
coverage={k:0 for k in ['merge','broadcast','boxed','unboxed','snan','all_mask_zero','all_mask_one','restart','no_work','zero_vl','alias','vd0','f0','reserved_frm','illegal','flush']}
def ctx(r,write=False):
    for k in range(2):
        v=regs[r]>>(64*k)&M64;lines.append(f"ctx({2*r+k},{int(write)},64'h{v:x},64'h{v:x});")
def check():
    for r in range(32):ctx(r)
    lines.append(f'if(io_versions!==32\'h{versions:x} || io_vstart!=={start} || io_vxrm!==0 || io_vxsat!==0)$fatal(1,"FP select state {commands}");')
    if fp:lines.append(f'if(io_frm!=={frm} || io_fflags!=={flags})$fatal(1,"FP select changed floating flags {commands}");')
def command(inst,scalar=0,avl=0,result=0,writes=0,bad=False,verify=True):
    global commands
    lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x50fb<<64)|commands:x},{int(bad)},64'h{result&M64:x},{writes},{commands%5},8'd{vl},64'h{typ:x});");commands+=1
    if verify:check()
def config(s,m,length):
    global vl,typ,start
    maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=s<<3|m;start=0
    command(typ<<20|1<<15|7<<12|3<<7|0x57,avl=length,result=vl,writes=1)
def csr(address,value):
    global start,frm,flags
    old={8:start,2:frm,1:flags}[address]
    if address==8:start=value
    if address==2:frm=value
    if address==1:flags=value
    command(address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,result=old,writes=1)
def seed(mask):
    for r in range(32):regs[r]=rng.getrandbits(128);ctx(r,True)
    regs[0]=mask;ctx(0,True)
def select(merge,scalar,vd=8,src=16,freg=1):
    global start,versions
    bits=8<<(typ>>3&3);m=typ&7;n=1<<m if m<4 else 1
    bad=not fp or typ>>63 or bits<32 or vd%n or (merge and (src%n or src==0 or vd==0)) or (not merge and src!=0)
    prior=tuple(regs);initial=start
    if bad:coverage['illegal']+=1
    else:
        boxed=bits!=32 or scalar>>32==0xffffffff
        value=scalar if boxed else 0x7fc00000
        for i in range(start,vl):
            row=vd+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift
            source=prior[src+i*bits//128]>>shift if merge else 0
            result=value if not merge or prior[0]>>i&1 else source
            regs[row]=regs[row]&~mask|(result&((1<<bits)-1))<<shift
        if start<vl:versions^=((1<<n)-1)<<vd
        coverage['merge' if merge else 'broadcast']+=1;coverage['boxed' if boxed else 'unboxed']+=1
        coverage['snan']+=int((scalar&0xffffffff)==0x7f800001 or scalar==0x7ff0000000000001)
        coverage['all_mask_zero']+=int(merge and prior[0]==0);coverage['all_mask_one']+=int(merge and prior[0]==(1<<128)-1)
        coverage['restart']+=int(start!=0);coverage['no_work']+=int(start>=vl);coverage['zero_vl']+=int(vl==0)
        coverage['alias']+=int(merge and vd==src);coverage['vd0']+=int(vd==0);coverage['f0']+=int(freg==0);coverage['reserved_frm']+=int(frm>4)
        start=0
    inst=0x17<<26|int(not merge)<<25|src<<20|freg<<15|5<<12|vd<<7|0x57
    specs.append(dict(command=commands,merge=merge,scalar=scalar,vd=vd,src=src,freg=freg,vl=vl,vtype=typ,vstart=initial,frm=frm,illegal=bool(bad)))
    command(inst,scalar=scalar,bad=bad)
for r in range(32):ctx(r,True)
types=[(s,m) for s in [2,3] for m in [0,1,2,3,7] if m<4 or s<=m-5]
if a.compact:types=[(2,0),(3,0)]
for s,m in types:
    maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
    lengths=[maximum] if a.compact else [0,1,maximum]
    for length in lengths:
        config(s,m,length)
        if fp:csr(2,7);csr(1,8)
        for mask in ([0,(1<<128)-1] if a.compact else [0,(1<<128)-1,int('a596'*8,16)]):
            seed(mask)
            values=[0xffffffff7f800001,0x123456783f800000] if s==2 else [0x7ff0000000000001,0x8000000000000000]
            if not a.compact:values += [0,0xffffffffff800000,0xffffffffffffffff,0x012345677fc12345]
            for scalar in values:
                for merge in [False,True]:
                    for st in ([0,1] if a.compact else sorted({0,1,vl,127})):
                        csr(8,st);select(merge,scalar,src=16 if merge else 0,freg=0 if st%2==0 else 31)
                    if not a.compact:
                        select(merge,scalar,vd=16 if merge else 0,src=16 if merge else 0)
        for vd,src,merge in [(0,16,True),(8,0,True),(8,16,False),(9,16,True)]:select(merge,0xffffffff3f800000,vd=vd,src=src)
config(0,0,0);select(False,0xffffffff3f800000,src=0);select(True,0xffffffff3f800000)
config(1,0,1);select(False,0xffffffff3f800000,src=0);select(True,0xffffffff3f800000)
if fp:
    config(2,0,4);seed(int('a596'*8,16));csr(2,7);csr(1,8)
    for merge in [False,True]:
        inst=0x17<<26|int(not merge)<<25|(16 if merge else 0)<<20|1<<15|5<<12|8<<7|0x57
        for delay in ([0,12] if a.compact else [0,1,4,12,40]):
            lines.append(f"cancel(32'h{inst:x},{delay},0);");coverage['flush']+=1;check()
        lines.append(f"cancel(32'h{inst:x},0,1);");coverage['flush']+=1;check()
lines.append('$display("PASS fp-select commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule')
label=a.top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl];options=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];options=['-s','glbl']
else:
    src=ROOT/f'build/rtl/verification/assert/{a.top}_Verification_Assert.sv';monitor=OUT/(label+'-assert.sv')
    monitor.write_text(src.read_text().replace(a.top+'.','tb.dut.'));files.append(monitor);options=['-s',a.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([BIN/'iverilog','-g2012','-s','tb',*options,'-DTOP='+a.top,'-o',OUT/label,*files],stdout=log,stderr=log,check=True)
result=subprocess.run([BIN/'vvp',OUT/label],cwd=ROOT,capture_output=True,text=True,timeout=1800);(OUT/(label+'.log')).write_text(result.stdout+result.stderr)
assert result.returncode==0,(result.stdout+result.stderr)[-3500:]
d=dict(status='PASS',top=a.top,compact=a.compact,mapped=a.mapped,commands=commands,cases=len(specs),case_specs=specs,coverage=coverage,
       source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/RamVector.scala']},
       artifact_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*files,OUT/(label+'.log'),OUT/(label+'-compile.log')]},
       summary=next(x for x in result.stdout.splitlines() if x.startswith('PASS fp-select')))
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(label,d['summary'],flush=True)
