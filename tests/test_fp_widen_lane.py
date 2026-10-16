#!/usr/bin/env python3
"""Mixed FP32/FP64 add lane against SoftFloat conversion plus binary64 add."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from reference_fp import Reference
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-widen-lane';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true');args=p.parse_args();assert not args.mapped or args.smoke
ref=Reference();rng=random.Random(0x303027);rows=[];lines=[HEADER.replace('repeat(400)','repeat(50)')]
# Independent known-answer checks exercise this wrapper's new path itself.
anchors=[(0x3f800000,0x3ff0000000000000,0,0x4000000000000000,0),
 (1,0,0,0x36a0000000000000,0),(0x80000000,0x8000000000000000,0,0x8000000000000000,0),
 (0x7f800001,0,0,0x7ff8000000000000,16),(0x7f800000,0xfff0000000000000,0,0x7ff8000000000000,16),
 (0x3f800000,0x4340000000000000,0,0x4340000000000000,1),
 (0x3f800000,0x4340000000000000,3,0x4340000000000001,1)]
for a,b,rm,value,flags in anchors:assert ref(27,True,rm,a,b)==(value,flags)
def add(d,rm,a,b,c=0):
 legal=d and rm<=4;value,flags=ref(27,True,rm,a,b) if legal else (0,0)
 i=len(rows);rows.append((d,27,rm,a,b,c,value,flags,int(not legal)))
 lines.append(f"run(1'b{int(d)},27,{rm},64'h{a:x},64'h{b:x},64'h{c:x},8'd{i%256},{rng.randrange(6)});")
values=[0,0x80000000,1,0x80000001,0x7fffff,0x800000,0x3f800000,0xbf800000,0x7f7fffff,0x7f800000,0xff800000,0x7f800001,0x7fc00123]
seeds=[0,0x8000000000000000,1,0x8000000000000001,0x3ff0000000000000,0xbff0000000000000,0x4340000000000000,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0x7ff8000000000123]
for rm in ([0,3] if args.smoke else range(5)):
 for i,a in enumerate(values):
  for b in (seeds[::4] if args.smoke else seeds):add(True,rm,(rng.getrandbits(32)<<32)|a,b,rng.getrandbits(64))
 for _ in range(4 if args.smoke else 100):add(True,rm,rng.getrandbits(64),rng.getrandbits(64),rng.getrandbits(64))
for rm in range(8):add(False,rm,0x3f800000,0x3ff0000000000000)
for rm in [5,6,7]:add(True,rm,0x3f800000,0x3ff0000000000000)
cancels=0
for delay in ([0,2,8,18,30] if args.smoke else range(40)):
 lines.append(f'cancel(27,{delay},0,0);');cancels+=1
lines+=['cancel(27,0,1,0);','cancel(27,2,0,1);'];cancels+=2
add(True,0,0x3f800000,0x3ff0000000000000)
lines.append('$display("PASS fp-widen-lane vectors=%0d cancels=%0d cycles=%0d",n,cancels,cycles);$finish;end endmodule')
label='mapped' if args.mapped else 'smoke' if args.smoke else 'rtl';tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/('build/synth/FloatingPointLane/mapped.v' if args.mapped else 'build/rtl/FloatingPointLane.sv')
files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
latency=check([s for s in run.stdout.splitlines() if s.startswith('F ')],rows)
d=dict(status='PASS',vectors=len(rows),flush_reset_cases=cancels,extra_reference_anchors=len(anchors),base_reference_anchors=ref.anchors,latency=latency,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS fp-widen-lane')),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/fp_reference.c',ROOT/'tests/reference_fp.py',ROOT/'tests/test_fp_lane.py',ROOT/'src/main/scala/vpu/FloatingPointLane.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
