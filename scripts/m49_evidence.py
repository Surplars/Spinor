"""Exact M48 dependency/evidence checks; only delivery prose may change in M49."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DELIVERY_ONLY={'README.md','Makefile','scripts/package.py','docs/repository.md',
               'docs/rvv-completion-plan.md','docs/cpu-spinor-contract.md'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def base_evidence():
    path=ROOT/'reports/m48/receipt.json';base=json.loads(path.read_text())
    assert base['status']=='FOF_LOADS_ATOMIC_VL_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED'
    changed=[];checked=[]
    for rel,h in base['source_sha256'].items():
        file=ROOT/rel
        if file.is_file() and sha(file)==h:checked.append(rel)
        else:
            assert rel in DELIVERY_ONLY,('M48 execution dependency changed',rel)
            changed.append(rel)
    for rel,h in base['artifact_sha256'].items():
        file=ROOT/rel
        assert file.is_file() and sha(file)==h,('M48 evidence missing/changed',rel)
    return base,dict(status='PASS',scope='EXACT_HARDWARE_AND_EXECUTION_DEPENDENCY_M48_EVIDENCE_REUSE',
                     receipt_sha256=sha(path),checked_sources=len(checked),checked_artifacts=len(base['artifact_sha256']),
                     changed_delivery_only=sorted(changed),hardware_changed=False,
                     rtl_matrix=base['regression_counts'] if 'regression_counts' in base else None)
