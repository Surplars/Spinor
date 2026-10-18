#!/usr/bin/env python3
"""Mixed-width FP lane: independent SoftFloat conversion + binary64 arithmetic."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from reference_fp import Reference
from reference_fp_widen import WideReference
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-wide-arithmetic-lane';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--resize',action='store_true');p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args();assert not a.mapped or a.compact
wide=WideReference();native=Reference();rng=random.Random(0x4050494e)
h=HEADER.replace('FloatingPointLane dut','reg [1:0] narrowOperands=0;FloatingPointLaneWiden dut').replace('repeat(400)','repeat(50)').replace('start=cycles;offer(d,op,rm,a,b,c,tag);','start=cycles;offer(d,op,rm,a,b,c,tag);narrowOperands=~narrowOperands;')
if a.resize:h=h.replace('FloatingPointLaneWiden dut','reg [2:0] conversionWidths=0;FloatingPointLaneResize dut')
lines=[h];rows=[];widthCounts={}
def add(widths,op,rm,x,y,z=0,d=True):
 legal=rm<=4 and ((widths==0 and op<=27 and (op!=27 or d)) or (d and (widths==2 and op in [0,1] or widths==3 and op in [0,1,2,5,6,7,8])))
 if widths==0 and op in [25,26]:legal=True
 value,flags=(native(op,d,rm,x,y,z) if widths==0 else wide(op,widths,rm,x,y,z)) if legal else (0,0)
 i=len(rows);rows.append((d,op,rm,x,y,z,value,flags,int(not legal)));widthCounts[str(widths)]=widthCounts.get(str(widths),0)+1
 lines.append(f"narrowOperands={widths};run({int(d)},{op},{rm},64'h{x:x},64'h{y:x},64'h{z:x},8'd{i%256},{rng.randrange(5)});")
values=[0,0x80000000,1,0x80000001,0x7fffff,0x800000,0x3f800000,0x3f800001,0x3f7ffffe,0xbf800000,0x7f7fffff,0x7f800000,0xff800000,0x7f800001,0x7fc12345]
wides=[0,0x8000000000000000,1,0x3ff0000000000000,0xbff0000000000000,0x4340000000000000,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0x7ff8000000000123]
for widths,ops in [(2,[0,1]),(3,[0,1,2,5,6,7,8])]:
 for op in ops:
  for rm in ([0,3] if a.compact else range(5)):
   xs=wides if widths==2 else values
   for j,x in enumerate(xs[::3] if a.compact else xs):
    bs=values[::5] if a.compact else values
    for k,y in enumerate(bs):add(widths,op,rm,x,y,wides[(j*3+k+rm)%len(wides)])
   for _ in range(2 if a.compact else 80):add(widths,op,rm,rng.getrandbits(64),rng.getrandbits(64),rng.getrandbits(64))
# Compatibility paths: same-width conversions and existing mixed reduction add.
for op in [21,22,23,24,25,26,27]:
 for d in [False,True]:
  for rm in ([0] if a.compact else range(8)):
   for v in [0,0x7ff0000000000001,0x7fffffffffffffff,0xffffffffffffffff]:add(0,op,rm,v,0x3ff0000000000000,d=d)
for widths in [1,2,3]:
 for op in [0,1,2,3,4,5,8,21,27,30]:
  for rm in [0,5,7]:add(widths,op,rm,0x3f800000,0x3f800000,d=False)
for widths in [1,2,3]:
 for op in [0,2,3,5,27,31]:
  for rm in [0,5,7]:add(widths,op,rm,0x3f800000,0x3f800000)
cancels=0
for widths in [2,3]:
 for op in ([0] if widths==2 else [0,2,5,6,7,8]):
  for delay in ([0,3,12,30] if a.compact else range(40)):
   lines.append(f'narrowOperands={widths};cancel({op},{delay},0,0);');cancels+=1
  lines.append(f'narrowOperands={widths};cancel({op},0,1,0);');cancels+=1
add(3,5,0,0x3f800001,0x3f7ffffe,0xbff0000000000000)
lines.append('$display("PASS fp-wide-arithmetic vectors=%0d cancels=%0d cycles=%0d",n,cancels,cycles);$finish;end endmodule')
label=('resize-' if a.resize else '')+('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/('build/synth/FloatingPointLaneWiden/mapped.v' if a.mapped else 'build/rtl/FloatingPointLaneWiden.sv')
if a.resize:rtl=ROOT/('build/synth/FloatingPointLaneResize/mapped.v' if a.mapped else 'build/rtl/FloatingPointLaneResize.sv')
files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
latency=check([x for x in run.stdout.splitlines() if x.startswith('F ')],rows)
r=dict(status='PASS',vectors=len(rows),width_counts=widthCounts,flush_cases=cancels,reference_anchors=wide.anchors+native.anchors,latency=latency,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS fp-wide-arithmetic')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp.py',ROOT/'tests/reference_fp_widen.py',ROOT/'tests/fp_widen_reference.c',ROOT/'tests/test_fp_lane.py',ROOT/'src/main/scala/vpu/FloatingPointLane.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(r,indent=2)+'\n');print(r['summary'])
