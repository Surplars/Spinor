#!/usr/bin/env python3
"""Gather oracle using immutable whole-group arrays and byte-derived index EMUL."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/gather';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x255525);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"gather premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"gather stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
coverage={k:0 for k in ['vv','vx','vi','ei16','illegal','dest_data_overlap','dest_index_overlap','mixed_eew_source_overlap','misaligned','bad_emul','reserved','mask_source_alias','masked_vd0','zero_vl','restart','restart_active','nop_start','masked','all_masked','huge_index','unsigned_immediate','past_vl_source','zero_source','source_v0','index_v0','dest_v0','source_alias','cross_register','fraction_index','wide_index_group','narrow_index_group','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"gather state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"gather FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2555<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
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
def geometry(ei16):
 s=typ>>3&3;m=typ&7;bits=8<<s;group=(1<<m) if m<4 else 1;ibits=16 if ei16 else bits
 # Derive occupied registers from the number of index bytes, independently
 # of the implementation's compile-time EMUL exponent table.
 ibytes=maximum*ibits//8;icount=max(1,(ibytes+15)//16)
 return bits,group,ibits,ibytes,icount
def put_elements(base,values,bits):
 for i,value in enumerate(values):
  row=base+(i*bits)//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift
  regs[row]=(regs[row]&~mask)|((value&((1<<bits)-1))<<shift)
def elements(snapshot,base,bits):return [(snapshot[base+i*bits//128]>>(i*bits%128))&((1<<bits)-1) for i in range(maximum)]
def encoding(form,ei16,vd,src,idx,vm,operand):
 rs=operand if form==3 else idx if form==0 else 5
 return ((14 if ei16 else 12)<<26)|(vm<<25)|(src<<20)|(rs<<15)|(form<<12)|(vd<<7)|0x57
def execute(form,ei16,vd=8,src=16,idx=24,vm=1,operand=0,record=False):
 global start,versions
 bits,group,ibits,ibytes,icount=geometry(ei16)
 overlap_data=vd==src
 overlap_idx=form==0 and vd<idx+icount and idx<vd+group
 mixed=bool(ei16 and bits!=16 and src<idx+icount and idx<src+group)
 mask_alias=not vm and (src==0 or form==0 and idx==0)
 misaligned=bool(vd%group or src%group or form==0 and idx%icount)
 bad=bool(typ>>63 or form not in [0,3,4] or ei16 and form!=0 or misaligned or
          overlap_data or overlap_idx or mixed or mask_alias or not vm and vd==0 or ibytes>128 and form==0)
 inst=encoding(form,ei16,vd,src,idx,vm,operand)
 if bad:
  coverage['illegal']+=1;coverage['dest_data_overlap']+=int(overlap_data);coverage['dest_index_overlap']+=int(overlap_idx)
  coverage['mixed_eew_source_overlap']+=int(mixed);coverage['misaligned']+=int(misaligned)
  coverage['bad_emul']+=int(form==0 and ibytes>128);coverage['reserved']+=int(form not in [0,3,4] or ei16 and form!=0)
  coverage['mask_source_alias']+=int(mask_alias);coverage['masked_vd0']+=int(not vm and vd==0)
 else:
  snapshot=list(regs);source=elements(snapshot,src,bits)
  indices=elements(snapshot,idx,ibits) if form==0 else [operand]*maximum
  active=[i for i in range(start,vl) if vm or (snapshot[0]>>i)&1]
  for i in active:
   j=indices[i];value=source[j] if j<maximum else 0
   coverage['huge_index']+=int(j>=256);coverage['past_vl_source']+=int(vl<=j<maximum);coverage['zero_source']+=int(j>=maximum)
   coverage['cross_register']+=int(j<maximum and (j*bits)//128!=(i*bits)//128)
   row=vd+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift
   regs[row]=(regs[row]&~mask)|(value<<shift)
  if start<vl:versions^=((1<<group)-1)<<vd
  coverage['ei16' if ei16 else {0:'vv',3:'vi',4:'vx'}[form]]+=1
  coverage['zero_vl']+=int(vl==0);coverage['restart']+=int(start!=0);coverage['restart_active']+=int(0<start<vl);coverage['nop_start']+=int(start>=vl and vl!=0)
  coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl>start)
  coverage['unsigned_immediate']+=int(form==3 and operand>=16);coverage['source_v0']+=int(src==0)
  coverage['index_v0']+=int(form==0 and idx==0);coverage['dest_v0']+=int(vd==0)
  coverage['source_alias']+=int(form==0 and src==idx)
  coverage['fraction_index']+=int(form==0 and ibytes<16)
  coverage['wide_index_group']+=int(ei16 and icount>group);coverage['narrow_index_group']+=int(ei16 and icount<group)
  seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=operand if form==4 else rng.getrandbits(64),bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,form=form,ei16=ei16,vl=vl,vm=vm,operand=operand))
  lines.append(f'$display("GATHERPERF {ident} %0d",cycles-begun);end')
 checkregs()
def seed(form,ei16,vd=8,src=16,idx=24,pattern=0):
 bits,group,ibits,ibytes,icount=geometry(ei16)
 for r in range(32):regs[r]=rng.getrandbits(128)
 put_elements(src,[(i*37+11)&((1<<bits)-1) for i in range(maximum)],bits)
 if form==0 and ibytes<=128:
  values=[[maximum-1-i for i in range(maximum)],[(i*13)%maximum for i in range(maximum)],
          [maximum-1 if i%3 else (1<<ibits)-1 for i in range(maximum)],
          [i if i%2 else maximum+i for i in range(maximum)]][pattern%4]
  put_elements(idx,values,ibits)
 # Leave explicit v0 data/index source tests untouched by predicate seeding.
 if src!=0 and (form!=0 or idx!=0):regs[0]=0 if pattern==3 else rng.getrandbits(128)
 for r in range(32):ctx(r,True)
cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(0,False);execute(4,False,operand=M64)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,2),(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));group=1<<m if m<4 else 1
 for form,ei16 in [(0,False),(4,False),(3,False),(0,True)]:
  for scenario in ([0,2,3] if args.smoke else range(7)):
   config(s,m,[mx,0,max(1,mx-1),mx,1,mx,mx][scenario]);seed(form,ei16,pattern=scenario)
   if scenario==4:setstart(127)
   if scenario==5:setstart(max(1,mx//2))
   execute(form,ei16,vm=int(scenario not in [2,3]),operand=31 if form==3 else mx-1,record=scenario==0)
  for length in [0,mx]:
   config(s,m,length);execute(form,ei16,vd=0,vm=0)
   execute(form,ei16,vd=16)
   if form==0:execute(form,ei16,vd=24)
   if group>1:execute(form,ei16,vd=9);execute(form,ei16,src=17)
   if form==0 and geometry(ei16)[4]>1:execute(form,ei16,idx=25)
# Scalar/immediate index precision; read source tail between VL and VLMAX.
for s,m in ([(0,3),(3,3)] if args.smoke else types):
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));config(s,m,max(1,mx-1));seed(4,False)
 for val in ([0,127,128,256,M64] if args.smoke else [0,1,7,8,15,16,31,63,64,127,128,129,255,256,1<<32,1<<63,M64]):execute(4,False,operand=val)
 for val in ([16,31] if args.smoke else range(32)):execute(3,False,operand=val)
# Nonzero high bits with small low indices detect accidental truncation.
for s in [1,2,3]:
 config(s,2,128);seed(0,False)
 values=[0,1,1<<(8<<s)-1,(1<<(8<<s)-1)|1,256,257]
 put_elements(24,[values[i%len(values)] for i in range(maximum)],8<<s)
 for r in range(24,28):ctx(r,True)
 execute(0,False)
config(0,2,64);seed(0,True)
values=[0,1,63,64,256,257,0x8000,0xffff]
put_elements(24,[values[i%8] for i in range(maximum)],16)
for r in range(24,32):ctx(r,True)
execute(0,True)
# Index alignment must use its own EMUL, not the data LMUL.
config(3,3,16);seed(0,True,idx=26);execute(0,True,idx=26)
config(0,2,64);execute(0,True,idx=20)
# Every legal data element index, including register crossings and duplicates.
config(0,3,127);seed(0,False)
for val in ([0,7,8,63,64,126,127,128,255] if args.smoke else range(256)):
 put_elements(24,[val]*maximum,8)
 for r in range(24,32):ctx(r,True)
 execute(0,False)
# EEW16 fractional/wide/small group overlaps and same-EEW source alias.
for s,m in [(0,2),(3,3),(1,2)]:
 config(s,m,2);seed(0,True)
 execute(0,True,src=24) # different EEW forbidden, EEW=SEW=16 allowed
 execute(0,True,vd=12 if s==0 else 8,idx=8 if s==0 else 12)
 execute(0,True,idx=0,vm=0);execute(0,True,src=0,vm=0)
config(0,3,128);seed(0,False);execute(0,False,idx=16)
seed(0,False,idx=0);execute(0,False,idx=0)
seed(0,False,src=0);execute(0,False,src=0)
seed(4,False,vd=0);execute(4,False,vd=0,operand=1)
config(0,3,128);seed(0,False);setstart(63);execute(0,False)
config(0,3,0);execute(4,False)
config(0,3,1);setstart(127);execute(4,False)
for form in [1,2,5,6]:execute(form,False)
# Flush all index read, source bound/address, RAM and private-write phases.
for form,ei16 in [(0,False),(4,False),(3,False),(0,True)]:
 config(0,2,64);seed(form,ei16)
 inst=encoding(form,ei16,8,16,24,1,1)
 for delay in ([0,2,8,10,12,20,75] if args.smoke else [0,2,*range(5,33),70,110,250]):
  lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
 execute(form,ei16,operand=1,record=True)
lines+=['$display("PASS gather commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('GATHERPERF ')};assert len(observed)==len(bench)
for row in bench:
 row['cycles']=observed[row['id']]
 if row['form'] in [3,4] and row['vm'] and row['vl']>=32:
  assert row['cycles']<=3*row['vl']+64,('splat must amortize RAM reads',row)
assert all(coverage.values()),coverage
assert len(seen_types)==(8 if args.smoke else 22)
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS gather')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/core/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
