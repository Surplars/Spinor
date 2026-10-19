#!/usr/bin/env python3
"""Held-input local bit pipeline equivalence, with a separate done proof."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m55/bit-proof';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rtl=ROOT/'build/m55/rtl/IntegerLaneSplit.sv';wrapper=ROOT/'tests/m55_bitproof.sv';ys=OUT/'proof.ys'
ys.write_text(f'read_verilog -sv {rtl} {wrapper}\nprep -top BitManipProof -flatten\nsat -seq 10 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove mismatch 0\nsat -seq 8 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove done 1 -prove-skip 7\n')
with (OUT/'proof.log').open('w') as f:subprocess.run([ROOT/'tools/oss-cad-suite/bin/yosys','-T','-s',ys],cwd=ROOT,stdout=f,stderr=f,check=True,timeout=180)
assert (OUT/'proof.log').read_text().count('SUCCESS!')==2
sources=[Path(__file__).resolve(),wrapper,ROOT/'src/main/scala/vpu/BitManipPipeline.scala']
d=dict(status='PASS',scope='BOUNDED_10_STEPS_HELD_ARBITRARY_64BIT_INPUTS_ALL_4_SEWS_8_BIT_PIPELINE_OPS_NOT_FULL_VPU',nonvacuity='DONE_PROVEN_AT_STEP_8',
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [rtl,ys,OUT/'proof.log']})
(OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS bit pipeline bounded SAT equivalence and done proof')
