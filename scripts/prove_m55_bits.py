#!/usr/bin/env python3
"""Decomposed held-input equivalence, 4 SEWs x 8 ops, with a done proof."""
import hashlib,json,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m55/bit-proof';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rtl=ROOT/'build/m55/rtl/IntegerLaneSplit.sv';wrapper=ROOT/'tests/m55_bitproof.sv'
def prove(pair):
    sew,op=pair;stem=OUT/f'sew{8<<sew}-op{op}';ys=stem.with_suffix('.ys');log=stem.with_suffix('.log')
    ys.write_text(f'read_verilog -sv {rtl} {wrapper}\nchparam -set SEW_CODE {sew} -set OP_CODE {op} BitManipProof\nprep -top BitManipProof -flatten\nsat -seq 10 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove mismatch 0\nsat -seq 8 -set-init-zero -set reset 0 -set-at 1 reset 1 -verify -prove done 1 -prove-skip 7\n')
    with log.open('w') as f:subprocess.run([ROOT/'tools/oss-cad-suite/bin/yosys','-T','-s',ys],cwd=ROOT,stdout=f,stderr=f,check=True,timeout=45)
    assert log.read_text().count('SUCCESS!')==2
    print('PASS SAT',8<<sew,op,flush=True);return [ys,log]
with ThreadPoolExecutor(max_workers=2) as pool:files=sum(pool.map(prove,[(s,o) for s in range(4) for o in range(30,38)]),[])
sources=[Path(__file__).resolve(),wrapper,ROOT/'src/main/scala/vpu/BitManipPipeline.scala']
d=dict(status='PASS',scope='BOUNDED_10_STEPS_HELD_ARBITRARY_64BIT_INPUTS_ALL_4_SEWS_8_BIT_PIPELINE_OPS_NOT_FULL_VPU',proof_cases=32,nonvacuity='DONE_PROVEN_AT_STEP_8_EACH_CASE',
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [rtl,*files]})
(OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS 32 bit pipeline bounded SAT cases and done proofs')
