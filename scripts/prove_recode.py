#!/usr/bin/env python3
"""SAT proof of both exact IEEE recoders for all 64-bit input patterns."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/recode-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True)
rtl=OUT/'IeeeRecodeProof.sv'
subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateRecodeProof',str(rtl)],cwd=ROOT,check=True,stdout=(OUT/'generate.log').open('w'),stderr=subprocess.STDOUT)
script=OUT/'proof.ys';script.write_text(f'read_verilog -sv {rtl}\nprep -top IeeeRecodeProof -flatten\nsat -verify -prove io_mismatch 0 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(script)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[ROOT/'scripts/prove_recode.py',ROOT/'src/main/scala/vpu/IeeeRecode.scala',ROOT/'src/main/scala/vpu/GenerateRecodeProof.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/rawFloatFromFN.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/recFNFromFN.scala',rtl,script]
d=dict(status='PASS',scope='ALL_64_BIT_PATTERNS_COMBINATIONAL_FP32_AND_FP64_ENCODING_EQUIVALENCE; PIPELINE_SEQUENCING_CHECKED_SEPARATELY',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS all-pattern FP32/FP64 recode equivalence against pinned HardFloat')
