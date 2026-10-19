#!/usr/bin/env python3
"""Bounded nonvacuous SAT equivalence of the new half rounder to HardFloat."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m54/half-round-proof';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rtl=OUT/'HalfRoundProof.sv';ys=OUT/'proof.ys'
with (OUT/'generate.log').open('w') as f:subprocess.run([ROOT/'mill','Vpu.runMain','vpu.GenerateHalfRoundProof',rtl],cwd=ROOT,stdout=f,stderr=f,check=True)
ys.write_text(f'read_verilog -sv {rtl}\nprep -top HalfRoundProof -flatten\nsat -seq 10 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove io_mismatch 0\n')
with (OUT/'proof.log').open('w') as f:subprocess.run([ROOT/'tools/oss-cad-suite/bin/yosys','-T','-s',ys],cwd=ROOT,stdout=f,stderr=f,check=True,timeout=300)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
d=dict(status='PASS',scope='BOUNDED_10_STEPS_SINGLE_HELD_RAW_INPUT_ALL_BITS_MODES_AND_DONE_NONVACUITY_NOT_FULL_VPU',
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'src/main/scala/vpu/GenerateHalfRoundProof.scala',ROOT/'src/main/scala/vpu/StagedRound.scala',ROOT/'third_party/berkeley-hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [rtl,ys,OUT/'generate.log',OUT/'proof.log']})
(OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS half rounder bounded SAT equivalence with done witness')
