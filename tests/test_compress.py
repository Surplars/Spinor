#!/usr/bin/env python3
"""Compress oracle: immutable source list filtered by explicit mask, stable order."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/compress';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x275527);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"compress premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"compress stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
coverage={k:0 for k in ['legal','illegal','dest_data_overlap','dest_mask_overlap','mixed_eew_source_overlap','misaligned','reserved_vm','reserved_form','reserved_start','zero_vl','empty','full','sparse','mask_v0','data_v0','dest_v0','unaligned_mask','cross_register','mask_above_vl','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"compress state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"compress FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2772<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
 case+=1
 if check:state()
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def checkregs():
 for r in range(32):ctx(r)
def config(s,m,length):
 global vl,typ,start,maximum
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m|(rng.randrange(4)<<6);start=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def setstart(value):
 global start
 old=start;start=value&127;cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,result=old,writes=1)
def encoding(vd=8,src=16,sel=3,vm=1,form=2):
 return (0x17<<26)|(vm<<25)|(src<<20)|(sel<<15)|(form<<12)|(vd<<7)|0x57
def execute(vd=8,src=16,sel=3,vm=1,form=2,record=False):
 global start,versions
 bits=8<<(typ>>3&3);group=(1<<(typ&7)) if typ&7<4 else 1
 data_overlap=bool(set(range(vd,vd+group))&set(range(src,src+group)))
 mask_overlap=sel in range(vd,vd+group);mixed=sel in range(src,src+group)
 misaligned=bool(vd%group or src%group)
 bad=bool(typ>>63 or data_overlap or mask_overlap or mixed or misaligned or not vm or form!=2 or start)
 inst=encoding(vd,src,sel,vm,form)
 selected=[]
 if bad:
  coverage['illegal']+=1;coverage['dest_data_overlap']+=int(data_overlap);coverage['dest_mask_overlap']+=int(mask_overlap)
  coverage['mixed_eew_source_overlap']+=int(mixed);coverage['misaligned']+=int(misaligned)
  coverage['reserved_vm']+=int(not vm);coverage['reserved_form']+=int(form!=2);coverage['reserved_start']+=int(start!=0)
 else:
  snapshot=list(regs)
  source=[(snapshot[src+i*bits//128]>>(i*bits%128))&((1<<bits)-1) for i in range(maximum)]
  # Stable list filtering is the semantic oracle, independent of RTL counters,
  # RAM byte offsets, mode reuse and integer-lane result timing.
  selected=[value for i,value in enumerate(source[:vl]) if snapshot[sel]>>i&1]
  for j,value in enumerate(selected):
   row=vd+j*bits//128;shift=j*bits%128;mask=((1<<bits)-1)<<shift
   regs[row]=(regs[row]&~mask)|(value<<shift)
  if vl:versions^=((1<<group)-1)<<vd
  start=0;coverage['legal']+=1;coverage['zero_vl']+=int(vl==0)
  coverage['empty']+=int(vl>0 and not selected);coverage['full']+=int(vl>0 and len(selected)==vl)
  coverage['sparse']+=int(0<len(selected)<vl);coverage['mask_v0']+=int(sel==0);coverage['data_v0']+=int(src==0)
  coverage['dest_v0']+=int(vd==0);coverage['unaligned_mask']+=int(sel%group!=0)
  coverage['cross_register']+=int(len(selected)*bits>128)
  coverage['mask_above_vl']+=int(bool(snapshot[sel]>>vl));seen_types.add(typ&63)
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=rng.getrandbits(64),bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,vl=vl,sew=bits,lmul=typ&7,selected=len(selected)))
  lines.append(f'$display("COMPRESSPERF {ident} %0d",cycles-begun);end')
 checkregs()
def seed(sel,pattern):
 for r in range(32):regs[r]=rng.getrandbits(128)
 masks=[0,M128,sum(1<<i for i in range(0,128,2)),1<<max(0,vl-1),1,
        rng.getrandbits(128),M128^((1<<vl)-1),sum(1<<i for i in [0,7,8,15,16,31,63,64,127])]
 regs[sel]=masks[pattern%len(masks)]
 for r in range(32):ctx(r,True)
cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute()
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));group=1<<m if m<4 else 1
 for pattern in ([0,1,2,7] if args.smoke else range(8)):
  config(s,m,mx);seed(3,pattern);execute(record=True)
 for length in [0,1,max(0,mx-1)]:
  config(s,m,length);seed(0,7);execute(sel=0)
 # Overlaps and vm/start constraints apply even at VL0, before no-op exits.
 for length in [0,mx]:
  config(s,m,length)
  execute(vd=16);execute(sel=8);execute(sel=8+group-1);execute(sel=16+group-1);execute(vm=0)
  if group>1:execute(vd=9);execute(src=17)
  setstart(1);execute();setstart(127);execute();setstart(0)
 # A mask is a single EEW1 register, not a data group with LMUL alignment.
 config(s,m,mx);seed(31,2);execute(src=0,sel=31)
 seed(31,7);execute(vd=0,src=8,sel=31)
# Low prefixes differ from source indices and span multiple rows at VLEN128*m8.
config(0,3,128)
for bit in ([0,7,8,63,64,127] if args.smoke else range(128)):
 seed(3,0);regs[3]=1<<bit;ctx(3,True);execute()
# Distinguish selected mask register from v0; upper bits beyond VL are ignored.
config(0,3,9);seed(31,6);execute(sel=31)
for form in [0,1,3,4,5,6]:execute(form=form)
# Cancel copy, mask fetch, source read, dense-address stage, writes and reply.
config(0,3,128);seed(3,1);inst=encoding()
for delay in ([0,2,8,12,16,20,40] if args.smoke else [0,2,*range(5,35),70,130,400,1000]):
 lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
execute(record=True)
# Empty and sparse masks also exercise count-owner reset after cancellation.
for pattern in [0,2,7]:seed(3,pattern);execute(record=True)
lines+=['$display("PASS compress commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(args.top+'.','tb.dut.'));files.append(f);extra=['-s',args.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('COMPRESSPERF ')};assert len(observed)==len(bench)
for row in bench:
 row['cycles']=observed[row['id']]
 assert row['cycles']<=20*row['vl']+64,('linear bound',row)
assert all(coverage.values()),coverage
assert len(seen_types)==(4 if args.smoke else 22)
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS compress')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/core/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
