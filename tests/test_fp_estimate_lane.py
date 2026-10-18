#!/usr/bin/env python3
"""Independent estimate bit/flag oracle; exponent/bin boundaries, flush and backpressure."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
from reference_fp_estimate import estimate,ANCHORS,nearest_sqrt
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-estimate-lane';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args();assert not a.mapped or a.compact
rng=random.Random(0x42e571);rows=[];lines=[HEADER.replace('FloatingPointLane dut','reg cancelPrecision=1;reg [63:0] cancelSource=0;FloatingPointEstimate dut').replace("offer(1'b1,op,0,64'h3ff0000000000001,","offer(cancelPrecision,op,0,cancelSource,").replace('repeat(400)','repeat(30)').replace('2000000','10000000').replace('start=cycles;offer(d,op,rm,a,b,c,tag);','start=cycles;offer(d,op,rm,a,b,c,tag);io_in_bits_double=~d;io_in_bits_rounding=~rm;io_in_bits_op=~op;')]
def add(d,op,rm,x):
 legal=op==31 or op==30 and rm<=4
 y,f=estimate(op,d,rm,x) if legal else (0,0);i=len(rows);rows.append((d,op,rm,x,0,0,y,f,int(not legal)))
 lines.append(f"run({int(d)},{op},{rm},64'h{x:x},0,0,8'd{i%256},{rng.randrange(4)});")
# Cross-check all normative table entries without using the RTL tables as oracle.
text=(ROOT/'docs/references/m42-estimates-v1.0.txt').read_text()
for name in ['vfrec7','vfrsqrt7']:
 part=text.split('.'+name+'.v common-case lookup table contents')[1].split('|===')[1]
 table=[int(v) for _,v in re.findall(r'^\|\s*(\d+)\s*\|\s*(\d+)\s*$',part,re.M)]
 expected=[(65536+(257+2*i)//2)//(257+2*i)-128 for i in range(128)] if name=='vfrec7' else [nearest_sqrt(128**2*(256 if i<64 else 512),129+2*(i%64))-128 for i in range(128)]
 assert table==expected,(name,len(table))
for d in [False,True]:
 w,p,e=(64,52,11) if d else (32,23,8);maxE=(1<<e)-1;sign=1<<(w-1);mask=(1<<p)-1
 edges=[0,sign,1,sign|1,mask,mask+1,(maxE<<p)-1,maxE<<p,(maxE<<p)|sign,(maxE<<p)|1,(maxE<<p)|(1<<(p-1))]
 for k in range(0,p,7 if a.compact else 1):
  for v in [-1,0,1]:
   x=((1<<k)+v)&mask
   edges += [x,x|sign]
 for op in [30,31]:
  for rm in ([0,1,7] if a.compact else range(8)):
   for x in edges:add(d,op,rm,x)
  # All table bins, exponent parity and boundary exponents; both signs.
  for ex in [1,2,(1<<(e-1))-1,(1<<(e-1)),maxE-2,maxE-1]:
   for i in range(0,128,8 if a.compact else 1):
    for sg in [0,sign]:
     for tail in ([0] if a.compact else [0,1,(1<<(p-7))-1]):add(d,op,0,sg|(ex<<p)|(i<<(p-7))|tail)
  # Every biased exponent, sparse table bins, independently randomized low bits.
  for ex in range(0,maxE+1,31 if a.compact else 1):
   for i in ([0] if a.compact else [0,63,127]):add(d,op,rng.randrange(5),(rng.randrange(2)<<(w-1))|(ex<<p)|(i<<(p-7))|rng.getrandbits(p-7))
  for _ in range(8 if a.compact else 500):add(d,op,rng.randrange(8),rng.getrandbits(64))
 for op in [0,29]:add(d,op,0,0)
cancels=0
for d in [False,True]:
 for op in [30,31]:
  for x in ([1,0x3ff0000000000000,0x0008000000000000] if d else [1,0x3f800000,0x00400000]):
   for delay in ([0,2,4,8] if a.compact else range(22)):
    lines.append(f"cancelPrecision={int(d)};cancelSource=64'h{x:x};cancel({op},{delay},0,0);");cancels+=1
   for reply,reset in [(1,0),(0,1),(1,1)]:lines.append(f"cancelPrecision={int(d)};cancelSource=64'h{x:x};cancel({op},0,{reply},{reset});");cancels+=1
for op,d,rm,x,y,f in ANCHORS:add(d,op,rm,x)
lines.append('$display("PASS fp-estimate vectors=%0d cancels=%0d cycles=%0d",n,cancels,cycles);$finish;end endmodule')
label=('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/('build/synth/FloatingPointEstimate/mapped.v' if a.mapped else 'build/rtl/FloatingPointEstimate.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'];
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
trace=[x for x in r.stdout.splitlines() if x.startswith('F ')];lat=check(trace,rows)
for line,row in zip(trace,rows,strict=True):
 if not row[-1]:assert int(line.split()[-1])<=18,(row,line)
files=[rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp_estimate.py',ROOT/'tests/test_fp_lane.py',ROOT/'src/main/scala/vpu/FloatingPointEstimate.scala',ROOT/'docs/references/m42-estimates-v1.0.txt']
d=dict(status='PASS',vectors=len(rows),reference_anchors=len(ANCHORS),table_entries_independently_checked=256,flush_cases=cancels,latency=lat,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS fp-estimate')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
