#!/usr/bin/env python3
"""All IEEE encodings: direct fclass equals pinned HardFloat recode/classify."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/classify-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True)
rtl=OUT/'ClassifyProof.sv'
with (OUT/'generate.log').open('w') as log:
    subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateClassifyProof',str(rtl)],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
script=OUT/'proof.ys'
script.write_text(f'read_verilog -sv {rtl}\nprep -top ClassifyProof -flatten\nsat -verify -prove io_mismatch 0 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:
    subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(script)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[ROOT/'scripts/prove_classify.py',ROOT/'src/main/scala/vpu/FloatingPointLane.scala',ROOT/'src/main/scala/vpu/GenerateClassifyProof.scala',rtl,script]
result.write_text(json.dumps(dict(status='PASS',scope='ALL_FP32_AND_FP64_ENCODINGS_VS_HARDFLOAT_CLASSIFY',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2)+'\n')
print('PASS all-pattern FP32/FP64 IEEE classification')
