#!/usr/bin/env python3
"""RVV single-width multiply-add: immutable three-source snapshots and Python modular arithmetic."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/integer-mac';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x354d4143);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"integer-mac premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"integer-mac stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
CODES={0x29:'vmadd',0x2b:'vnmsub',0x2d:'vmacc',0x2f:'vnmsac'}
coverage={k:0 for k in [*CODES.values(),'vv','vx','illegal','misaligned','vill','bad_opcode','reserved_encoding','dest_vs2','dest_vs1','all_alias','same_sources','fraction_group','masked_source_v0','masked_vd0','zero_vl','restart','restart_active','nop_start','masked','all_masked','source_v0','dest_v0','cross_register','overflow','subtract_wrap','scalar_truncation','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"integer-mac state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"integer-mac FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x35aa<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
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
 bits=8<<(typ>>3&3);m=typ&7
 return bits,1<<m if m<4 else 1

def execute(code,form,vd=8,src=16,other=24,vm=1,scalar=0,record=False,opcode=0x57):
 global start,versions
 bits,count=geometry();mask=(1<<bits)-1
 misaligned=vd%count!=0 or src%count!=0 or form==2 and other%count!=0
 bad=bool(typ>>63 or code not in CODES or form not in [2,6] or opcode!=0x57 or misaligned or not vm and (vd==0 or src==0 or form==2 and other==0))
 inst=(code<<26)|(vm<<25)|(src<<20)|(other<<15)|(form<<12)|(vd<<7)|opcode
 initial_start=start
 if bad:
  coverage['illegal']+=1;coverage['misaligned']+=int(misaligned);coverage['vill']+=int(typ>>63!=0)
  coverage['bad_opcode']+=int(opcode!=0x57);coverage['reserved_encoding']+=int(code not in CODES)
  coverage['masked_source_v0']+=int(not vm and (src==0 or form==2 and other==0));coverage['masked_vd0']+=int(not vm and vd==0)
 else:
  # All operands, including old vd, are read from an immutable architectural
  # snapshot. The formulas below follow the spec, independently of RTL states.
  old=tuple(regs)
  def element(base,i):return old[base+i*bits//128]>>(i*bits%128)&mask
  active=[i for i in range(start,vl) if vm or old[0]>>i&1]
  for i in active:
   x=element(src,i);y=element(other,i) if form==2 else scalar&mask;d=element(vd,i)
   if code==0x29:mathematical=y*d+x
   elif code==0x2b:mathematical=x-y*d
   elif code==0x2d:mathematical=y*x+d
   else:mathematical=d-y*x
   value=mathematical&mask;row=vd+i*bits//128;offset=i*bits%128
   regs[row]=(regs[row]&~(mask<<offset))|(value<<offset)
   coverage['cross_register']+=int(i*bits>=128);coverage['overflow']+=int(mathematical>mask)
   coverage['subtract_wrap']+=int(mathematical<0)
  if start<vl:versions^=((1<<count)-1)<<vd
  coverage[CODES[code]]+=1;coverage['vv' if form==2 else 'vx']+=1
  coverage['dest_vs2']+=int(vd==src);coverage['dest_vs1']+=int(form==2 and vd==other)
  coverage['all_alias']+=int(form==2 and vd==src==other);coverage['same_sources']+=int(form==2 and src==other)
  coverage['fraction_group']+=int(typ&4!=0);coverage['scalar_truncation']+=int(form==6 and scalar>mask)
  coverage['zero_vl']+=int(vl==0);coverage['restart']+=int(start!=0);coverage['restart_active']+=int(0<start<vl)
  coverage['nop_start']+=int(start>=vl and vl!=0);coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl>start)
  coverage['source_v0']+=int(src==0);coverage['dest_v0']+=int(vd==0);seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=scalar,bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,code=code,form=form,vl=vl,vm=vm,vtype=typ&63,vstart=initial_start))
  lines.append(f'$display("MACPERF {ident} %0d",cycles-begun);end')
 checkregs()

def seed(pattern=0):
 bits,count=geometry();mask=(1<<bits)-1
 for r in range(32):regs[r]=rng.getrandbits(128)
 for base in [8,16,24]:
  values=[0,1,(1<<(bits-1))-1,1<<(bits-1),mask,2,0x55,0xaa]
  for i in range(maximum):
   row=base+i*bits//128;offset=i*bits%128
   value=values[(i+base//8)%8] if pattern%2==0 else rng.getrandbits(bits)
   regs[row]=(regs[row]&~(mask<<offset))|((value&mask)<<offset)
 regs[0]=0 if pattern==3 else rng.getrandbits(128)
 for r in range(32):ctx(r,True)

cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(0x2d,6)
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
types=[(0,0),(2,0),(3,0),(0,5),(0,3)] if args.smoke else all_types
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
 for code in CODES:
  for form in [2,6]:
   for scenario in ([0,2] if args.smoke else range(7)):
    config(s,m,[mx,0,max(1,mx-1),mx,1,mx,mx][scenario]);seed(pattern=scenario)
    if scenario==4:setstart(127)
    if scenario==5:setstart(max(1,mx//2))
    execute(code,form,vm=int(scenario not in [2,3]),scalar=M64,record=scenario==0)
   # Every alias reads committed old operands, including all-three-equal.
   for alias in ([0,2] if args.smoke else range(5)):
    config(s,m,mx);seed(pattern=alias)
    vd,src,other=[(16,16,24),(24,16,24),(16,16,16),(8,16,16),(24,24,16)][alias]
    execute(code,form,vd=vd,src=src,other=other,scalar=0x8000000000000001,vm=alias%2)
   for length in ([0] if args.smoke else [0,mx]):
    config(s,m,length)
    execute(code,form,vd=0,vm=0);execute(code,form,src=0,vm=0)
    if form==2:execute(code,form,other=0,vm=0)
    if m in [1,2,3]:
     execute(code,form,vd=9);execute(code,form,src=17)
     if form==2:execute(code,form,other=25)
# Boundary register groups, scalar truncation, restart and fractional tails.
for s,m in ([(0,2),(3,0)] if args.smoke else [(s,m) for s in range(4) for m in [0,3]]+[(0,5),(1,6),(2,7)]):
 config(s,m,128);bits,count=geometry()
 for code in CODES:
  seed()
  for scalar in ([0,M64] if args.smoke else [0,1,(1<<bits)-1,1<<(bits-1),1<<32,1<<63,M64]):execute(code,6,vd=32-count,scalar=scalar)
  seed();setstart(1);execute(code,2,vd=32-count,record=True)
  seed();execute(code,2,vd=24,other=24)
config(0,0,16);seed(pattern=3);execute(0x2d,2,vm=0)
seed();execute(0x29,6,src=0,scalar=M64);execute(0x2b,6,vd=0,scalar=M64)
seed();execute(0x2f,2,other=16)
setstart(127);execute(0x29,6,scalar=M64)
config(0,0,0);execute(0x2d,2)
for code in [0x28,0x2a,0x2c,0x2e]:
 for form in [2,6]:execute(code,form)
execute(0x2d,2,opcode=0x53)
# Interrupt across RAM reads, multiply partials, ALU launch/return, candidate
# writes and held completion. Ready+flush must cancel, never publish.
for code in CODES:
 for form in [2,6]:
  config(3,1,4);seed();inst=(code<<26)|(1<<25)|(16<<20)|(24<<15)|(form<<12)|(16<<7)|0x57
  for delay in ([0,20,115,130,260] if args.smoke else [0,2,*range(8,35),*range(105,135),180,250,350,450]):
   lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
  lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
  execute(code,form,vd=16,scalar=M64,record=True)
lines+=['$display("PASS integer-mac commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
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
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('MACPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values()),coverage
result=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS integer-mac')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
