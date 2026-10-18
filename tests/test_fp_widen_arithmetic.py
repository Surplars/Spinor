#!/usr/bin/env python3
"""RVV wide FP architectural oracle: whole registers, independent SoftFloat math."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
from reference_fp_widen import WideReference
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-wide-arithmetic';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVectorFp16','RamVector','RamVector16'],default='RamVectorFp');a=p.parse_args();assert not a.mapped or a.compact
fp='Fp' in a.top;ref=WideReference();rng=random.Random(0x4050494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;'+('reg [4:0] oldFlags;' if fp else ''))
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;'+('oldFlags=io_fflags;' if fp else '')+'io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart)$fatal(1,"premature wide publish");'+('if(io_fflags!==oldFlags)$fatal(1,"premature FP flags");' if fp else '')
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall)begin '+guard+' if(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable wide reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;frm=0;flags=0;commands=0;performance=[];types=set();encodings=set()
coverage={x:0 for x in ['add','sub','wide_add','wide_sub','mul','fma','fnmacc','fmsac','fnmsac','illegal','masked','all_masked','restart','zero_vl','no_work','boxed','unboxed','cross_register','source_alias','high_overlap','bad_acc_overlap','mixed_eew_sources','fflags','flush','reserved_frm']}
ops={0x30:0,0x32:1,0x34:0,0x36:1,0x38:2,0x3c:5,0x3d:8,0x3e:6,0x3f:7}
names=dict(zip(ops,['add','sub','wide_add','wide_sub','mul','fma','fnmacc','fmsac','fnmsac']))
forms=[(code,form) for code in ops for form in [1,5]]
def ctx(r,write=False):
 for k in range(2):
  v=regs[r]>>(64*k)&M64;lines.append(f"ctx({2*r+k},{int(write)},64'h{v:x},64'h{v:x});")
def check():
 for r in range(32):ctx(r)
 lines.append(f'if(io_versions!==32\'h{versions:x} || io_vstart!=={start} || io_vxrm!==2 || io_vxsat!==1)$fatal(1,"state {commands}");')
 if fp:lines.append(f'if(io_frm!=={frm} || io_fflags!=={flags})$fatal(1,"FP state {commands}");')
def cmd(inst,scalar=0,result=0,write=False,bad=False,avl=0,record=None):
 global commands
 if record:lines.append('begin integer begun;begun=cycles;')
 lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x40ab<<64)|commands:x},{int(bad)},64'h{result&M64:x},{int(write)},{0 if record else rng.randrange(5)},8'd{vl},64'h{typ:x});");commands+=1
 if record:
  i=len(performance);performance.append(dict(id=i,**record));lines.append(f'$display("PERF {i} %0d",cycles-begun);end')
 check()
def csr(address,value):
 global start,frm,flags
 if address==8:old=start;start=value
 elif address==2:old=frm;frm=value
 elif address==1:old=flags;flags=value
 else:raise AssertionError(address)
 cmd(address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,result=old,write=True)
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(maximum,length);typ=s<<3|m;start=0
 cmd(typ<<20|1<<15|7<<12|3<<7|0x57,result=vl,write=True,avl=length)
def seed(wide=False):
 vals=[0,0x80000000,1,0x800000,0x3f800000,0x3f800001,0x3f7ffffe,0xbf800000,0x7f7fffff,0x7f800000,0xff800000,0x7f800001,0x7fc12345]
 seeds=[0,0x8000000000000000,1,0x3ff0000000000000,0xbff0000000000000,0x4340000000000000,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001]
 for r in range(32):
  regs[r]=sum(rng.choice(seeds)<<(64*k) for k in range(2)) if r in range(8,16) or wide and r in range(16,24) else sum(rng.choice(vals)<<(32*k) for k in range(4));ctx(r,True)
 regs[0]=int('a596'*8,16);ctx(0,True)
def element(snapshot,r,index,bits):return snapshot[r+index*bits//128]>>(index*bits%128)&((1<<bits)-1)
def execute(code,form,vd=8,src=16,other=24,vm=1,scalar=0xffffffff3f800001,record=False):
 global start,versions,flags
 s=typ>>3&3;m=typ&7;n=1<<m if m<4 else 1;dest=2*n if m<4 else 1;wide=code in [0x34,0x36];mac=code>=0x3c;vector=form==1;source=dest if wide else n
 group=lambda base,count:set(range(base,base+count))
 overlapA=bool(group(vd,dest)&group(src,source));overlapB=bool(vector and group(vd,dest)&group(other,n));mixed=bool(wide and vector and group(src,source)&group(other,n))
 highA=not wide and src==vd+dest-n and m<4;highB=vector and other==vd+dest-n and m<4
 badAcc=mac and (overlapA or overlapB)
 bad=bool(not fp or typ>>63 or s!=2 or m==3 or src%source or vd%dest or (vector and other%n) or (not wide and overlapA and not highA) or (overlapB and not highB) or badAcc or mixed or (not vm and (vd==0 or src==0 or vector and other==0)) or frm>4)
 old=tuple(regs);initial=start
 if bad:coverage['illegal']+=1;coverage['bad_acc_overlap']+=int(badAcc);coverage['mixed_eew_sources']+=int(mixed);coverage['reserved_frm']+=int(frm>4)
 else:
  active=[i for i in range(start,vl) if vm or old[0]>>i&1]
  for i in active:
   x=element(old,src,i,64 if wide else 32);y=element(old,other,i,32) if vector else scalar&0xffffffff if scalar>>32==0xffffffff else 0x7fc00000;c=element(old,vd,i,64)
   value,exc=ref(ops[code],2 if wide else 3,frm,x,y,c)
   r=vd+i//2;shift=i%2*64;regs[r]=regs[r]&~(M64<<shift)|value<<shift;flags|=exc
   coverage['fflags']+=int(exc!=0);coverage['cross_register']+=int(i*64>=128)
  if start<vl:versions^=((1<<dest)-1)<<vd
  coverage[names[code]]+=1;coverage['masked']+=int(not vm);coverage['all_masked']+=int(start<vl and not active);coverage['restart']+=int(start!=0);coverage['zero_vl']+=int(vl==0);coverage['no_work']+=int(start>=vl);coverage['source_alias']+=int(vd==src or vector and vd==other or vector and src==other);coverage['high_overlap']+=int(overlapA and highA or overlapB and highB)
  coverage['boxed' if scalar>>32==0xffffffff else 'unboxed']+=int(not vector);types.add(typ);encodings.add((code,form));start=0
 inst=code<<26|vm<<25|src<<20|(other if vector else 1)<<15|form<<12|vd<<7|0x57
 cmd(inst,scalar=scalar,bad=bad,record=dict(code=code,form=form,sew=32,result_bits=64,vtype=typ,vl=vl,vstart=initial,frm=frm) if record and not bad else None)
# Seed independent integer fixed-point sticky state, then preserve it throughout FP.
lines.append("command(32'h00a091f3,2,0,0,0,0,0,1,0,0,64'h8000000000000000);command(32'h009091f3,1,0,0,0,0,0,1,0,0,64'h8000000000000000);");commands+=2
for r in range(32):ctx(r,True)
execute(*forms[0])
alltypes=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for s,m in ([(2,0),(2,7),(3,0)] if a.compact else alltypes):
 config(s,m,4 if a.compact else 128)
 for code,form in forms:
  seed(code in [0x34,0x36])
  for rm in ([0] if a.compact else range(5)):
   if fp:
    if not a.compact:csr(2,rm)
    csr(1,0)
   execute(code,form,record=True)
  if not a.compact:
   csr(8,1);execute(code,form,vm=0)
   execute(code,form,vd=16);execute(code,form,vd=16,src=16+((1<<m) if m<3 else 1))
   execute(code,form,other=16)
   execute(code,form,vm=0,src=0)
 if not a.compact:
  regs[0]=0;ctx(0,True)
  for code,form in forms:execute(code,form,vm=0)
  config(s,m,0)
  for code,form in forms:execute(code,form)
# NaN boxing, inexact wide additions, masked flags and illegal frm are tested at VL0 too.
config(2,0,3);seed(True)
for code,form in ([(0x30,1),(0x34,5),(0x3c,1),(0x3d,5),(0x3e,1),(0x3f,5)] if a.compact else forms):
 execute(code,form,scalar=0x7f800001)
 if fp:csr(2,7)
 execute(code,form)
 if fp:csr(2,0)
 csr(8,127);execute(code,form)
 if fp:
  for delay in ([0,20] if a.compact else [0,1,3,10,20,35,60,100]):lines.append(f"cancel(32'h{code<<26|1<<25|16<<20|(24 if form==1 else 1)<<15|form<<12|8<<7|0x57:x},{delay},0);");coverage['flush']+=1;check()
  lines.append(f"cancel(32'h{code<<26|1<<25|16<<20|(24 if form==1 else 1)<<15|form<<12|8<<7|0x57:x},0,1);");coverage['flush']+=1;check()
 execute(code,form)
lines.append('$display("PASS fp-wide-arithmetic commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule')
label=a.top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{a.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(a.top+'.','tb.dut.'));files.append(f);extra=['-s',a.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(x.split()[1]):int(x.split()[2]) for x in run.stdout.splitlines() if x.startswith('PERF ')};assert len(observed)==len(performance)
for row in performance:row['cycles']=observed[row['id']]
r=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),encodings=sorted(encodings),performance=performance,reference_anchors=ref.anchors,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS fp-wide-arithmetic')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp_widen.py',ROOT/'tests/fp_widen_reference.c',ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/RamVector.scala',ROOT/'src/main/scala/vpu/FloatingPointLane.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(r,indent=2)+'\n');print(r['summary'])
