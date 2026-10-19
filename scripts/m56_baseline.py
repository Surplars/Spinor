#!/usr/bin/env python3
"""Versioned source resolution for retained evidence, never stale current RTL."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CHANGED={'src/main/scala/vpu/'+n for n in ['Protocol.scala','RamVector.scala','SpinorParams.scala','MemoryRamVector.scala','VectorMemoryEngine.scala','VpuMonitor.scala','GenerateConfigured.scala']}
VERSIONED=CHANGED|{'src/main/scala/vpu/IntegerLane.scala','src/main/scala/vpu/FloatingPointConvertResize.scala','README.md','CURRENT.md','.gitattributes','docs/cpu-spinor-contract.md'}
def historical(d):
    assert d['status']=='PASS';n=0
    for key in ['source_sha256','artifact_sha256','external_tool_dependency_sha256','external_source_sha256','sha256']:
        for rel,h in d.get(key,{}).items():
            if (ROOT/rel).is_file() and sha(ROOT/rel)==h:n+=1;continue
            assert rel in VERSIONED,(key,rel,'unversioned historical mutation')
            assert any((ROOT/f'archive/m{m}/source'/rel).is_file() and sha(ROOT/f'archive/m{m}/source'/rel)==h for m in [53,54,55]),rel
            n+=1
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256'];n+=1
    return n
def audit():
    d=json.loads((ROOT/'archive/m55/baseline.json').read_text());assert d['current_M55_evidence_checked']
    for m in [53,54,55]:
        f=json.loads((ROOT/f'archive/m{m}/baseline.json').read_text())
        for rel,h in f['archive_sha256'].items():assert sha(ROOT/rel)==h,rel
    current={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')};old={p:h for p,h in d['source_sha256'].items() if p.endswith('.scala')}
    assert set(current)-set(old)=={'src/main/scala/vpu/GenerateM56.scala','src/main/scala/vpu/GenerateHostGsim.scala'}
    assert not(set(old)-set(current));changed={p for p,h in old.items() if current[p]!=h};assert changed==CHANGED,changed
    bindings={}
    for rel,h in d['reports'].items():assert sha(ROOT/rel)==h,rel;bindings[rel]=historical(json.loads((ROOT/rel).read_text()))
    return dict(status='PASS',prior_commit=d['commit'],changed_hardware_sources=sorted(changed),historical_checked_bindings=bindings)
if __name__=='__main__':print(json.dumps(audit(),indent=2))
