#!/usr/bin/env python3
"""RVV slide oracle over immutable whole-group element arrays (not RTL indices)."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/slide';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x245524);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"slide premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"slide stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
coverage={k:0 for k in ['up_vx','up_vi','down_vx','down_vi','up1','down1','illegal','overlap_up','alias_down','misaligned','reserved','masked_vd0','zero_vl','restart','nop_start','masked','all_masked','huge_offset','immediate_unsigned','past_vl_source','zero_source','below_offset','scalar_insert','scalar_masked','source_v0','dest_v0','cross_register','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"slide state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"slide FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2455<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
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
def encoding(down,form,vd,src,vm,operand):
 rs=operand if form==3 else 5
 return ((15 if down else 14)<<26)|(vm<<25)|(src<<20)|(rs<<15)|(form<<12)|(vd<<7)|0x57
def execute(down,form,vd,src,vm,operand,record=False):
 global start,versions
 group=(1<<(typ&7)) if typ&7<4 else 1;bits=8<<(typ>>3&3);mask=(1<<bits)-1;one=form==6
 offset=1 if one else operand
 overlap=not down and vd==src
 bad=bool(typ>>63 or vd%group or src%group or (not vm and vd==0) or form not in [3,4,6] or overlap)
 inst=encoding(down,form,vd,src,vm,operand)
 if bad:
  coverage['illegal']+=1;coverage['overlap_up']+=int(overlap);coverage['misaligned']+=int(vd%group!=0 or src%group!=0)
  coverage['reserved']+=int(form not in [3,4,6]);coverage['masked_vd0']+=int(not vm and vd==0)
 else:
  snapshot=list(regs)
  source=[(snapshot[src+(i*bits)//128]>>((i*bits)%128))&mask for i in range(maximum)]
  active=[i for i in range(start,vl) if vm or (snapshot[0]>>i)&1]
  for i in active:
   scalar=one and i==(vl-1 if down else 0)
   if not down and not one and i<offset:coverage['below_offset']+=1;continue
   j=i+offset if down else i-offset
   value=operand&mask if scalar else source[j] if 0<=j<maximum else 0
   coverage['scalar_insert']+=int(scalar)
   coverage['past_vl_source']+=int(not scalar and vl<=j<maximum)
   coverage['zero_source']+=int(not scalar and j>=maximum)
   coverage['cross_register']+=int(not scalar and 0<=j<maximum and (j*bits)//128!=(i*bits)//128)
   r=vd+(i*bits)//128;shift=(i*bits)%128
   regs[r]=(regs[r]&~(mask<<shift))|(value<<shift)
  if start<vl:versions^=((1<<group)-1)<<vd
  key=('down1' if down else 'up1') if one else ('down_' if down else 'up_')+('vi' if form==3 else 'vx')
  coverage[key]+=1;coverage['alias_down']+=int(down and vd==src);coverage['zero_vl']+=int(vl==0)
  coverage['restart']+=int(start!=0);coverage['nop_start']+=int(start>=vl and vl!=0)
  coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl>start)
  coverage['huge_offset']+=int(not one and offset>=256);coverage['immediate_unsigned']+=int(form==3 and offset>=16)
  coverage['scalar_masked']+=int(one and vl>0 and not vm and not ((snapshot[0]>>(vl-1 if down else 0))&1))
  coverage['source_v0']+=int(src==0);coverage['dest_v0']+=int(vd==0);seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=operand if form!=3 else rng.getrandbits(64),bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,down=down,form=form,vl=vl,vm=vm,operand=operand))
  lines.append(f'$display("SLIDEPERF {ident} %0d",cycles-begun);end')
 checkregs()
cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(False,4,8,16,1,1);execute(True,6,8,8,1,M64)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));group=1<<m if m<4 else 1
 for down,form in [(False,4),(False,3),(True,4),(True,3),(False,6),(True,6)]:
  for scenario in ([0,2,4] if args.smoke else range(8)):
   config(s,m,[mx,0,max(1,mx-1),1,mx,mx,mx,mx][scenario])
   vd=0 if scenario==5 else 8;src=8 if scenario==4 else 0 if scenario==7 else 16;vm=int(scenario not in [2,6,7])
   for r in sorted(set(range(src,src+group))|set(range(vd,vd+group))|{0}):regs[r]=rng.getrandbits(128);ctx(r,True)
   if scenario==6:regs[0]=0;ctx(0,True)
   if scenario==3:setstart(127)
   if scenario==7:setstart(max(1,mx//2))
   operand=(rng.getrandbits(64) if form==6 else [1,31,16,0,0,31,1,2][scenario])
   execute(down,form,vd,src,vm,operand,record=scenario==0)
  # Constraints are checked even at VL0; ordinary slide down permits alias.
  for length in [0,mx]:
   config(s,m,length);execute(down,form,0,16,0,1)
   if not down:execute(down,form,8,8,1,1)
   if group>1:execute(down,form,9,16,1,1);execute(down,form,8,17,1,1)
# Small explicit cases keep smoke coverage broad without duplicating all types.
config(0,3,0);execute(True,4,8,16,1,0)
config(0,3,1);setstart(127);execute(True,4,8,16,1,0)
config(0,3,128);execute(False,6,0,16,1,M64);execute(True,4,8,0,1,0)
# Boundary offsets retain XLEN precision and distinguish VL from VLMAX.
for s,m in ([(0,3),(3,3)] if args.smoke else types):
 config(s,m,max(1,((16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m)))-1))
 for down in [False,True]:
  for amount in ([0,1,127,128,256,M64] if args.smoke else [0,1,2,7,8,15,16,31,63,64,127,128,129,255,256,1<<32,1<<63,M64]):
   execute(down,4,8,16,1,amount)
  for amount in ([16,31] if args.smoke else range(32)):execute(down,3,8,16,1,amount)
# Mask only selects destination; source may be v0. Exercise suppressed scalar.
config(0,3,127);regs[0]=0;ctx(0,True)
for down in [False,True]:execute(down,6,8,0,0,M64)
for form in [0,1,2,5]:
 for down in [False,True]:execute(down,form,8,16,1,1)
# Cancellation across source calculation/read, pipeline and private writes.
config(0,3,128)
for down,form in [(False,4),(True,4),(False,6),(True,6)]:
 inst=encoding(down,form,8,16,1,1)
 for delay in ([0,2,8,10,12,20,75] if args.smoke else [0,2,*range(5,31),70,110,400]):
  lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
 execute(down,form,8,16,1,1,record=True)
lines+=['$display("PASS slide commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('SLIDEPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values()),coverage
assert len(seen_types)==(4 if args.smoke else 22)
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS slide')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
