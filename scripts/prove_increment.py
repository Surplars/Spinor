#!/usr/bin/env python3
"""SAT proof of modulo increments and split 64-bit vector address arithmetic."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/increment-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True)
rtl=OUT/'IncrementProof.sv'
subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateIncrementProof',str(rtl)],cwd=ROOT,check=True,stdout=(OUT/'generate.log').open('w'),stderr=subprocess.STDOUT)
script=OUT/'proof.ys';script.write_text(f'read_verilog -sv {rtl}\nprep -top IncrementProof -flatten\nsat -verify -prove io_mismatch 0 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(script)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[ROOT/'scripts/prove_increment.py',ROOT/'src/main/scala/vpu/execute/fp/StagedFloatToInt.scala',ROOT/'src/main/scala/vpu/execute/fp/StagedFmaPost.scala',ROOT/'src/main/scala/vpu/memory/PackedElementRead.scala',ROOT/'src/main/scala/vpu/util/ParallelIncrement.scala',ROOT/'src/main/scala/vpu/config/VectorConfig.scala',ROOT/'src/main/scala/vpu/core/RamVector.scala',ROOT/'src/main/scala/vpu/util/CarrySelect.scala',ROOT/'src/main/scala/vpu/generate/proof/GenerateIncrementProof.scala',ROOT/'src/main/scala/vpu/memory/VectorMemoryEngine.scala',rtl,script]
d=dict(status='PASS',scope='ALL_INPUTS_SEGMENTED_8BIT_INCREMENT_WIDTHS_32_64_109_AND_MODULO_INCREMENT_WIDTHS_5_8_32_55_109_AND_COMBINATIONAL_SPLIT_64_BIT_ADDRESS_AND_CONFIGURATION_COMPARISON_AND_ALIGNED_GROUP_MEMBERSHIP_OVERLAP_ALIGNMENT_END_AND_WIDENING_HIGH_PART_AND_NARROWING_WIDENING_ALIGNMENT_AND_ONE_HOT_BYTE_READ; PIPELINE_CHECKED_SEPARATELY',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS all-pattern increment and split-address equivalence')
