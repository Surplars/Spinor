#!/usr/bin/env python3
"""Independent width-aware SoftFloat conversion checks; held output and cancellation."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from reference_fp_resize import ResizeReference
from reference_fp import Reference
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-resize-lane';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--lane',action='store_true');a=p.parse_args();assert not a.mapped or a.compact
ref=ResizeReference();rng=random.Random(0x4150494e);rows=[];counts={}
top='FloatingPointLaneResize' if a.lane else 'FloatingPointConvertResize';port='conversionWidths' if a.lane else 'io_widthMode'
h=HEADER.replace('FloatingPointLane dut',f'reg [2:0] {port}=0;'+('reg [1:0] narrowOperands=0;' if a.lane else '')+top+' dut')
h=h.replace('FloatingPointConvertResize dut','reg cancelPrecision=0;FloatingPointConvertResize dut') if not a.lane else h.replace('FloatingPointLaneResize dut','reg cancelPrecision=0;FloatingPointLaneResize dut')
h=h.replace("offer(1'b1,op,0,","offer(cancelPrecision,op,0,").replace('repeat(400)','repeat(100)')
h=h.replace('start=cycles;offer(d,op,rm,a,b,c,tag);',f'start=cycles;offer(d,op,rm,a,b,c,tag);{port}=~{port};')
lines=[h];ops=[21,22,23,24,25,26,28,29]
def legal(m,d,op,rm):
 width=(m==0 and op in range(21,27) or m==1 and d and op!=29 or m==2 and not d or m==5 and not d and op in [23,24] or m==6 and not d and op in [21,22,25,26])
 return width and (rm<=4 or op in [25,26,29])
def add(m,d,op,rm,x):
 ok=legal(m,d,op,rm);v,f=ref(op,m,d,rm,x) if ok else (0,0);i=len(rows);rows.append((d,op,rm,x,0,0,v,f,int(not ok)));counts[str(m)]=counts.get(str(m),0)+1
 lines.append(f"{port}={m};run({int(d)},{op},{rm},64'h{x:x},0,0,8'd{i%256},{rng.randrange(5)});")
edges=[0,1,0x80000000,0x8000000000000000,0x3f800000,0xbf800000,0x7f800000,0x7f800001,0x7fc12345,0x3ff0000000000000,0x3ff0000010000000,0xbff0000010000000,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fefffffffffffff,0x0010000000000000,0x36a0000000000000,0x3690000000000000,0x47efffffe0000000,0x4f000000,0xcf000000,0x4f800000,0x47000000,0xc7000000,0x477fff00,0x10000,0xffff,0xffffffff,0x7fffffff,0x7fffffffffffffff,0xffffffffffffffff]
for k in [15,16,24,31,32,53,63]:
 for delta in [-1,0,1]:edges.append(((1<<k)+delta)&((1<<64)-1))
for m in [0,1,2,5,6]:
 for d in ([False,True] if m==0 else [m==1]):
  for op in ops:
   for rm in ([0,3,7] if a.compact else range(8)):
    for x in edges[::5] if a.compact else edges:add(m,d,op,rm,x)
    for _ in range(1 if a.compact else 30):add(m,d,op,rm,rng.getrandbits(64))
for m in [3,4,7]:
 for op in ops:add(m,False,op,0,0)
cancels=0
for m,d,op in [(1,True,21),(1,True,24),(1,True,28),(2,False,28),(2,False,29),(5,False,24),(6,False,22)]:
 for delay in ([0,3,10,20] if a.compact else range(80)):
  lines.append(f'{port}={m};cancelPrecision={int(d)};cancel({op},{delay},0,0);');cancels+=1
 for reply,reset in [(1,0),(0,1),(1,1)]:lines.append(f'{port}={m};cancelPrecision={int(d)};cancel({op},0,{reply},{reset});');cancels+=1
add(2,False,29,0,0x3ff0000010000000)
lines.append('$display("PASS fp-resize vectors=%0d cancels=%0d cycles=%0d",n,cancels,cycles);$finish;end endmodule')
label=top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/(f'build/synth/{top}/mapped.v' if a.mapped else f'build/rtl/{top}.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
lat=check([x for x in r.stdout.splitlines() if x.startswith('F ')],rows)
files=[rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp_resize.py',ROOT/'tests/fp_resize_reference.c',ROOT/'tests/test_fp_lane.py',ROOT/'src/main/scala/vpu/execute/fp/FloatingPointConvertResize.scala',ROOT/'src/main/scala/vpu/execute/fp/StagedFloatToInt.scala',ROOT/'src/main/scala/vpu/execute/fp/FloatingPointLane.scala']
d=dict(status='PASS',vectors=len(rows),width_counts=counts,reference_anchors=ref.anchors,flush_cases=cancels,latency=lat,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS fp-resize')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
