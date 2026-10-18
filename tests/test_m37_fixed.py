#!/usr/bin/env python3
"""Independent full-register architectural oracle for carry/borrow and fixed point.

Full mode sweeps all legal types, immediate encodings and move/restart boundaries.
Compact mode is intentionally bounded for FPGA primitive simulation.
"""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
from test_fixed_point_lane import golden
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m37-fixed';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.compact
fp=args.top=='RamVectorFp';rng=random.Random(0x3750494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;reg oldSat;').replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;oldSat=io_vxsat;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart || io_vxsat!==oldSat)$fatal(1,"premature state publication");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)

lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;saturation=0;rounding=0;commands=0;bench=[];types=set();encodings=set()
coverage={k:0 for k in ['carry','carry_zero_bit','carry_one_bit','saturating','saturated','average','shift','masked','all_masked','restart','zero_vl','illegal','flush','destination_v0','source_alias','sticky_already_set']}
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
 bits=8<<s;mask=(1<<bits)-1;vals=[0,1,mask,mask-1,1<<(bits-1),(1<<(bits-1))-1,2,3]
 for r in range(32):
  regs[r]=sum((vals[(r+i+r//8)%8]&mask)<<(bits*i) for i in range(128//bits));ctx(r,True)
 regs[0]=int('a596'*8,16);ctx(0,True)
def element(old,r,i,bits):return old[r+i*bits//128]>>(i*bits%128)&((1<<bits)-1)
def put(r,i,bits,value):
 row=r+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift;regs[row]=regs[row]&~mask|(value&((1<<bits)-1))<<shift
# 15 carry encodings distinguish their fixed vm bit; other operations accept both vm values.
forms=[]
for code,mode in [(0x10,0),(0x11,2),(0x12,1),(0x13,3)]:
 for form in ([0,4,3] if code<0x12 else [0,4]):
  for vm in ([0,1] if code&1 else [0]):forms.append((code,form,mode,vm))
for code,mode in [(0x20,4),(0x21,5),(0x22,6),(0x23,7)]:
 for form in ([0,4,3] if code<0x22 else [0,4]):forms.append((code,form,mode,1))
for code,mode in [(8,8),(9,9),(10,10),(11,11)]:
 for form in [2,6]:forms.append((code,form,mode,1))
for code,mode in [(0x2a,12),(0x2b,13)]:
 for form in [0,4,3]:forms.append((code,form,mode,1))
assert len(forms)==39

def operate(code,form,mode,vm,vd=8,src=16,other=24,scalar=M64,imm=31,force_bad=False,record=False):
 global start,versions,saturation
 bits=8<<(typ>>3&3);count=1<<(typ&7) if typ&7<4 else 1;comp=mode in [2,3];vector=form in [0,2];carry=mode<4
 bad=bool(force_bad or typ>>63 or src%count or (vector and other%count) or (not comp and vd%count) or (comp and vd!=src and src<=vd<src+count) or (comp and vector and vd!=other and other<=vd<other+count) or (carry and not comp and (vm or vd==0)) or (not vm and (src==0 or vector and other==0 or not comp and vd==0)))
 old=tuple(regs);initial=start;old_sat=saturation
 if bad:coverage['illegal']+=1
 else:
  active=[i for i in range(start,vl) if carry or vm or old[0]>>i&1]
  for i in active:
   x=element(old,src,i,bits);y=element(old,other,i,bits) if vector else scalar if form in [4,6] else imm if mode>=12 or imm<16 else imm-32
   ci=int(not vm and old[0]>>i&1) if carry else 0
   val,sat=golden(x,y,bits.bit_length()-4,mode,rounding,ci)
   if comp:regs[vd]=regs[vd]&~(1<<i)|val<<i
   else:put(vd,i,bits,val)
   saturation|=sat;coverage['saturated']+=sat
   if carry:coverage['carry_one_bit' if ci else 'carry_zero_bit']+=1
  if start<vl:versions^=((1<<(1 if comp else count))-1)<<vd
  encodings.add((code,form,vm if carry else 1));types.add(typ)
  coverage['carry' if carry else 'saturating' if mode<8 else 'average' if mode<12 else 'shift']+=1
  coverage['masked']+=int(not vm and not carry);coverage['all_masked']+=int(not active and start<vl and not carry)
  coverage['restart']+=int(start!=0);coverage['zero_vl']+=int(vl==0);coverage['destination_v0']+=int(vd==0);coverage['source_alias']+=int(vd==src or vector and vd==other);coverage['sticky_already_set']+=old_sat
  start=0
 inst=code<<26|vm<<25|src<<20|(other if vector else imm)<<15|form<<12|vd<<7|0x57
 command(inst,scalar=scalar,bad=bad,record=dict(code=code,form=form,mode=mode,vm=vm,sew=bits,vtype=typ,vl=vl,vstart=initial,rounding=rounding) if record else None)
for r in range(32):ctx(r,True)
# FP sticky state is independent of fixed-point rounding/saturation.
if fp:
 for address,value in [(1,21),(2,3)]:
  lines.append(f"command(32'h{address<<20|1<<15|1<<12|3<<7|0x73:x},64'd{value},0,0,0,0,0,1,1,8'd0,64'h8000000000000000);");commands+=1
operate(*forms[0]) # vill rejection
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for s,m in ([(s,0) for s in range(4)] if args.compact else all_types):
 config(s,m,2 if args.compact else 128);seed(s)
 for code,form,mode,vm in forms:
  for rm in ([0,1,2,3] if mode>=8 and not args.compact else [mode%4]):
   csr(15,rm*2);operate(code,form,mode,vm,scalar=[M64,0,1<<63,1][rm],record=True)
  if not args.compact:
   csr(8,1);operate(code,form,mode,vm,vd=0 if mode in [2,3] else 8)
   if mode>=4:operate(code,form,mode,0)
   operate(code,form,mode,vm,vd=16)
 for code,form,mode,vm in forms:
  if not args.compact:operate(code,form,mode,vm,src=0);operate(code,form,mode,vm,vd=9 if m in [1,2,3] else 8,src=17 if m in [1,2,3] else 16)
 # No active body elements must not raise saturation, but successful completion clears vstart.
 if not args.compact:
  regs[0]=0;ctx(0,True);csr(9,0);operate(0x21,0,5,0)
  config(s,m,0);csr(9,0)
  for code,form,mode,vm in forms:operate(code,form,mode,vm)
# Sweep all immediate fields and shift distances at SEW64, including discarded-bit ties.
config(3,0,2);seed(3)
for code,form,mode,vm in forms:
 if form in [3,4,6] and not args.compact:
  for value in range(32):operate(code,form,mode,vm,scalar=value,imm=value)
# Carry encoding reservations and v0 restrictions; malformed immediate subtract forms.
config(0,0,4);seed(0)
for code,form,mode,vm in forms:
 if mode<4:
  if mode in [0,1]:operate(code,form,mode,1,force_bad=True);operate(code,form,mode,0,vd=0)
  operate(code,form,mode,0,src=0)
for code in [0x12,0x13,0x22,0x23]:operate(code,3,1 if code<0x20 else 6,0 if code<0x20 else 1,force_bad=True)
# Cancellations include partial candidate data, pending saturation and held completion.
for code,form,mode,vm in forms:
 if form not in [0,2]:continue
 csr(9,0);csr(8,1)
 inst=code<<26|vm<<25|16<<20|24<<15|form<<12|8<<7|0x57
 for delay in ([12] if args.compact else [0,1,3,8,12,20,32,55]):
  lines.append(f'cancel(32\'h{inst:x},{delay},0);');coverage['flush']+=1;check()
 lines.append(f'cancel(32\'h{inst:x},0,1);');coverage['flush']+=1;check()
 operate(code,form,mode,vm)
# CSR aliases and sticky clearing, then ordinary arithmetic after fixed operations.
csr(15,7);csr(9,0);csr(10,2)
lines+=['$display("PASS m37-fixed commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
assert len(encodings)==39,encodings
result=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),encodings=sorted(encodings),performance=bench,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS m37-fixed')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/test_fixed_point_lane.py',ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/RamVector.scala',ROOT/'src/main/scala/vpu/FixedPointLane.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
