#!/usr/bin/env python3
"""Bounded SAT equivalence of staged rounding to pinned HardFloat, held inputs."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/round-proof';OUT.mkdir(parents=True,exist_ok=True)
result=OUT/'results.json';result.unlink(missing_ok=True);rtl=OUT/'RoundProof.sv'
with (OUT/'generate.log').open('w') as log:
 subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateRoundProof',str(rtl)],cwd=ROOT,stdout=log,stderr=log,check=True)
ys=OUT/'proof.ys';ys.write_text(f'read_verilog -sv {rtl}\nprep -top RoundProof -flatten\nsat -seq 10 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove io_mismatch 0\n')
with (OUT/'proof.log').open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-T','-s',str(ys)],stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[Path(__file__).resolve(),ROOT/'src/main/scala/vpu/generate/proof/GenerateRoundProof.scala',ROOT/'src/main/scala/vpu/execute/fp/StagedRound.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala',rtl,ys]
d=dict(status='PASS',scope='BOUNDED_10_STEPS_SINGLE_HELD_RAW_INPUT_4_FORMATS_ALL_RAW_BITS_AND_MODES_WITH_DONE_NONVACUITY_NOT_FULL_LANE_PROOF',
 input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
result.write_text(json.dumps(d,indent=2)+'\n');print('PASS staged-round bounded equivalence, four formats, nonvacuous done')
