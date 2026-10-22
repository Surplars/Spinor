#!/usr/bin/env python3
"""RVV mask/scalar oracle: Python bit sets and signed integers, no RTL decode reuse."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/mask-scalar';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin';M128=(1<<128)-1;M64=(1<<64)-1
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--baseline',action='store_true',help='run the same oracle/benchmark on frozen M20 RTL')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
assert not args.baseline or (args.top=='RamVectorFp' and not args.mapped)
fp=args.top=='RamVectorFp';rng=random.Random(0x190019)
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',
 'originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"architectural commit before acknowledgement");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard,1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1)
h=h.replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;vstart=0;case=0
flags=rounding=vxrm=vxsat=0
stats=dict(mask=0,scalar_read=0,scalar_write=0,illegal=0,flush=0,zero_vl=0,nonzero_start=0,start_at_or_past_vl=0,aliases=0,unaligned=0,rd_zero=0)
byop={n:0 for n in ['vmandn','vmand','vmor','vmxor','vmorn','vmnand','vmnor','vmxnor','vmv.x.s','vmv.s.x']};types_seen=set();bench=[]
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{vstart} || io_vxrm!==2'd{vxrm} || io_vxsat!==1'd{vxsat})$fatal(1,\"mask/scalar state case {case}\");")
 if fp:lines.append(f"if(io_fflags!==5'd{flags} || io_frm!==3'd{rounding})$fatal(1,\"mask/scalar FP state case {case}\");")
def cmd(inst,scalar=0,avl=0,value=0,writes=0,bad=False,stall=None):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{((0xf019<<64)|case):x},1'b{int(bad)},64'h{value&M64:x},1'b{writes},{rng.randrange(6) if stall is None else stall},8'd{vl},64'h{typ:x});")
 case+=1;state()
def config(s,m,length,policy=0):
 global vl,typ,vstart
 typ=(s<<3)|m|policy;maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(maximum,length);vstart=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,avl=length,value=vl,writes=1)
def csr(addr,value):
 global vstart,flags,rounding,vxrm,vxsat
 old={8:vstart,9:vxsat,10:vxrm,1:flags,2:rounding}[addr]
 if addr==8:vstart=value
 if addr==9:vxsat=value
 if addr==10:vxrm=value
 if addr==1:flags=value
 if addr==2:rounding=value
 cmd((addr<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,value=old,writes=1)
def checkregs():
 for r in range(32):ctx(r)
def operands(indices,scenario,w):
 for r in sorted(set(indices)):
  regs[r]=rng.getrandbits(128)
  if scenario==3:regs[r]=0
  elif scenario==4:regs[r]=M128
  elif scenario==5:regs[r]=sum(1<<i for i in range((r&1),128,2))
  elif scenario==6:regs[r]=(regs[r]&~((1<<w)-1))|(1<<(w-1))
  elif scenario==7:regs[r]=(regs[r]&~((1<<w)-1))|((1<<(w-1))-1)
  ctx(r,True)
def execute(op,vd,vs2,vs1,scalar=0,bad=False,vm=1,record=False):
 global versions,vstart
 maskop=op<8;read=op==8;name=list(byop)[op]
 f6=0x18+op if maskop else 0x10;f3=2 if maskop or read else 6
 inst=(f6<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(f3<<12)|(vd<<7)|0x57
 value=0;writes=0;oldstart=vstart;w=8<<((typ>>3)&3)
 if not bad:
  if maskop:
   # Independent per-bit truth table; never imports IntegerLane.golden.
   result=regs[vd]
   for bit in range(vstart,vl):
    a=(regs[vs2]>>bit)&1;b=(regs[vs1]>>bit)&1
    val=[a and not b,a and b,a or b,a!=b,a or not b,not(a and b),not(a or b),a==b][op]
    result=(result&~(1<<bit))|(int(val)<<bit)
   if vl>vstart:regs[vd]=result;versions^=1<<vd
   stats['mask']+=1;stats['aliases']+=int(vd in [vs2,vs1])
  elif read:
   value=regs[vs2]&((1<<w)-1)
   if value>>(w-1):value-=1<<w
   writes=int(vd!=0);stats['scalar_read']+=1;stats['rd_zero']+=int(vd==0)
  else:
   if vl>vstart:regs[vd]=(regs[vd]&~((1<<w)-1))|(scalar&((1<<w)-1));versions^=1<<vd
   stats['scalar_write']+=1
  stats['zero_vl']+=int(vl==0);stats['nonzero_start']+=int(vstart!=0);stats['start_at_or_past_vl']+=int(vstart>=vl)
  n=1<<(typ&7) if typ&7<4 else 1;stats['unaligned']+=int(any(r%n for r in [vd,vs2,vs1]))
  byop[name]+=1;types_seen.add(typ&63);vstart=0
 else:stats['illegal']+=1
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=scalar,value=value,writes=writes,bad=bad,stall=0 if record else None)
 if record:
  ident=len(bench);bench.append(dict(id=ident,op=name,vl=vl,vstart=oldstart,sew=w))
  lines.append(f'$display("MASKPERF {ident} %0d",cycles-begun);end')
 checkregs()
for r in range(32):ctx(r,True)
# vill must reject even scalar read at VL=0.
execute(8,3,31,0,bad=True);execute(0,0,31,3,bad=True);execute(9,31,0,7,bad=True)
csr(9,1);csr(10,2)
if fp:csr(1,21);csr(2,3)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));w=8<<s
 for op in range(10):
  for scenario in ([0,1,3,6] if args.smoke else range(8)):
   length=0 if scenario==1 else max(0,maximum-1) if scenario==7 else maximum
   config(s,m,length,rng.randrange(4)<<6)
   start={2:1,3:min(127,vl),4:127,5:min(127,max(1,vl//2)),6:min(127,max(0,vl-1))}.get(scenario,0)
   if start:csr(8,start)
   vd,vs2,vs1=[(7,31,3),(0,31,7),(31,31,3),(3,7,3),(0,0,0),(7,3,7),(31,3,7),(7,7,7)][scenario]
   if op==8:vs1=0
   if op==9:vs2=0
   operands([vd,vs2,vs1],scenario,w)
   scalar=rng.getrandbits(64) if scenario%2 else M64
   execute(op,vd,vs2,vs1,scalar=scalar,record=scenario==0)
  # Reserved masked variants must fail without touching vstart or any state.
  config(s,m,maximum);csr(8,1);execute(op,7,0 if op==9 else 31,0 if op==8 else 3,vm=0,bad=True)
 # Reserved fixed source fields for each scalar direction.
 config(s,m,maximum);execute(8,3,31,1,bad=True);execute(9,7,1,3,bad=True)
# Directed sign boundary and GPR-zero reads at VL=0 with nonzero vstart.
for s in range(4):
 config(s,3,0);csr(8,127);regs[31]=(1<<(8<<s))-1;ctx(31,True);execute(8,0,31,0)
# Exercise every intra-byte start/end offset, byte crossings and the final bit.
# Random prestart/tail data must survive; rotate all destination/source aliases.
lengths=[1,7,8,9,63,64,65,127,128] if args.smoke else [*range(1,18),63,64,65,*range(119,129)]
for op in range(8):
 for length in lengths:
  starts=sorted({0,1,7,8,max(0,length-1),length,127}) if not args.smoke else [max(0,length-1)]
  for initial in starts:
   config(0,3,length);csr(8,min(127,initial))
   vd,vs2,vs1=[(7,31,3),(0,0,3),(31,31,3),(3,31,3),(0,0,0)][(length+initial+op)%5]
   operands([vd,vs2,vs1],0,8);execute(op,vd,vs2,vs1,record=initial==0)
# Cancellation in each byte-engine phase and its staged candidate write.
config(0,3,128);csr(8,3)
inst=(0x1b<<26)|(1<<25)|(31<<20)|(3<<15)|(2<<12)|(7<<7)|0x57
for delay in range(5,24):
 lines.append(f"cancel(32'h{inst:08x},{delay},1'b0);");state();checkregs();stats['flush']+=1
# Cancel every instruction kind, including completed-but-uncommitted and private writes.
config(0,3,128);csr(8,3)
for op in range(10):
 inst=((0x18+op if op<8 else 0x10)<<26)|(1<<25)|((0 if op==9 else 31)<<20)|((0 if op==8 else 3)<<15)|((6 if op==9 else 2)<<12)|(7<<7)|0x57
 for delay in [0,2,6,12,40]:
  lines.append(f"cancel(32'h{inst:08x},{delay},1'b0);");state();checkregs();stats['flush']+=1
 lines.append(f"cancel(32'h{inst:08x},0,1'b1);");state();checkregs();stats['flush']+=1
# A real mixed program: write scalar, read it, build v0, then masked streaming add.
config(2,0,4);execute(9,8,0,1,scalar=0xfffffffd);execute(8,3,8,0)
regs[1]=0b1010;regs[2]=0b1100;ctx(1,True);ctx(2,True);execute(3,0,1,2)
before=regs.copy();dest=regs[24]
for i in range(vl):
 if (regs[0]>>i)&1:
  v=((before[8]>>(32*i))+(before[16]>>(32*i)))&0xffffffff
  dest=(dest&~(0xffffffff<<(32*i)))|(v<<(32*i))
regs[24]=dest;versions^=1<<24
cmd((8<<20)|(16<<15)|(24<<7)|0x57);checkregs()
lines+=['$display("PASS mask-scalar commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl')
if args.baseline:label+='-m20-baseline'
tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl];extra=[]
if args.baseline:rtl=ROOT/'archive/m20/rtl/RamVectorFp.sv';files=[tb,rtl]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
elif not args.baseline:
 module=args.top;source=ROOT/f'build/rtl/verification/assert/{module}_Verification_Assert.sv'
 if source.exists():
  monitor=OUT/(label+'-assert.sv');monitor.write_text(source.read_text().replace(module+'.','tb.dut.'));files.append(monitor);extra=['-s',module+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(BIN/'vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('MASKPERF ')}
assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(byop.values()) and all(stats.values())
result=dict(status='PASS',scope='MASK_LOGIC_AND_INTEGER_SCALAR_MOVES_NOT_FULL_RVV',top=args.top,mapped=args.mapped,commands=case,coverage=stats,by_operation=byop,types=sorted(types_seen),performance=bench,
 summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS mask-scalar')),
 sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/('archive/m20/source/RamVector.scala' if args.baseline else 'src/main/scala/vpu/core/RamVector.scala')]})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
