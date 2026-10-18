#!/usr/bin/env python3
"""Synthetic integrity checks: changed arithmetic/dependencies/evidence must invalidate reuse."""
import hashlib,importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sha=lambda b:hashlib.sha256(b).hexdigest()
spec=importlib.util.spec_from_file_location('cache_policy',ROOT/'scripts/reuse_m47.py');policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
checks=[]
(ROOT/'build').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
 r=Path(tmp);policy.ROOT=r;policy.__file__=str(r/'scripts/reuse_m47.py');(r/'scripts').mkdir();Path(policy.__file__).write_bytes((ROOT/'scripts/reuse_m47.py').read_bytes())
 source={'tests/reference_fp.py':b'fixed independent oracle','src/main/scala/vpu/RamVector.scala':b'arithmetic','src/main/scala/vpu/VectorMemoryEngine.scala':b'old memory','src/main/scala/vpu/VpuHostBoundary.scala':b'old boundary'}
 artifacts={'build/rtl/RamVectorFp.sv':b'fixed arithmetic RTL','build/numerical/results.json':b'{"status":"PASS"}','build/m42-regression/rtl.json':b'{}','build/rtl/LishiVpuMemory.sv':b'old memory top','build/rtl/VpuHostBoundary.sv':b'old boundary RTL'}
 for p,b in (source|artifacts).items():q=r/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
 receipt=r/'archive/m42/reports/receipt.json';receipt.parent.mkdir(parents=True);receipt.write_text(json.dumps(dict(source_sha256={p:sha(b) for p,b in source.items()},artifact_sha256={p:sha(b) for p,b in artifacts.items()})))
 assert policy.validate(r/'probe-valid')[0];checks.append('unchanged exact dependencies accepted')
 for i,p in enumerate(['tests/reference_fp.py','src/main/scala/vpu/RamVector.scala','build/rtl/RamVectorFp.sv','build/numerical/results.json','build/m42-regression/rtl.json']):
  f=r/p;before=f.read_bytes();f.write_bytes(before+b' changed');assert not policy.validate(r/f'probe-reject-{i}')[0],p;f.write_bytes(before);checks.append('reject changed '+p)
 for p in ['src/main/scala/vpu/VectorMemoryEngine.scala','build/rtl/LishiVpuMemory.sv']:(r/p).write_text('new memory independently retested')
 assert policy.validate(r/'probe-memory')[0];checks.append('memory changes allow only arithmetic reuse')
 for p in ['src/main/scala/vpu/VpuHostBoundary.scala','build/rtl/VpuHostBoundary.sv']:(r/p).write_text('changed boundary independently retested')
 assert policy.validate(r/'probe-boundary')[0];checks.append('boundary changes allow only arithmetic reuse')
result=dict(status='PASS',scope='SYNTHETIC_CACHE_POLICY_INTEGRITY_CHECKS; REAL_M42_BINDINGS_SEPARATELY_VERIFIED',checks=checks,source_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in [Path(__file__).resolve(),ROOT/'scripts/reuse_m47.py']});out=ROOT/'build/evidence-reuse-m47-test';out.mkdir(parents=True,exist_ok=True);(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS evidence reuse policy',len(checks),'checks')
