#!/usr/bin/env python3
"""Independent global first-index oracle for RVV mask prefix instructions."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/mask-prefix';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x225522);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"prefix premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"prefix stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0
vxrm=vxsat=frm=flags=0;seen_types=set();bench=[]
coverage=dict(before=0,only=0,including=0,illegal=0,overlap=0,masked_vd0=0,nonzero_start=0,reserved=0,zero_vl=0,masked=0,all_masked=0,no_hit=0,source_v0=0,dest_v0=0,unaligned=0,flush=0)
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd{vxrm} || io_vxsat!==1'b{vxsat})$fatal(1,\"prefix state {case}\");")
 if fp:lines.append(f"if(io_frm!==3'd{frm} || io_fflags!==5'd{flags})$fatal(1,\"prefix FP state {case}\");")
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2255<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
 case+=1;state()
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def checkregs():
 for r in range(32):ctx(r)
def config(s,m,length,policy=0):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m|policy;start=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def csr(addr,value):
 global start,vxrm,vxsat,frm,flags
 old={8:start,9:vxsat,10:vxrm,1:flags,2:frm}[addr]
 if addr==8:start=value
 if addr==9:vxsat=value
 if addr==10:vxrm=value
 if addr==1:flags=value
 if addr==2:frm=value
 cmd((addr<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,result=old,writes=1)
def execute(mode,vd,src,vm,record=False,f3=2):
 global start,versions
 bad=bool(typ>>63 or start or vd==src or (not vm and vd==0) or mode not in [1,2,3] or f3!=2)
 active=[i for i in range(vl) if vm or (regs[0]>>i)&1]
 hits=[i for i in active if (regs[src]>>i)&1];first=min(hits) if hits else 128
 inst=(0x14<<26)|(vm<<25)|(src<<20)|(mode<<15)|(f3<<12)|(vd<<7)|0x57
 if bad:
  coverage['illegal']+=1;coverage['overlap']+=int(vd==src);coverage['masked_vd0']+=int(not vm and vd==0)
  coverage['nonzero_start']+=int(start!=0);coverage['reserved']+=int(mode not in [1,2,3] or f3!=2)
 else:
  value=regs[vd]
  for i in active:
   bit=int(i<first if mode==1 else i==first if mode==2 else i<=first)
   value=(value&~(1<<i))|(bit<<i)
  regs[vd]=value
  if vl:versions^=1<<vd
  coverage[{1:'before',2:'only',3:'including'}[mode]]+=1
  coverage['zero_vl']+=int(vl==0);coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl!=0)
  coverage['no_hit']+=int(not hits);coverage['source_v0']+=int(src==0);coverage['dest_v0']+=int(vd==0)
  group=1<<(typ&7) if typ&7<4 else 1;coverage['unaligned']+=int(vd%group!=0 or src%group!=0)
  seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,mode=mode,vl=vl,vm=vm,first=-1 if not hits else first))
  lines.append(f'$display("PREFIXPERF {ident} %0d",cycles-begun);end')
 checkregs()
for r in range(32):ctx(r,True)
for mode in [1,2,3]:execute(mode,7,31,1)
csr(9,1);csr(10,2)
if fp:csr(1,21);csr(2,3)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
 for mode in [1,2,3]:
  for scenario in ([0,1,3] if args.smoke else range(10)):
   config(s,m,0 if scenario==1 else maximum-1 if scenario==8 else maximum,rng.randrange(4)<<6)
   vd,src,vm=[(7,31,1),(31,7,0),(0,31,1),(7,0,0),(3,31,0),(7,31,0),(31,3,1),(3,7,1),(7,31,0),(31,7,1)][scenario]
   regs[0]=rng.getrandbits(128);regs[src]=rng.getrandbits(128);regs[vd]=rng.getrandbits(128)
   if scenario==0:regs[src]=0
   if scenario==2:regs[src]=M128
   if scenario==3:regs[src]=M128
   if scenario==4:regs[src]=1<<max(0,vl-1);regs[0]=M128
   if scenario==5:regs[src]=M128;regs[0]=0
   if scenario==6:regs[src]=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   if scenario==7:regs[src]=1<<min(127,vl)
   if scenario==8:regs[src]=(1<<127)|1;regs[0]=M128^1
   for r in sorted({0,src,vd}):ctx(r,True)
   execute(mode,vd,src,vm,record=scenario==0)
  # These restrictions apply even with no active elements or VL=0.
  for length in [0,maximum]:
   config(s,m,length);execute(mode,7,7,1);execute(mode,0,31,0)
   csr(8,1);execute(mode,7,31,1)
# Single-register sources/destinations ignore LMUL alignment. Cross each byte,
# all 128 source positions, masked-out earlier source bits and partial tail.
config(0,3,128)
for bit in ([0,7,8,63,64,127] if args.smoke else range(128)):
 for vm in [0,1]:
  regs[31]=1<<bit;regs[0]=M128 ^ ((1<<bit) if not vm else 0);ctx(31,True);ctx(0,True)
  for mode in [1,2,3]:execute(mode,7,31,vm)
for length in ([7,8,9,127] if args.smoke else [*range(1,18),63,64,65,127]):
 config(0,3,length)
 for mode in [1,2,3]:
  regs[31]=(1<<min(length,127))|1;regs[0]=M128^1;ctx(31,True);ctx(0,True)
  execute(mode,7,31,0)
# Decode must reject all other unary selectors rather than treating them as
# prefix operations. f3=1 is a reserved FP encoding at this f6.
config(0,3,128)
for mode in ([0,4,15,31] if args.smoke else [x for x in range(32) if x not in [1,2,3,16,17]]):execute(mode,7,31,1)
for mode in [1,2,3]:execute(mode,7,31,1,f3=1)
# Flush every byte phase, after a private write, and while completion is held.
config(0,3,128);regs[31]=1<<64;regs[0]=M128;ctx(31,True);ctx(0,True)
for mode in [1,2,3]:
 inst=(0x14<<26)|(1<<25)|(31<<20)|(mode<<15)|(2<<12)|(7<<7)|0x57
 for delay in ([0,2,8,10,12,20,75] if args.smoke else [0,2,*range(5,25),70,110]):
  lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
 execute(mode,7,31,1)
# Reuse the result as v0, consume via scan, then use another prefix opcode.
config(0,3,128);regs[31]=(1<<64)|1;ctx(31,True);execute(1,0,31,1)
cmd((0x10<<26)|(1<<25)|(16<<15)|(2<<12)|(3<<7)|0x57,result=0,writes=1)
execute(3,7,0,0)
# Long-vector latency rows with no hit, first byte and final byte.
for value in [0,1,1<<127]:
 regs[31]=value;ctx(31,True)
 for mode in [1,2,3]:execute(mode,7,31,1,record=True)
lines+=['$display("PASS mask-prefix commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('PREFIXPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values());assert len(seen_types)==(4 if args.smoke else 22)
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS mask-prefix')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/core/RamVector.scala',ROOT/'src/main/scala/vpu/execute/integer/MaskPrefixByte.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
