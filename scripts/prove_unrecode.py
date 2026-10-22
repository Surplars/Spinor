#!/usr/bin/env python3
"""All-bit enabled FP32/64 decoder equivalence, four bounded time steps."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/unrecode-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True);rtl=OUT/'UnrecodeProof.sv'
with (OUT/'generate.log').open('w') as log:
 subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateUnrecodeProof',str(rtl)],cwd=ROOT,stdout=log,stderr=log,check=True)
ys=OUT/'proof.ys';ys.write_text(f'read_verilog -sv {rtl}\nprep -top UnrecodeProof -flatten\nsat -seq 4 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove io_mismatch 0\n')
with (OUT/'proof.log').open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(ys)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[Path(__file__).resolve(),ROOT/'src/main/scala/vpu/generate/proof/GenerateUnrecodeProof.scala',ROOT/'src/main/scala/vpu/execute/fp/StagedIeeeUnrecode.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/fNFromRecFN.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/rawFloatFromRecFN.scala',rtl,ys]
d=dict(status='PASS',scope='BOUNDED_4_STEPS_ALL_RECODED_BITS_AND_CAPTURE_HOLD_FP32_FP64_NOT_FULL_LANE_PROOF',
 input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS staged IEEE decoder equivalence, both widths, all bits/captures/holds')
