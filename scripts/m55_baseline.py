#!/usr/bin/env python3
"""Exact historical bindings resolve only to explicit immutable snapshots."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CHANGED={'src/main/scala/vpu/'+n for n in ['Protocol.scala','RamVector.scala','IntegerLane.scala','VpuMonitor.scala','GenerateConfigured.scala']}
VERSIONED=CHANGED|{'CURRENT.md','README.md','.gitattributes','src/main/scala/vpu/FloatingPointConvertResize.scala'}
def historical(d):
    assert d['status']=='PASS';n=0
    for key in ['source_sha256','artifact_sha256','external_tool_dependency_sha256','external_source_sha256','sha256']:
        for rel,h in d.get(key,{}).items():
            if (ROOT/rel).is_file() and sha(ROOT/rel)==h:n+=1;continue
            assert rel in VERSIONED,(key,rel,'unversioned historical mutation')
            assert any((ROOT/f'archive/m{m}/source'/rel).is_file() and sha(ROOT/f'archive/m{m}/source'/rel)==h for m in [53,54]),rel
            n+=1
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256'];n+=1
    return n
def audit():
    d=json.loads((ROOT/'archive/m54/baseline.json').read_text());assert d['current_M54_evidence_checked']
    for m in [53,54]:
        f=json.loads((ROOT/f'archive/m{m}/baseline.json').read_text())
        for rel,h in f['archive_sha256'].items():assert sha(ROOT/rel)==h,rel
    current={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    old={p:h for p,h in d['source_sha256'].items() if p.endswith('.scala')}
    assert set(current)-set(old)=={'src/main/scala/vpu/GenerateM55.scala','src/main/scala/vpu/BitManipPipeline.scala'}
    assert not(set(old)-set(current))
    changed={p for p,h in old.items() if current[p]!=h};assert changed==CHANGED,changed
    bindings={}
    for rel,h in d['reports'].items():
        assert sha(ROOT/rel)==h,rel;bindings[rel]=historical(json.loads((ROOT/rel).read_text()))
    return dict(status='PASS',prior_commit=d['commit'],changed_hardware_sources=sorted(changed),historical_checked_bindings=bindings,M53_local_300MHz_applies_to_M55=False)
if __name__=='__main__':print(json.dumps(audit(),indent=2))
