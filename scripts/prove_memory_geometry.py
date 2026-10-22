#!/usr/bin/env python3
"""Prove all 128 EMUL decode keys and 32 RF bases against independent arithmetic."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/memory-geometry-proof';OUT.mkdir(parents=True,exist_ok=True)
(OUT/'results.json').unlink(missing_ok=True)
with (OUT/'generate.log').open('w') as log:subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateMemoryGeometryProof',str(OUT)],cwd=ROOT,stdout=log,stderr=log,check=True)
script=OUT/'proof.ys';script.write_text(f'read_verilog -sv {OUT}/MemoryGeometryProof.sv\nprep -top MemoryGeometryProof\nflatten\nopt\nsat -verify -prove io_ok 1 -show-inputs\n')
with (OUT/'proof.log').open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/yosys'),'-Q','-T','-s',str(script)],cwd=ROOT,stdout=log,stderr=log,check=True)
assert 'SUCCESS!' in (OUT/'proof.log').read_text()
files=[Path(__file__).resolve(),ROOT/'src/main/scala/vpu/memory/MemoryGeometry.scala',ROOT/'src/main/scala/vpu/generate/proof/GenerateMemoryGeometryProof.scala',ROOT/'src/main/scala/vpu/memory/VectorMemoryEngine.scala',OUT/'MemoryGeometryProof.sv',script]
d=dict(status='PASS',scope='ALL_128_LMUL_EEW_SEW_KEYS_AND_32_RF_BASES; EXACT_OLD_GROUP_VALIDITY_INTEGRAL_AND_ALIGNED_POWER_OF_TWO_END_CHECK; COMBINATIONAL_ONLY_NOT_LSU_FSM',input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files});(OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS all-pattern memory geometry and aligned group end check')
