#!/usr/bin/env python3
"""Independent full-register architectural oracle for carry/borrow and fixed point.

Full mode sweeps all legal types, immediate encodings and move/restart boundaries.
Compact mode is intentionally bounded for FPGA primitive simulation.
"""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
from test_clip_lane import golden as clipGolden
from test_fractional_lane import golden as fractionalGolden
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m38-fixed';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.compact
fp=args.top=='RamVectorFp';rng=random.Random(0x3850494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;reg oldSat;').replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;oldSat=io_vxsat;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart || io_vxsat!==oldSat)$fatal(1,"premature state publication");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)


lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;saturation=0;rounding=0;commands=0;bench=[];types=set();encodings=set()
coverage={k:0 for k in ['multiply','clip_unsigned','clip_signed','saturated','masked','all_masked','restart','zero_vl','illegal','flush','source_alias','sticky_already_set','wide_source_boundary','post_round_overflow','min_product']}
def ctx(r,wr=False):
 for k in range(2):
  x=regs[r]>>(64*k)&M64;lines.append(f"ctx({2*r+k},{int(wr)},64'h{x:x},64'h{x:x});")
def check():
 for r in range(32):ctx(r)
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!=={start} || io_vxrm!=={rounding} || io_vxsat!=={saturation})$fatal(1,\"state cmd={commands}\");")
 if fp:lines.append('if(io_frm!==3 || io_fflags!==21)$fatal(1,"FP state");')
def command(inst,scalar=0,result=0,writes=0,bad=False,avl=None,record=None):
 global commands
 if record:lines.append('begin integer begun;begun=cycles;')
 lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{(vl if avl is None else avl):x},80'h{(0x37ab<<64)|commands:x},{int(bad)},64'h{result&M64:x},{writes},{0 if record else rng.randrange(5)},8'd{vl},64'h{typ:x});")
 commands+=1
 if record:
  ident=len(bench);bench.append(dict(id=ident,**record));lines.append(f'$display("PERF {ident} %0d",cycles-begun);end')
 check()
def csr(address,value):
 global start,saturation,rounding
 if address==8:old=start;start=value
 elif address==9:old=saturation;saturation=value&1
 elif address==10:old=rounding;rounding=value&3
 elif address==15:old=rounding*2+saturation;rounding=value>>1&3;saturation=value&1
 else:raise AssertionError(address)
 command(address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,result=old,writes=1)
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=s<<3|m;start=0
 command(typ<<20|1<<15|7<<12|3<<7|0x57,result=vl,writes=1,avl=length)
def seed(s):
 bits=8<<s;mask=(1<<bits)-1;vals=[1<<(bits-1),(1<<(bits-1))-1,mask,0,1,mask-1,2,3]
 for r in range(32):
  regs[r]=sum((vals[(r+i+r//8)%8]&mask)<<(bits*i) for i in range(128//bits));ctx(r,True)
 regs[0]=int('a596'*8,16);ctx(0,True)
def element(old,r,i,bits):return old[r+i*bits//128]>>(i*bits%128)&((1<<bits)-1)
def put(r,i,bits,value):
 row=r+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift;regs[row]=regs[row]&~mask|(value&((1<<bits)-1))<<shift

forms=[(0x27,f) for f in [0,4]]+[(code,f) for code in [0x2e,0x2f] for f in [0,4,3]]
def operate(code,form,vm=1,vd=8,src=16,other=24,scalar=63,imm=1,force_bad=False,record=False):
 global start,versions,saturation
 s=typ>>3&3;bits=8<<s;count=1<<(typ&7) if typ&7<4 else 1;wide=code!=0x27;sourceBits=2*bits if wide else bits;sourceCount=2*count if wide and typ&7<4 else count;vector=form==0
 group=lambda r,n:set(range(r,r+n))
 bad=bool(force_bad or typ>>63 or src%sourceCount or vd%count or (vector and other%count) or (wide and (s==3 or typ&7==3)) or (wide and vd!=src and group(vd,count)&group(src,sourceCount)) or (wide and vector and group(other,count)&group(src,sourceCount)) or (not vm and (vd==0 or src==0 or vector and other==0)))
 old=tuple(regs);initial=start;old_sat=saturation;mode=(15 if code==0x2f else 14) if wide else 28
 if bad:coverage['illegal']+=1
 else:
  active=[i for i in range(start,vl) if vm or old[0]>>i&1]
  for i in active:
   x=element(old,src,i,sourceBits);y=element(old,other,i,bits) if vector else scalar if form==4 else imm
   value,sat=(clipGolden if wide else fractionalGolden)(x,y,s,mode,rounding)
   put(vd,i,bits,value);saturation|=sat;coverage['saturated']+=sat
   coverage['min_product']+=int(not wide and x==1<<(bits-1) and y&((1<<bits)-1)==1<<(bits-1))
   coverage['wide_source_boundary']+=int(wide and i*sourceBits>=128)
   if wide:
    # Distinguish saturation introduced by rounding from pre-existing overflow.
    _,unrounded=clipGolden(x,y,s,mode,2);coverage['post_round_overflow']+=int(sat and not unrounded)
  if start<vl:versions^=((1<<count)-1)<<vd
  coverage['multiply' if not wide else 'clip_signed' if code==0x2f else 'clip_unsigned']+=1
  coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and start<vl);coverage['restart']+=int(start!=0);coverage['zero_vl']+=int(vl==0);coverage['source_alias']+=int(vd==src or vector and vd==other);coverage['sticky_already_set']+=old_sat
  encodings.add((code,form));types.add((code,typ));start=0
 inst=code<<26|vm<<25|src<<20|(other if vector else imm)<<15|form<<12|vd<<7|0x57
 command(inst,scalar=scalar,bad=bad,record=dict(code=code,form=form,vm=vm,sew=bits,vtype=typ,vl=vl,vstart=initial,rounding=rounding) if record else None)
def element(old,r,i,bits):return old[r+i*bits//128]>>(i*bits%128)&((1<<bits)-1)
def put(r,i,bits,value):
 row=r+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift;regs[row]=regs[row]&~mask|(value&((1<<bits)-1))<<shift
for r in range(32):ctx(r,True)
if fp:
 for address,value in [(1,21),(2,3)]:
  lines.append(f"command(32'h{address<<20|1<<15|1<<12|3<<7|0x73:x},64'd{value},0,0,0,0,0,1,1,8'd0,64'h8000000000000000);");commands+=1
operate(*forms[0])
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for s,m in ([(s,0) for s in range(4)] if args.compact else all_types):
 config(s,m,2 if args.compact else 128);seed(s)
 for code,form in forms:
  for rm in ([mode%4 for mode in [code]] if args.compact else range(4)):
   csr(15,rm*2);operate(code,form,scalar=1<<(7 if s==0 else (8<<s)-1) if code==0x27 else (8<<s)-1,imm=7 if s==0 else 15,record=True)
  if not args.compact:
   csr(8,1);operate(code,form,vm=0)
   operate(code,form,vd=16)
   if code!=0x27:
    operate(code,form,vd=24)
    if m in [0,1,2]:operate(code,form,vd=16+(1<<m));operate(code,form,other=16)
   else:operate(code,form,vd=24)
   operate(code,form,vm=0,src=0)
 if not args.compact:
  csr(9,0);regs[0]=0;ctx(0,True)
  for code,form in forms:operate(code,form,vm=0)
  config(s,m,0);csr(9,0)
  for code,form in forms:operate(code,form)
# Explicit round-before-saturation and MIN*MIN; scalar/imm shift sweeps.
for s in range(3):
 config(s,0,2);seed(s);bits=8<<s
 # Two wide inputs at +MAX+half and -MIN-half after scaling by one.
 regs[16]=((1<<bits)-1)|(((1<<(2*bits))-(1<<bits)-1)<<(2*bits));ctx(16,True)
 for rm in range(4):
  csr(15,rm*2)
  for code in [0x2e,0x2f]:operate(code,4,scalar=1);operate(code,3,imm=1)
 config(s,0,2);seed(s)
 if not args.compact:
  for shift in range(2*(8<<s)):
   for code in [0x2e,0x2f]:operate(code,4,scalar=shift);operate(code,3,imm=shift&31)
for s in range(4):
 config(s,0,2);bits=8<<s;seed(s)
 regs[16]=sum((1<<(bits-1))<<(i*bits) for i in range(128//bits));regs[24]=regs[16];ctx(16,True);ctx(24,True)
 for rm in range(4):csr(15,rm*2);operate(0x27,0);operate(0x27,4,scalar=1<<(bits-1))
# Candidate and completion cancellations, retry with nonzero vstart.
config(0,0,4);seed(0)
for code,form in forms:
 csr(9,0);csr(8,1)
 inst=code<<26|1<<25|16<<20|(24 if form==0 else 1)<<15|form<<12|8<<7|0x57
 for delay in ([12] if args.compact else [0,1,3,8,12,20,32,55,80,120]):
  lines.append(f'cancel(32\'h{inst:x},{delay},0);');coverage['flush']+=1;check()
 lines.append(f'cancel(32\'h{inst:x},0,1);');coverage['flush']+=1;check()
 operate(code,form)
# vm=0 whole-move encoding is reserved, not vsmul.vi.
operate(0x27,3,vm=0,force_bad=True)
csr(15,7);csr(9,0);csr(10,2)
lines+=['$display("PASS m38-fixed commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-compact' if args.compact else '-full')+('-mapped' if args.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(args.top+'.','tb.dut.'));files.append(f);extra=['-s',args.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('PERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert len(encodings)==8,encodings
result=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),encodings=sorted(encodings),performance=bench,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS m38-fixed')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/test_fixed_point_lane.py',ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/RamVector.scala',ROOT/'src/main/scala/vpu/FixedPointLane.scala',ROOT/'src/main/scala/vpu/IntegerMultiply.scala',ROOT/'tests/test_clip_lane.py',ROOT/'tests/test_fractional_lane.py']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
