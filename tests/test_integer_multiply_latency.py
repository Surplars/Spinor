#!/usr/bin/env python3
"""Measure accepting-edge-to-visible-result latency using the numerical test cases."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
s=(OUT/'integer-multiply-tb.sv').read_text().replace('held=io_out_bits_data;',
 '$display("LAT %0d %0d %0d",sew,op,cycles-start);held=io_out_bits_data;')
tb=OUT/'integer-multiply-latency-tb.sv';tb.write_text(s);exe=OUT/'integer-multiply-latency'
with (OUT/'integer-multiply-latency.compile.log').open('w') as log:
 subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb','-o',str(exe),str(tb),str(ROOT/'build/rtl/IntegerMultiply.sv')],stdout=log,stderr=log,check=True)
run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True,check=True)
result={}
for line in run.stdout.splitlines():
 if line.startswith('LAT '):
  _,sew,op,cycles=line.split();result.setdefault(sew+':'+op,set()).add(int(cycles))
result={k:sorted(v) for k,v in result.items()}
assert len(result)==16
for key,value in result.items():
 sew,op=map(int,key.split(':'));assert value==[[7,7,25,97][sew]+(0 if op==20 else 4)],(key,value)
(OUT/'integer-multiply-latency.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS multiplier accepting-edge latency, all 16 SEW/operation combinations')
