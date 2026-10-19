#!/usr/bin/env python3
"""Read-only historical audit: changed M53 sources resolve to frozen copies."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CHANGED={'src/main/scala/vpu/'+n for n in ['RamVector.scala','FloatingPointConvertResize.scala','VpuMonitor.scala','GenerateConfigured.scala']}
def check_historical(d):
    assert d['status']=='PASS';count=0
    for key in ['source_sha256','artifact_sha256','external_tool_dependency_sha256','external_source_sha256','sha256']:
        for rel,h in d.get(key,{}).items():
            path=ROOT/rel
            if path.is_file() and sha(path)==h:count+=1;continue
            assert rel in CHANGED,(key,rel,'historical evidence changed outside versioned sources')
            archived=ROOT/'archive/m53/source'/rel;assert sha(archived)==h,rel;count+=1
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256'];count+=1
    return count
def audit():
    frozen=json.loads((ROOT/'archive/m53/baseline.json').read_text());assert frozen['current_M53_evidence_checked']
    for rel,h in frozen['archive_sha256'].items():assert sha(ROOT/rel)==h,rel
    current={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert set(current)-set(frozen['source_sha256'])=={'src/main/scala/vpu/GenerateM54.scala','src/main/scala/vpu/GenerateHalfRoundProof.scala'}
    assert set(frozen['source_sha256'])-set(current)==set()
    changed={p for p,h in frozen['source_sha256'].items() if current[p]!=h};assert changed==CHANGED,changed
    checked={}
    for m in [50,51,52,53]:
        rel=f'reports/m{m}/receipt.json';assert sha(ROOT/rel)==frozen['reports'][rel]
        checked[rel]=check_historical(json.loads((ROOT/rel).read_text()))
    return dict(status='PASS',prior_commit=frozen['commit'],changed_hardware_sources=sorted(changed),
                historical_checked_bindings=checked,M53_local_300MHz_applies_to_M54=False)
if __name__=='__main__':print(json.dumps(audit(),indent=2))
