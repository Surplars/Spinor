#!/usr/bin/env python3
"""RVV narrowing shift oracle: immutable wide-source groups and narrow shift vectors."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/narrowing-shifts';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x325532);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"narrowing-shift premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"narrowing-shift stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
coverage={k:0 for k in ['logical','arithmetic','wv','wx','wi','illegal','bad_width','bad_emul','bad_form','misaligned','bad_overlap','source_alias','low_overlap','dest_shift_alias','fraction_source','masked_source_v0','masked_vd0','zero_vl','restart','restart_active','nop_start','masked','all_masked','source_v0','dest_v0','source_cross_register','shift_cross_register','negative','high_shift_bit','huge_shift','unsigned_immediate','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"narrowing-shift state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"narrowing-shift FP state");')
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
def geometry():
 bits=8<<(typ>>3&3);wide=bits*2
 # Derive EMUL from bytes occupied by VLMAX, independently of RTL alignment bits.
 dest_bytes=maximum*bits//8;source_bytes=maximum*wide//8
 return bits,wide,max(1,(dest_bytes+15)//16),max(1,(source_bytes+15)//16),source_bytes

def packed(snapshot,base,count):return sum(snapshot[base+j]<<(128*j) for j in range(count))
def execute(arithmetic,form,vd=8,src=16,idx=24,vm=1,operand=0,record=False,scan=True):
 global start,versions
 bits,wide,group,source_count,source_bytes=geometry()
 overlap=vd<src+source_count and src<vd+group
 alias=form==0 and idx<src+source_count and src<idx+group
 misaligned=vd%group!=0 or src%source_count!=0 or form==0 and idx%group!=0
 bad=bool(typ>>63 or form not in [0,3,4] or wide>64 or source_bytes>128 or misaligned or
          overlap and vd!=src or alias or not vm and (vd==0 or src==0 or form==0 and idx==0))
 amount_field=operand if form==3 else idx
 inst=((0x2d if arithmetic else 0x2c)<<26)|(vm<<25)|(src<<20)|(amount_field<<15)|(form<<12)|(vd<<7)|0x57
 if bad:
  coverage['illegal']+=1;coverage['bad_width']+=int(wide>64);coverage['bad_emul']+=int(source_bytes>128)
  coverage['bad_form']+=int(form not in [0,3,4]);coverage['misaligned']+=int(misaligned)
  coverage['bad_overlap']+=int(overlap and vd!=src);coverage['source_alias']+=int(alias)
  coverage['masked_source_v0']+=int(not vm and (src==0 or form==0 and idx==0));coverage['masked_vd0']+=int(not vm and vd==0)
 else:
  snapshot=list(regs);source=packed(snapshot,src,source_count);shifts=packed(snapshot,idx,group) if form==0 else 0
  active=[i for i in range(start,vl) if vm or snapshot[0]>>i&1]
  for i in active:
   x=source>>(i*wide)&((1<<wide)-1);negative=bool(x>>(wide-1))
   amount=(shifts>>(i*bits)&((1<<bits)-1)) if form==0 else operand
   shift=amount%(wide)
   value=((x-(1<<wide) if arithmetic and negative else x)>>shift)&((1<<bits)-1)
   row=vd+i*bits//128;offset=i*bits%128;mask=((1<<bits)-1)<<offset
   regs[row]=(regs[row]&~mask)|(value<<offset)
   coverage['source_cross_register']+=int(i*wide>=128);coverage['shift_cross_register']+=int(form==0 and i*bits>=128)
   coverage['negative']+=int(negative);coverage['high_shift_bit']+=int(shift>=bits);coverage['huge_shift']+=int(amount>=wide)
  if start<vl:versions^=((1<<group)-1)<<vd
  coverage['arithmetic' if arithmetic else 'logical']+=1;coverage[{0:'wv',3:'wi',4:'wx'}[form]]+=1
  coverage['low_overlap']+=int(overlap);coverage['dest_shift_alias']+=int(form==0 and vd==idx)
  coverage['fraction_source']+=int(source_bytes<16);coverage['unsigned_immediate']+=int(form==3 and operand>=16)
  coverage['zero_vl']+=int(vl==0);coverage['restart']+=int(start!=0);coverage['restart_active']+=int(0<start<vl)
  coverage['nop_start']+=int(start>=vl and vl!=0);coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl>start)
  coverage['source_v0']+=int(src==0);coverage['dest_v0']+=int(vd==0);seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=operand if form==4 else rng.getrandbits(64),bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,arithmetic=arithmetic,form=form,vl=vl,vm=vm,vtype=typ&63))
  lines.append(f'$display("NARROWPERF {ident} %0d",cycles-begun);end')
 if scan:checkregs()

def seed(src=16,idx=24,pattern=0):
 bits,wide,group,source_count,source_bytes=geometry()
 for r in range(32):regs[r]=rng.getrandbits(128)
 if wide<=64 and source_bytes<=128:
  values=[0,1,(1<<(wide-1))-1,1<<(wide-1),(1<<wide)-1,0x123456789abcdef0,0x55,0xaa]
  for i in range(maximum):
   row=src+i*wide//128;offset=i*wide%128;mask=((1<<wide)-1)<<offset
   value=values[i%len(values)] if pattern%2==0 else rng.getrandbits(wide)
   regs[row]=(regs[row]&~mask)|((value&((1<<wide)-1))<<offset)
  amounts=[0,bits-1,bits,wide-1,wide,wide+1,(1<<bits)-1,1]
  if src!=idx:
   for i in range(maximum):
    row=idx+i*bits//128;offset=i*bits%128;mask=((1<<bits)-1)<<offset
    regs[row]=(regs[row]&~mask)|((amounts[i%len(amounts)]&((1<<bits)-1))<<offset)
 if src!=0 and idx!=0:regs[0]=0 if pattern==3 else rng.getrandbits(128)
 for r in range(32):ctx(r,True)

cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(False,4) # vill with VL=0 remains illegal
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
types=[(0,2),(2,2),(0,5),(1,7),(3,0),(0,3)] if args.smoke else all_types
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
 for arithmetic in [False,True]:
  for form in [0,4,3]:
   scenarios=[0,2] if args.smoke else range(7)
   for scenario in scenarios:
    config(s,m,[mx,0,max(1,mx-1),mx,1,mx,mx][scenario]);seed(pattern=scenario)
    if scenario==4:setstart(127)
    if scenario==5:setstart(max(1,mx//2))
    execute(arithmetic,form,vm=int(scenario not in [2,3]),operand=31 if form==3 else 63,record=scenario==0)
   for length in ([0] if args.smoke else [0,mx]):
    config(s,m,length);bits,wide,group,scount,sbytes=geometry()
    execute(arithmetic,form,vd=16) # legal low overlap
    execute(arithmetic,form,vd=16+group) # forbidden higher overlap for integer LMUL
    execute(arithmetic,form,vd=0,vm=0);execute(arithmetic,form,src=0,vm=0)
    if form==0:execute(arithmetic,form,idx=16);execute(arithmetic,form,idx=0,vm=0)
    if group>1:execute(arithmetic,form,vd=9)
    if scount>1:execute(arithmetic,form,src=17)
   if not args.smoke:
    config(s,m,mx);seed();execute(arithmetic,form,vd=16)
    seed(src=0);execute(arithmetic,form,src=0)
    seed();execute(arithmetic,form,vd=0)
    if form==0:seed();execute(arithmetic,form,vd=24) # same-EEW destination/shift vector alias
# Explicit source-width shift masks, unsigned immediates and all vector amounts.
for s,m in ([(0,2),(2,2)] if args.smoke else [(0,2),(1,2),(2,2),(0,5)]):
 config(s,m,128);seed();bits,wide,group,scount,sbytes=geometry()
 for arithmetic in [False,True]:
  for amount in ([0,bits,wide-1,wide,1<<63,M64] if args.smoke else [0,1,bits-1,bits,wide-1,wide,wide+1,127,255,256,1<<32,1<<63,M64]):execute(arithmetic,4,operand=amount)
  for amount in ([16,31] if args.smoke else range(32)):execute(arithmetic,3,operand=amount)
# Legal low overlap and restart with source EMUL 8, including upper register edge.
for arithmetic in [False,True]:
 for form in [0,4,3]:
  config(0,2,63);seed(src=24,idx=8);setstart(31);execute(arithmetic,form,vd=24,src=24,idx=8,operand=8)
  config(2,0,4);seed();setstart(127);execute(arithmetic,form,operand=31)
config(0,2,64);seed(pattern=3);execute(False,4,vm=0)
config(0,2,64);seed(src=0);execute(False,4,src=0)
seed();execute(True,4,vd=0)
config(0,5,1);seed();execute(False,4);execute(True,4) # source fractional EMUL
config(0,2,64);seed();execute(False,0,vd=24) # destination aliases shift vector
for form in [2,6]:execute(False,form)
# Flush sampled across decode, copy, source reads, pipeline and held completion.
for arithmetic in [False,True]:
 for form in [0,4,3]:
  config(0,2,64);seed();inst=((0x2d if arithmetic else 0x2c)<<26)|(1<<25)|(16<<20)|((24 if form==0 else 5)<<15)|(form<<12)|(8<<7)|0x57
  for delay in ([0,8,12,30,75] if args.smoke else [0,2,*range(5,33),70,110]):
   lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
  lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
  execute(arithmetic,form,operand=5,record=True)
lines+=['$display("PASS narrowing-shifts commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('NARROWPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values()),coverage
result=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS narrowing-shifts')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
