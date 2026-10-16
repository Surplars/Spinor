#!/usr/bin/env python3
"""Independent RVV integer reduction oracle: whole-register state and version map."""
import argparse,functools,hashlib,json,operator,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/reductions';OUT.mkdir(parents=True,exist_ok=True)
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
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;vstart=0;case=0
stats=dict(reductions=0,illegal=0,configs=0,flushes=0,all_masked=0,zero_vl=0,masked_vd0=0,unaligned_scalar=0,aliases=0)
byop={i:0 for i in range(8)};bytype={};bench=[]
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{vstart} || io_vxrm!==0 || io_vxsat!==0)$fatal(1,\"state case {case}\");")
 if fp:lines.append("if(io_frm!==0 || io_fflags!==0)$fatal(1,\"reduction changed FP CSR\");")
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
def prepare(sew,lmul,scenario):
 global regs
 w=8<<sew;n=(1<<lmul) if lmul<4 else 1
 limits=[0,(1<<w)-1,1<<(w-1),(1<<(w-1))-1,1,2,(1<<w)-2]
 regs=[sum(rng.choice(limits+[rng.getrandbits(w)])<<(e*w) for e in range(128//w)) for _ in range(32)]
 if scenario==2:regs[0]=0
 elif scenario==1:regs[0]=sum(1<<i for i in range(0,128,2))
 elif scenario==4:regs[0]=MASK^1
 elif scenario==7:regs[0]=1<<max(0,vl-1)
 for r in range(32):ctx(r,True)
def reduce_value(op,values,w):
 mask=(1<<w)-1
 if op==0:return sum(values)&mask
 if op in [1,2,3]:return functools.reduce([operator.and_,operator.or_,operator.xor][op-1],values)&mask
 if op in [4,6]:return (min(values) if op==4 else max(values))&mask
 signed=lambda x:x-(1<<w) if x>>(w-1) else x
 return (min(values,key=signed) if op==5 else max(values,key=signed))&mask
def reduction(op,vd,vs2,vs1,vm,bad=False,form=2,record=False):
 global versions,vstart
 inst=(op<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(form<<12)|(vd<<7)|0x57
 oldregs=regs.copy();w=8<<((typ>>3)&3);m=(1<<w)-1;n=(1<<(typ&7)) if typ&7<4 else 1
 group=sum(regs[vs2+i]<<(128*i) for i in range(n)) if vs2+n<=32 else 0
 active=[(group>>(e*w))&m for e in range(vl) if vm or (regs[0]>>e)&1]
 if not bad:
  if vl:
   result=reduce_value(op,[regs[vs1]&m]+active,w)
   regs[vd]=(regs[vd]&~m)|result;versions^=1<<vd
  vstart=0
  stats['reductions']+=1;byop[op]+=1;bytype[str(typ&63)]=bytype.get(str(typ&63),0)+1
  stats['all_masked']+=int(vl>0 and not active);stats['zero_vl']+=int(vl==0)
  stats['masked_vd0']+=int(not vm and vd==0);stats['unaligned_scalar']+=int(vd%n!=0 or vs1%n!=0)
  stats['aliases']+=int(vs2<=vd<vs2+n or vd==vs1 or vs2<=vs1<vs2+n)
 else:stats['illegal']+=1
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,bad=bad,stall=0 if record else None)
 if record:
  ident=len(bench);bench.append(dict(id=ident,op=op,sew=w,vlmul=typ&7,vl=vl,active=len(active),completion_stall_cycles=0))
  lines.append(f'$display("REDPERF {ident} %0d",cycles-begun);end')
 # Read every register: catches tail/source corruption and invalid group commits.
 for r in range(32):ctx(r)
 if bad:assert regs==oldregs
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(s,s) for s in range(4)]+[(0,5),(1,6),(2,7)]
for sew,lmul in types:
 maximum=(16>>sew)*(1<<lmul) if lmul<4 else (16>>sew)//(1<<(8-lmul));n=(1<<lmul) if lmul<4 else 1
 for op in range(8):
  for scenario in ([0,2,6] if args.smoke else range(8)):
   length=0 if scenario==3 else 1 if scenario==4 else max(0,maximum-1) if scenario==5 else maximum
   config(sew,lmul,length,(rng.randrange(4)<<6));prepare(sew,lmul,scenario)
   vd,vs1,vm={0:(7,31,1),1:(8+n-1,27,0),2:(0,5,0),3:(3,2,0),4:(31,31,0),5:(3,8+n-1,0),6:(8,8,1),7:(3,0,0)}[scenario]
   reduction(op,vd,8,vs1,vm,record=scenario==0)
 # Reserved start is illegal even when VL=0, and must preserve all state.
 for op in range(8):
  config(sew,lmul,maximum if op&1 else 0);prepare(sew,lmul,0);start(1 if op&1 else 127)
  reduction(op,3,8,31,1,bad=True)
 if n>1:
  config(sew,lmul,maximum);prepare(sew,lmul,0);reduction(0,3,9,31,1,bad=True)
 config(sew,lmul,maximum);prepare(sew,lmul,0);reduction(0,3,8,31,1,bad=True,form=6)
# Maximum VL and register-group boundary (v24..v31) with scalar overlap.
config(0,3,128);prepare(0,3,0);reduction(0,31,24,25,1,record=True)
config(0,3,128);prepare(0,3,1);reduction(3,0,24,31,0,record=True)
# Flush at seed, accumulation, private writeback and stalled-completion phases.
config(0,3,128);prepare(0,3,0)
inst=(1<<25)|(8<<20)|(31<<15)|(2<<12)|(7<<7)|0x57
for delay in [0,2,7,12,18,30,70,400,1300]:
 lines.append(f"cancel(32'h{inst:08x},{delay},1'b0);");state()
 for r in range(32):ctx(r)
 stats['flushes']+=1
lines.append(f"cancel(32'h{inst:08x},0,1'b1);");state()
for r in range(32):ctx(r)
stats['flushes']+=1
reduction(0,7,8,31,1)
lines+=['$display("PASS reductions commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl')
tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv')
files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 module=args.top;assertions=ROOT/f'build/rtl/verification/assert/{module}_Verification_Assert.sv'
 if assertions.exists():
  monitor=OUT/(label+'-assert.sv');monitor.write_text(assertions.read_text().replace(module+'.','tb.dut.'));files.append(monitor);extra=['-s',module+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(BIN/'vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('REDPERF ')}
assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(byop.values()) and stats['masked_vd0'] and stats['aliases'] and stats['illegal'] and stats['all_masked']
d=dict(status='PASS',scope='SINGLE_WIDTH_INTEGER_REDUCTIONS_NOT_FULL_RVV',top=args.top,mapped=args.mapped,commands=case,coverage=stats,by_operation=byop,by_type=bytype,performance=bench,
 summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS reductions')),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance','by_type']},indent=2))
