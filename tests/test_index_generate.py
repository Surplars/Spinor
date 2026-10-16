#!/usr/bin/env python3
"""Full-vector mathematical oracle for viota.m and vid.v; no DUT decode reuse."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/index-generate';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x235523);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"index premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"index stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0
seen_types=set();bench=[]
coverage=dict(vid=0,iota=0,illegal=0,overlap=0,masked_vd0=0,nonzero_start=0,vid_restart=0,reserved=0,misaligned=0,zero_vl=0,masked=0,all_masked=0,no_hit=0,source_v0=0,dest_v0=0,unaligned_source=0,flush=0)
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"index state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"index FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2355<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
 case+=1
 if check:state()
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def checkregs():
 for r in range(32):ctx(r)
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m|(rng.randrange(4)<<6);start=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def setstart(value):
 global start
 old=start;start=value&127;cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,result=old,writes=1)
def execute(mode,vd,src,vm,record=False,f3=2):
 global start,versions
 group=(1<<(typ&7)) if typ&7<4 else 1;bits=8<<(typ>>3&3)
 overlap=mode==16 and vd<=src<vd+group
 bad=bool(typ>>63 or vd%group or (not vm and vd==0) or mode not in [16,17] or f3!=2 or
          (mode==17 and src!=0) or (mode==16 and (start!=0 or overlap)))
 active=[i for i in range(vl) if vm or (regs[0]>>i)&1]
 hits=[i for i in active if (regs[src]>>i)&1]
 if bad:
  coverage['illegal']+=1;coverage['overlap']+=int(overlap);coverage['masked_vd0']+=int(not vm and vd==0)
  coverage['nonzero_start']+=int(mode==16 and start!=0);coverage['reserved']+=int(mode==17 and src!=0 or f3!=2 or mode not in [16,17]);coverage['misaligned']+=int(vd%group!=0)
 else:
  # Mathematical exclusive population count of the entire enabled prefix.
  # Independent of RAM reads, streamed element pipeline and counter feedback.
  for i in active:
   if i<start:continue
   value=i if mode==17 else sum(j<i for j in hits)
   r=vd+(i*bits)//128;shift=(i*bits)%128;mask=((1<<bits)-1)<<shift
   regs[r]=(regs[r]&~mask)|((value&((1<<bits)-1))<<shift)
  if start<vl:versions^=((1<<group)-1)<<vd
  coverage['iota' if mode==16 else 'vid']+=1;coverage['zero_vl']+=int(vl==0)
  coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl!=0)
  coverage['no_hit']+=int(not hits and mode==16);coverage['source_v0']+=int(src==0 and mode==16)
  coverage['dest_v0']+=int(vd==0);coverage['unaligned_source']+=int(mode==16 and src%group!=0)
  coverage['vid_restart']+=int(mode==17 and start!=0);seen_types.add(typ&63);start=0
 inst=(0x14<<26)|(vm<<25)|(src<<20)|(mode<<15)|(f3<<12)|(vd<<7)|0x57
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,op='vid' if mode==17 else 'iota',vl=vl,vm=vm,hits=len(hits)))
  lines.append(f'$display("INDEXPERF {ident} %0d",cycles-begun);end')
 checkregs()
# Seed unrelated architectural CSRs, then keep them unchanged throughout.
cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(16,8,31,1);execute(17,8,0,1)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));group=1<<m if m<4 else 1
 for mode in [16,17]:
  for scenario in ([0,1,2,4,5,6] if args.smoke else range(8)):
   config(s,m,[maximum,0,max(1,maximum-1),1,maximum,maximum,maximum,maximum][scenario])
   src=0 if mode==17 or scenario==4 else 31;vd=0 if scenario==6 else 8;vm=int(scenario not in [2,4,5])
   for r in range(vd,vd+group):regs[r]=rng.getrandbits(128);ctx(r,True)
   regs[0]=0 if scenario==5 else rng.getrandbits(128) if scenario in [2,4] else M128
   ctx(0,True)
   if mode==16:
    regs[src]=[M128,0,rng.getrandbits(128),1,0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,M128,1<<127,0][scenario];ctx(src,True)
   if mode==17 and scenario in [3,7]:setstart(1 if scenario==3 else 127)
   execute(mode,vd,src,vm,record=scenario==0)
  # Check illegal restrictions even at zero length; iota source is one mask
  # register but the destination consumes a normal LMUL group.
  for length in [0,maximum]:
   config(s,m,length);execute(mode,0,0 if mode==17 else 31,0)
   if mode==16:
    for src in sorted({8,8+group-1}):execute(mode,8,src,1)
    setstart(1);execute(mode,8,31,1)
   else:execute(mode,8,31,1)
   if group>1:execute(mode,9,0 if mode==17 else 31,1)
# Every source bit, cross-byte and register boundaries, partial tails.
config(0,3,128)
for bit in ([0,7,8,63,64,127] if args.smoke else range(128)):
 regs[31]=1<<bit;ctx(31,True)
 for vm in [0,1]:
  regs[0]=M128^(1<<bit);ctx(0,True);execute(16,8,31,vm)
for length in ([7,8,9,127] if args.smoke else [*range(1,18),63,64,65,127,128]):
 config(0,3,length);regs[31]=M128;regs[0]=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;ctx(31,True);ctx(0,True)
 execute(16,8,31,0);execute(17,8,0,0)
 for restart in sorted({1,length-1,length,127}):setstart(restart);execute(17,8,0,1)
config(0,3,128)
for mode in [16,17]:execute(mode,8,0 if mode==17 else 31,1,f3=1)
# Flush every data/writeback phase, after candidate writes and held completion;
# committed source and all destination rows must remain intact.
for mode in [16,17]:
 inst=(0x14<<26)|(1<<25)|((0 if mode==17 else 31)<<20)|(mode<<15)|(2<<12)|(8<<7)|0x57
 for delay in ([0,2,8,10,12,20,75] if args.smoke else [0,2,*range(5,30),70,110,400]):
  lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
 execute(mode,8,0 if mode==17 else 31,1,record=True)
lines+=['$display("PASS index-generate commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('INDEXPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values()),coverage
assert len(seen_types)==(4 if args.smoke else 22)
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS index-generate')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
