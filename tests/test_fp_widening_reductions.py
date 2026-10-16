#!/usr/bin/env python3
"""Independent SoftFloat widening FP reduction oracle: immutable sources and whole architectural state."""
import argparse,functools,hashlib,json,operator,random,subprocess
from pathlib import Path
from test_vector import HEADER
from reference_fp import Reference
ref=Reference()
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-widening-reductions';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin';MASK=(1<<128)-1
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
rng=random.Random(0x182018);fp=args.top=='RamVectorFp'
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();if(io_versions!==originalVersions)$fatal(1,"early version publish");end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\nif(io_versions!==originalVersions)$fatal(1,"publish while completion stalled");',1)
if fp:
 h=h.replace('originalVersions;', 'originalVersions;reg [4:0] originalFlags;')
 h=h.replace('originalVersions=io_versions;', 'originalVersions=io_versions;originalFlags=io_fflags;')
 h=h.replace('if(io_versions!==originalVersions)', 'if(io_fflags!==originalFlags)$fatal(1,"early flags publish");if(io_versions!==originalVersions)')
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;vstart=0;case=0;frm=0;fflags=0
stats=dict(reductions=0,illegal=0,configs=0,flushes=0,all_masked=0,zero_vl=0,masked_vd0=0,unaligned_scalar=0,aliases=0,masked_source_v0=0,noncanonical_seed=0,rounding_modes=0,mixed_eew_sources=0,source_m8=0)
byop={i:0 for i in [1,3]};bytype={};bench=[]
lines.append("command(32'h00a091f3,2,0,0,0,0,0,1,0,0,64'h8000000000000000);")
lines.append("command(32'h009091f3,1,0,0,0,0,0,1,0,0,64'h8000000000000000);")
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{vstart} || io_vxrm!==2 || io_vxsat!==1)$fatal(1,\"state case {case}\");")
 if fp:lines.append(f"if(io_frm!==3'd{frm} || io_fflags!==5'd{fflags})$fatal(1,\"reduction changed FP CSR\");")
def cmd(inst,result=0,wr=0,scalar=0,avl=0,bad=False,stall=None):
 global case
 wait=rng.randrange(5) if stall is None else stall
 lines.append(f"command(32'h{inst:08x},64'h{scalar:x},0,64'h{avl:x},80'h{((0xdeadbeef<<48)|case):x},1'b{int(bad)},64'h{result:x},1'b{wr},{wait},8'd{vl},64'h{typ:x});")
 case+=1;state()
def ctx(r,write=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&((1<<64)-1)
  lines.append(f"ctx({2*r+k},1'b{int(write)},64'h{x:x},64'h{x:x});")
def config(sew,lmul,length,policy=0):
 global vl,typ,vstart
 typ=(sew<<3)|lmul|policy;maximum=(16>>sew)*(1<<lmul) if lmul<4 else (16>>sew)//(1<<(8-lmul))
 vl=min(maximum,length);vstart=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,wr=1,avl=length);stats['configs']+=1
def start(value):
 global vstart
 old=vstart;vstart=value;cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,result=old,wr=1,scalar=value)
def csr(address,value):
 global frm,fflags
 old=frm if address==2 else fflags
 if address==2:frm=value
 else:fflags=value
 cmd((address<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,result=old,wr=1,scalar=value)
def prepare(sew,lmul,scenario):
 global regs
 values=[0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x3f800000,0xbf800000,0x7f800000,0xff800000,0x7fc00123,0x7f800001,0x7f7fffff]
 regs=[sum(rng.choice(values)<<(e*32) for e in range(4)) for _ in range(32)]
 regs[31]=rng.choice([0,1,0x8000000000000000,0x3ff0000000000000,0x7ff0000000000000,0x7fefffffffffffff,0x7ff0000000000001])
 if scenario==0:
  for r in range(8,16):regs[r]=sum(0x3f800000<<(e*32) for e in range(4))
  regs[31]=0x3ff0000000000000
 elif scenario==2:regs[0]=0;regs[5]=0x7ff0000000000001
 elif scenario==1:regs[0]=sum(1<<i for i in range(0,128,2))
 elif scenario==4:regs[0]=MASK^1
 elif scenario==7:regs[0]=1<<max(0,vl-1)
 for r in range(32):ctx(r,True)
def reduction(op,vd,vs2,vs1,vm,bad=False,form=1,record=False):
 global versions,vstart,fflags
 sew=(typ>>3)&3;n=(1<<(typ&7)) if typ&7<4 else 1
 alias=vs2<=vs1<vs2+n;maskalias=not vm and (vs1==0 or vs2==0)
 bad=bad or not fp or alias or maskalias or sew!=2 or frm>4 or vstart!=0
 stats['mixed_eew_sources']+=int(alias);stats['masked_source_v0']+=int(maskalias)
 inst=((0x30+op)<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(form<<12)|(vd<<7)|0x57
 group=sum(regs[vs2+i]<<(128*i) for i in range(n)) if vs2+n<=32 else 0
 active=[(group>>(e*32))&0xffffffff for e in range(vl) if vm or (regs[0]>>e)&1]
 if not bad:
  if vl:
   value=regs[vs1]&((1<<64)-1)
   for source in active:
    # SoftFloat f32_to_f64 + f64_add, canonical NaN and conversion flags.
    value,flags=ref(27,True,frm,source,value);fflags|=flags
   regs[vd]=(regs[vd]&~((1<<64)-1))|value;versions^=1<<vd
  vstart=0;stats['reductions']+=1;byop[op]+=1;bytype[str(typ&63)]=bytype.get(str(typ&63),0)+1
  stats['all_masked']+=int(vl>0 and not active);stats['zero_vl']+=int(vl==0)
  stats['noncanonical_seed']+=int(vl>0 and not active and (regs[vs1]&((1<<64)-1))!=0)
  stats['masked_vd0']+=int(not vm and vd==0);stats['unaligned_scalar']+=int(vd%n!=0 or vs1%n!=0)
  stats['aliases']+=int(vs2<=vd<vs2+n or vd==vs1);stats['source_m8']+=int(n==8)
 else:stats['illegal']+=1
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,bad=bad,stall=0 if record else None)
 if record:
  ident=len(bench);bench.append(dict(id=ident,op=op,sew=32,accumulator_bits=64,vlmul=typ&7,vl=vl,active=len(active),frm=frm,completion_stall_cycles=0))
  lines.append(f'$display("REDPERF {ident} %0d",cycles-begun);end')
 for r in range(32):ctx(r)
types=[(2,m) for m in [0,1,2,3,7]]
if args.smoke:types=[(2,0),(2,3),(2,7)]
for sew,lmul in types:
 maximum=4*(1<<lmul) if lmul<4 else 2;n=(1<<lmul) if lmul<4 else 1
 for rm in ([0] if args.smoke else range(5)):
  if fp:csr(2,rm);stats['rounding_modes']+=1
  for op in [1,3]:
   for scenario in ([0,2,3,6] if args.smoke else range(8)):
    length=0 if scenario==3 else 1 if scenario==4 else max(0,maximum-1) if scenario==5 else maximum
    config(sew,lmul,length,rng.randrange(4)<<6);prepare(sew,lmul,scenario)
    if fp:csr(1,8)
    vd,vs1,vm={0:(7,31,1),1:(8+n-1,27,0),2:(0,5,0),3:(3,2,0),4:(31,31,0),5:(3,8+n-1,0),6:(8,31,1),7:(3,0,0)}[scenario]
    reduction(op,vd,8,vs1,vm,record=scenario==0)
 for length in [0,maximum]:
  config(2,lmul,length);prepare(2,lmul,0)
  for seed in range(8,8+n):reduction(1,3,8,seed,1)
  reduction(3,3,0,31,0);reduction(1,3,8,0,0)
 for op in [1,3]:
  config(2,lmul,maximum if op==3 else 0);prepare(2,lmul,0);start(127);reduction(op,3,8,31,1)
 if n>1:
  config(2,lmul,maximum);prepare(2,lmul,0);reduction(1,3,9,31,1,bad=True)
 config(2,lmul,maximum);prepare(2,lmul,0);reduction(1,3,8,31,1,bad=True,form=5)
 reduction(3,31,0,31,1);reduction(1,3,8,0,1)
for sew in [0,1,3]:
 for length in [0,1]:
  config(sew,0,length);prepare(sew,0,0)
  for op in [1,3]:reduction(op,3,8,31,1)
if fp:
 for rm in [5,6,7]:
  csr(2,rm)
  for length in [0,4]:
   config(2,0,length);prepare(2,0,0)
   for op in [1,3]:reduction(op,3,8,31,1)
 csr(2,0)
 # No-active seed copying must retain sNaN/qNaN payloads, -0 and flags.
 config(2,3,32);prepare(2,3,2)
 for seed in [0x8000000000000000,0x7ff8000000000123,0x7ff0000000000001]:
  regs[5]=seed;ctx(5,True)
  for op in [1,3]:csr(1,8);reduction(op,7,8,5,0)
 # Independent exact-promotion boundaries and double rounding counterexamples.
 values=[0,0x80000000,1,0x007fffff,0x00800000,0x3f800000,0xbf800000,0x7f7fffff,0x7f800000,0xff800000,0x7f800001,0x7fc00123]
 seeds=[1,0x8000000000000001,0x3ff0000000000001,0xbff0000000000000,0x7fefffffffffffff,0x7ff0000000000001]
 for rm in ([0] if args.smoke else range(5)):
  csr(2,rm);config(2,0,4)
  for i,x in enumerate(values):
   prepare(2,0,0);regs[8]=sum(v<<(e*32) for e,v in enumerate([x,x^0x80000000,x,1]));ctx(8,True)
   regs[31]=seeds[i%len(seeds)];ctx(31,True)
   for op in [1,3]:csr(1,8);reduction(op,7,8,31,1)
 csr(2,0)
 # Ordered fold: (2^53 + 1) - 2^53 + 1 == 1 with RNE, rather than 2.
 config(2,0,3);prepare(2,0,0);regs[8]=0x3f800000|(0xda000000<<32)|(0x3f800000<<64);ctx(8,True)
 regs[31]=0x4340000000000000;ctx(31,True)
 for op in [1,3]:csr(1,8);reduction(op,7,8,31,1)
# Maximum source group can end at v31; scalar seed stays outside that group.
config(2,3,32);prepare(2,3,0)
if fp:csr(1,8)
reduction(1,31,24,5,1,record=True)
config(2,3,32);prepare(2,3,1)
if fp:csr(1,8)
reduction(3,0,24,5,0,record=True)
# Cancellation after a pending sNaN operation must not publish NV.
config(2,3,32);prepare(2,3,0)
if fp:csr(1,8)
regs[31]=0x7ff0000000000001;ctx(31,True)
for op in [1,3]:
 inst=((0x30+op)<<26)|(1<<25)|(8<<20)|(31<<15)|(1<<12)|(7<<7)|0x57
 for delay in ([0,18,70] if args.smoke else [0,2,7,12,18,30,70,120,400,800]):
  lines.append(f"cancel(32'h{inst:08x},{delay},1'b0);");state()
  for r in range(32):ctx(r)
  stats['flushes']+=1
 lines.append(f"cancel(32'h{inst:08x},0,1'b1);");state()
 for r in range(32):ctx(r)
 stats['flushes']+=1
 reduction(op,7,8,31,1)
lines+=['$display("PASS fp-widening-reductions commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl')
tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv')
files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 assertions=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
 if assertions.exists():
  monitor=OUT/(label+'-assert.sv');monitor.write_text(assertions.read_text().replace(args.top+'.','tb.dut.'));files.append(monitor);extra=['-s',args.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(BIN/'vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('REDPERF ')}
assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert stats['illegal'] and stats['flushes']
if fp:assert all(byop.values()) and all(stats.values()) and len(bytype)>=len(types)
d=dict(status='PASS',scope='FP32_TO_FP64_REDUCTIONS_ORDERED_FOLD_NOT_FULL_RVV',top=args.top,mapped=args.mapped,commands=case+2,reference_anchors=ref.anchors,coverage=stats,by_operation=byop,by_type=bytype,performance=bench,
 summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS fp-widening-reductions')),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp.py',ROOT/'tests/fp_reference.c',ROOT/'src/main/scala/vpu/RamVector.scala',ROOT/'docs/references/fp-widening-reductions-v1.0.txt']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance','by_type']},indent=2))
