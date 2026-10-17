#!/usr/bin/env python3
"""Independent architectural oracle for reverse/greater-than, whole moves and compact widening MAC.

Full mode sweeps all legal types, immediate encodings and move/restart boundaries.
Compact mode is intentionally bounded for FPGA primitive simulation.
"""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m36-integer';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.compact
fp=args.top=='RamVectorFp';rng=random.Random(0x3650494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;').replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart)$fatal(1,"premature state publication");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;commands=0;bench=[]
coverage={k:0 for k in ['reverse','gt','gtu','whole','wmac','illegal','flush','zero_vl_move','vill_move','restart_move','self_move','compare_v0','masked','immediate_negative','whole_partial_byte_group','all_masked']}
encodings=set();types=set()
def ctx(r,wr=False):
 for k in range(2):
  x=regs[r]>>(k*64)&M64;lines.append(f"ctx({2*r+k},{int(wr)},64'h{x:x},64'h{x:x});")
def check():
 for r in range(32):ctx(r)
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!=={start} || io_vxrm!==2 || io_vxsat!==1)$fatal(1,\"state {commands}\");")
 if fp:lines.append('if(io_frm!==3 || io_fflags!==21)$fatal(1,"FP state");')
def command(inst,scalar=0,result=0,writes=0,bad=False,check_state=True,record=None,avl=None):
 global commands
 if record:lines.append('begin integer begun;begun=cycles;')
 lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{(vl if avl is None else avl):x},80'h{(0x36ab<<64)|commands:x},{int(bad)},64'h{result&M64:x},{writes},{0 if record else rng.randrange(5)},8'd{vl},64'h{typ:x});")
 commands+=1
 if record:
  ident=len(bench);bench.append(dict(id=ident,**record));lines.append(f'$display("PERF {ident} %0d",cycles-begun);end')
 if check_state:check()
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m;start=0
 command((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def vill():
 global vl,typ,start
 vl=0;typ=1<<63;start=0;command((0x20<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=0,writes=1)
def restart(value):
 global start
 old=start;start=value;command(0x008091f3,scalar=value,result=old,writes=1)
def seed(s=0):
 bits=8<<s;mask=(1<<bits)-1;values=[0,1,mask,mask//2,mask//2+1,0xaa,0x55,2]
 for r in range(32):
  regs[r]=sum((values[(r+r//8+i)%8]&mask)<<(i*bits) for i in range(128//bits));ctx(r,True)
 regs[0]=rng.getrandbits(128);ctx(0,True)
def element(old,r,i,bits):return old[r+i*bits//128]>>(i*bits%128)&((1<<bits)-1)
def put(r,i,bits,value):
 row=r+i*bits//128;shift=i*bits%128;mask=((1<<bits)-1)<<shift;regs[row]=(regs[row]&~mask)|((value&((1<<bits)-1))<<shift)
def basic(code,form,vd=8,src=16,imm=31,scalar=M64,vm=1):
 global start,versions
 bits=8<<(typ>>3&3);count=1<<(typ&7) if typ&7<4 else 1;comp=code!=3
 bad=bool(typ>>63 or form not in [3,4] or src%count or (not comp and vd%count) or (comp and vd!=src and src<=vd<src+count) or (not vm and (src==0 or (not comp and vd==0))))
 old=tuple(regs);initial=start
 if bad:coverage['illegal']+=1
 else:
  rhs=(scalar if form==4 else imm if imm<16 else imm-32)&((1<<bits)-1)
  active=[i for i in range(start,vl) if vm or old[0]>>i&1]
  for i in active:
   x=element(old,src,i,bits)
   if code==3:put(vd,i,bits,rhs-x)
   else:
    signed=lambda v:v-(1<<bits) if v>>(bits-1) else v
    val=(signed(x)>signed(rhs)) if code==0x1f else x>rhs
    regs[vd]=(regs[vd]&~(1<<i))|(int(val)<<i)
  if start<vl:versions^=((1<<(1 if comp else count))-1)<<vd
  coverage[{3:'reverse',0x1e:'gtu',0x1f:'gt'}[code]]+=1;coverage['masked']+=int(not vm);coverage['compare_v0']+=int(comp and vd==0)
  coverage['immediate_negative']+=int(form==3 and imm>=16);coverage['all_masked']+=int(not active and start<vl)
  encodings.add((code,form));types.add(typ&63);start=0
 command((code<<26)|(vm<<25)|(src<<20)|(imm<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar,bad=bad,record=dict(kind='basic',code=code,form=form,sew=bits,vl=vl,vstart=initial))
def whole(n,vd=8,src=16,vm=1,selector=None):
 global start,versions
 sel=n-1 if selector is None else selector;bad=bool(sel not in [0,1,3,7] or not vm or vd%n or src%n)
 bits=8<<(typ>>3&3);first=start*bits;old=tuple(regs);initial=start
 if bad:coverage['illegal']+=1
 else:
  if first<n*128 and vd!=src:
   for i in range(first,n*128,8):
    byte=old[src+i//128]>>(i%128)&255
    shift=i%128;row=vd+i//128;regs[row]=(regs[row]&~(255<<shift))|(byte<<shift)
   versions^=((1<<n)-1)<<vd
  coverage['whole']+=1;coverage['zero_vl_move']+=int(vl==0);coverage['vill_move']+=int(typ>>63!=0);coverage['restart_move']+=int(start!=0);coverage['self_move']+=int(vd==src)
  coverage['whole_partial_byte_group']+=int(0<first<n*128 and first%128!=0)
  encodings.add((0x27,sel));start=0
 command((0x27<<26)|(vm<<25)|(src<<20)|(sel<<15)|(3<<12)|(vd<<7)|0x57,bad=bad,record=dict(kind='whole',n=n,sew=bits,vstart=initial,vl=vl))
def wmac(code,form,s,m=0,vm=1,vd=8,src=16,other=24):
 global start,versions
 bits=8<<s;wide=2*bits;old=tuple(regs);mask=(1<<bits)-1;scalar=0x80000000ffffffff
 for i in range(start,vl):
  if not vm and not (old[0]>>i&1):continue
  x=element(old,src,i,bits);y=element(old,other,i,bits) if form==2 else scalar&mask;d=element(old,vd,i,wide)
  if code in [0x3d,0x3e] and x>>(bits-1):x-=1<<bits
  if code in [0x3d,0x3f] and y>>(bits-1):y-=1<<bits
  put(vd,i,wide,x*y+d)
 if start<vl:versions^=((1<<(2<<m))-1)<<vd
 start=0;coverage['wmac']+=1;encodings.add((code,form))
 command((code<<26)|(vm<<25)|(src<<20)|(other<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar)
def cancel(inst,delay=0,held=False):
 lines.append(f"cancel(32'h{inst:x},{delay},{int(held)});");check();coverage['flush']+=1
for r in range(32):ctx(r,True)
for csr,value in [(9,1),(10,2)]+([(1,21),(2,3)] if fp else []):command((csr<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,writes=1,check_state=False)
seed();whole(1);basic(3,4) # vill bypass only for whole move
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for s,m in ([(s,0) for s in range(4)] if args.compact else all_types):
 config(s,m,2 if args.compact else 128);seed(s)
 for code in [3,0x1e,0x1f]:
  for form in [3,4]:
   for imm in ([31] if args.compact else range(32) if form==3 else [0,1,15,16,31]):
    basic(code,form,imm=imm,scalar=[0,M64,1<<63,1<<32,0x80000001][imm%5])
   restart(1);basic(code,form,vm=0,vd=0 if code!=3 else 8)
   if not args.compact:
    basic(code,form,vd=16);basic(code,form,src=0,vm=0)
    if m in [1,2,3]:basic(code,form,src=17);basic(code,form,vd=17)
 if not args.compact:
  regs[0]=0;ctx(0,True);basic(3,4,vm=0);basic(0x1f,3,vm=0)
  config(s,m,0);basic(3,4);basic(0x1e,3);basic(0x1f,4)
for s in range(4):
 for n in [1,2,4,8]:
  config(s,7 if not args.compact and s<=2 else 0,0);seed(s)
  for value in ([1] if args.compact else sorted({0,1,(16>>s)-1,16>>s,n*(16>>s)-1,min(127,n*(16>>s)),127})):
   restart(value);whole(n,vd=32-n,src=0)
  whole(n,vd=8,src=8)
  whole(n,vm=0)
  if n>1:whole(n,vd=9);whole(n,src=17)
  if not args.compact:
   for sel in [2,4,5,6,8,15,31]:whole(n,selector=sel)
  config(s,0,1);whole(n)
# vill must not disable whole moves, including restarted whole group copies.
vill();seed()
for n in [1,2,4,8]:restart(1);whole(n)
for s in range(3):
 config(s,0,2);seed(s)
 for code in [0x3c,0x3d,0x3e,0x3f]:
  for form in [2,6]:
   if code==0x3e and form==2:continue
   wmac(code,form,s)
# Wide destination crossing and masked restart in the highest eight-register group.
config(2,2,10);seed(2);restart(1);wmac(0x3f,2,2,m=2,vm=0,vd=24,src=8,other=16)
config(0,0,4);seed()
for inst in [(0x27<<26)|(1<<25)|(16<<20)|(7<<15)|(3<<12)|(8<<7)|0x57,(3<<26)|(1<<25)|(16<<20)|(4<<12)|(8<<7)|0x57,(0x1e<<26)|(1<<25)|(16<<20)|(3<<12)|(8<<7)|0x57,(0x3f<<26)|(1<<25)|(16<<20)|(24<<15)|(2<<12)|(8<<7)|0x57]:
 for delay in ([12] if args.compact else [0,1,2,5,8,12,16,20,24,32,40,55,80,120]):cancel(inst,delay)
 cancel(inst,held=True)
# Decode transitions: move after masked compare and MAC, then arithmetic/reduction tests run separately.
whole(8);basic(3,4);basic(0x1e,3);whole(2);wmac(0x3d,6,0);whole(1)
for code in [3,0x1e,0x1f]:basic(code,0)
lines+=['$display("PASS m36-integer commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
assert all(v for k,v in coverage.items() if k!='all_masked' or not args.compact),coverage
assert len(encodings)==17
result=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),encodings=sorted(encodings),performance=bench,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS m36-integer')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
