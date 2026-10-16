#!/usr/bin/env python3
"""SAT proof of production 32-bit conditional negation including carry out."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/divider-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True)
rtl=OUT/'DividerWordProof.sv'
subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateDividerProof',str(rtl)],cwd=ROOT,check=True,stdout=(OUT/'generate.log').open('w'),stderr=subprocess.STDOUT)
script=OUT/'proof.ys';script.write_text(f'read_verilog -sv {rtl}\nprep -top DividerWordProof -flatten\nsat -verify -prove io_mismatch 0 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(script)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[ROOT/'scripts/prove_divider_word.py',ROOT/'src/main/scala/vpu/IntegerDivide.scala',ROOT/'src/main/scala/vpu/StagedDivSqrt.scala',ROOT/'src/main/scala/vpu/StagedFloatToInt.scala',ROOT/'src/main/scala/vpu/ParallelIncrement.scala',ROOT/'src/main/scala/vpu/CarrySelect.scala',ROOT/'src/main/scala/vpu/GenerateDividerProof.scala',rtl,script]
d=dict(status='PASS',scope='ALL_2_POWER_34_NEGATE_INPUTS; ALL_PATTERNS_ADD_AND_INCREMENT_WIDTHS_11_16_17_26_32_33_WITH_CARRY_OUT; SEQUENCING_CHECKED_SEPARATELY',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS all-pattern divider word and carry equivalence')
