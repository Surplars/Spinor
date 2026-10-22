#!/usr/bin/env python3
"""SAT proof of all byte-prefix data, carry-in and selector combinations."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/mask-prefix-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True)
rtl=OUT/'MaskPrefixProof.sv'
subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateMaskPrefixProof',str(rtl)],cwd=ROOT,check=True,stdout=(OUT/'generate.log').open('w'),stderr=subprocess.STDOUT)
script=OUT/'proof.ys';script.write_text(f'read_verilog -sv {rtl}\nprep -top MaskPrefixProof -flatten\nsat -verify -prove io_mismatch 0 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(script)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[ROOT/'scripts/prove_mask_prefix.py',ROOT/'src/main/scala/vpu/execute/integer/MaskPrefixByte.scala',ROOT/'src/main/scala/vpu/generate/proof/GenerateMaskPrefixProof.scala',rtl,script]
d=dict(status='PASS',scope='ALL_2048_SOURCE_BYTE_SEEN_AND_SELECTOR_COMBINATIONS; LOCAL_COMBINATIONAL_PROOF; FSM_AND_RAM_COMMIT_CHECKED_IN_SIMULATION',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS all-pattern byte prefix equivalence against arithmetic first-bit oracle')
