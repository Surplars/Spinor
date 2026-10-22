#!/usr/bin/env python3
"""Frozen M41/current converter numerical equivalence and exact per-input cycle savings."""
import hashlib,json,random,subprocess
from pathlib import Path
from reference_fp_resize import ResizeReference
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/conversion-efficiency';OUT.mkdir(parents=True,exist_ok=True);rng=random.Random(0x4200);ref=ResizeReference()
rows=[];specs=[];lines=[HEADER.replace('FloatingPointLane dut','reg [2:0] io_widthMode=0;FloatingPointConvertResize dut').replace('2000000','10000000')]
for mode,d,bits in [(0,False,32),(0,True,64),(1,True,32),(2,False,64),(5,False,16)]:
 for op in [23,24]:
  values=[0,(1<<bits)-1]
  for k in range(bits):values += [((1<<k)+j)&((1<<bits)-1) for j in [-1,0,1]]
  values += [rng.getrandbits(64) for _ in range(100)]
  for rm in range(5):
   for x in values:
    y,f=ref(op,mode,d,rm,x);i=len(rows);rows.append((d,op,rm,x,0,0,y,f,0));masked=x&((1<<bits)-1)
    mag=((1<<bits)-masked) if op==24 and masked>>(bits-1) else masked
    clz=bits-mag.bit_length();saving=(64-mag.bit_length())-(clz//8+clz%8) if mag else 0
    specs.append(dict(mode=mode,bits=bits,op=op,x=x,rounding=rm,saving=saving))
    lines.append(f"io_widthMode={mode};run({int(d)},{op},{rm},64'h{x:x},0,0,8'd{i%256},0);")
lines.append('$display("PASS efficiency %0d",n);$finish;end endmodule');tb=OUT/'tb.sv';tb.write_text('\n'.join(lines));latencies={};inputs=[tb,Path(__file__).resolve(),ROOT/'tests/reference_fp_resize.py',ROOT/'tests/test_fp_lane.py',ROOT/'src/main/scala/vpu/execute/fp/FloatingPointConvertResize.scala']
for label,rtl in [('M41',ROOT/'archive/m41/rtl/FloatingPointConvertResize.sv'),('M42',ROOT/'build/rtl/FloatingPointConvertResize.sv')]:
 inputs.append(rtl)
 with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),str(tb),str(rtl)],stdout=log,stderr=log,check=True)
 p=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True,check=True);(OUT/(label+'.log')).write_text(p.stdout+p.stderr);trace=[x for x in p.stdout.splitlines() if x.startswith('F ')];check(trace,rows);latencies[label]=[int(x.split()[-1]) for x in trace]
for i,row in enumerate(specs):
 old,new=latencies['M41'][i],latencies['M42'][i];assert old-new==row['saving'],(row,old,new)
 row.update(old_cycles=old,new_cycles=new)
result=dict(status='PASS',cases=len(rows),specs=specs,maximum_saved_cycles=max(x['saving'] for x in specs),summary={str(bits):dict(old_min=min(x['old_cycles'] for x in specs if x['bits']==bits),old_max=max(x['old_cycles'] for x in specs if x['bits']==bits),new_min=min(x['new_cycles'] for x in specs if x['bits']==bits),new_max=max(x['new_cycles'] for x in specs if x['bits']==bits)) for bits in [16,32,64]},sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS efficiency',len(rows),'inputs',result['summary'])
