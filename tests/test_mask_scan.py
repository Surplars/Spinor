#!/usr/bin/env python3
"""Independent bit-list oracle for vcpop/vfirst, including GPR-zero and VL-zero."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/mask-scan';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--baseline',action='store_true',help='run the same oracle/benchmark on frozen M20 RTL')
p.add_argument('--top',default='RamVectorFp',choices=['RamVectorFp','RamVector','RamVector16']);args=p.parse_args()
assert not args.mapped or args.smoke
assert not args.baseline or (args.top=='RamVectorFp' and not args.mapped)
fp=args.top=='RamVectorFp';rng=random.Random(0x202020);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','3000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"early mask-scan commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard,1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];vl=0;typ=1<<63;start=0;case=0
coverage=dict(pop=0,first=0,illegal=0,zero_vl=0,masked=0,rd_zero=0,no_set=0,source_v0=0,unaligned=0,flush=0)
types_seen=set();bench=[]
def state():
 lines.append(f"if(io_versions!==0 || io_vstart!==7'd{start} || io_vxrm!==0 || io_vxsat!==0)$fatal(1,\"scan state {case}\");")
 if fp:lines.append('if(io_fflags!==0 || io_frm!==0)$fatal(1,"scan changed FP CSR");')
def cmd(inst,result=0,writes=0,bad=False,scalar=0,avl=0,stall=3):
 global case
 lines.append(f"command(32'h{inst:x},64'h{scalar:x},0,64'h{avl:x},80'h{(0xab20<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{stall},8'd{vl},64'h{typ:x});")
 case+=1;state()
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m|(rng.randrange(4)<<6);start=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def setstart(value):
 global start
 old=start;start=value;cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,result=old,writes=1,scalar=value)
def scan(first,rd,src,vm,bad=False,record=False):
 global start
 active=[i for i in range(vl) if (regs[src]>>i)&1 and (vm or (regs[0]>>i)&1)]
 result=next(iter(active),-1) if first else len(active)
 if bad:coverage['illegal']+=1;result=0
 else:
  coverage['first' if first else 'pop']+=1;coverage['zero_vl']+=int(vl==0)
  coverage['masked']+=int(not vm);coverage['rd_zero']+=int(rd==0);coverage['no_set']+=int(not active)
  coverage['source_v0']+=int(src==0);coverage['unaligned']+=int(src%8!=0);types_seen.add(typ&63);start=0
 inst=(0x10<<26)|(vm<<25)|(src<<20)|((17 if first else 16)<<15)|(2<<12)|(rd<<7)|0x57
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,result=result,writes=int(rd!=0 and not bad),bad=bad,stall=0 if record else rng.randrange(6))
 if record:
  ident=len(bench);bench.append(dict(id=ident,op='vfirst' if first else 'vcpop',vl=vl,vm=vm,set_bits=len(active),first=next(iter(active),-1)))
  lines.append(f'$display("SCANPERF {ident} %0d",cycles-begun);end')
 for r in range(32):ctx(r)
for r in range(32):ctx(r,True)
scan(False,3,31,1,bad=True);scan(True,0,0,0,bad=True)
types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
if args.smoke:types=[(0,3),(3,3),(0,5),(2,7)]
for s,m in types:
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
 for first in [False,True]:
  for scenario in ([0,1,2,3,5] if args.smoke else range(8)):
   config(s,m,0 if scenario==1 else max(0,maximum-1) if scenario==7 else maximum)
   src=0 if scenario==5 else 31
   regs[src]=[M128,0,rng.getrandbits(128),1<<max(0,vl-1),1,0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,0,M128][scenario]
   if src!=0:regs[0]=[M128,0,0x55555555555555555555555555555555,M128,M128,0,0,M128][scenario];ctx(0,True)
   ctx(src,True);scan(first,0 if scenario&1 else 3,src,0 if scenario in [2,5,6] else 1,record=scenario==0)
  for length in [0,maximum]:
   config(s,m,length);setstart(127 if not length else 1);scan(first,3,31,1,bad=True)
# Every one-hot location (including masked-out hits) and partial final bytes.
for length in ([7,8,9,63,64,65,127,128] if args.smoke else [*range(1,18),63,64,65,*range(119,129)]):
 config(0,3,length)
 positions=range(128) if length==128 and not args.smoke else sorted({0,1,6,7,8,9,63,64,126,127,length-1,length})
 for bit in positions:
  if bit>127:continue
  regs[31]=1<<bit;regs[0]=M128 ^ (1<<bit);ctx(31,True);ctx(0,True)
  for first,vm in [(False,1),(True,1),(False,0),(True,0)]:scan(first,3,31,vm)
# Apples-to-apples latency rows, including a long first-hit search and no hit.
config(0,3,128)
for value in [0,M128,1,1<<7,1<<8,1<<63,1<<64,1<<127]:
 regs[31]=value;ctx(31,True)
 for first in [False,True]:scan(first,3,31,1,record=True)
# Small and sparse masked vectors expose fixed byte-pipeline overhead too.
for length in [1,2,7,8,9,128]:
 config(0,3,length);regs[31]=M128;ctx(31,True)
 for predicate in [0,1<<(length-1),M128]:
  regs[0]=predicate;ctx(0,True)
  for first in [False,True]:scan(first,3,31,0,record=True)
# Cancellation at every byte phase and completed reply, ready asserted on flush.
config(0,3,128);regs[31]=1<<127;regs[0]=M128;ctx(31,True);ctx(0,True)
for first in [False,True]:
 inst=(0x10<<26)|(1<<25)|(31<<20)|((17 if first else 16)<<15)|(2<<12)|(3<<7)|0x57
 for delay in [0,2,*range(5,17),40,70,200]:
  lines.append(f"cancel(32'h{inst:x},{delay},0);");state();coverage['flush']+=1
 lines.append(f"cancel(32'h{inst:x},0,1);");state();coverage['flush']+=1
 for r in range(32):ctx(r)
 scan(first,3,31,1)
lines+=['$display("PASS mask-scan commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl')
if args.baseline:label+='-m20-baseline'
tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl];extra=[]
if args.baseline:rtl=ROOT/'archive/m20/rtl/RamVectorFp.sv';files=[tb,rtl]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
elif not args.baseline:
 source=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(args.top+'.','tb.dut.'));files.append(f);extra=['-s',args.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('SCANPERF ')}
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values())
d=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(types_seen),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS mask-scan')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/('archive/m20/source/RamVector.scala' if args.baseline else 'src/main/scala/vpu/core/RamVector.scala')]})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['sha256','performance']},indent=2))
