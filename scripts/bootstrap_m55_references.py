#!/usr/bin/env python3
"""Reuse pinned upstream libraries, enable Zvbb solely in Spike's ISA string."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=ROOT/'build/m55/reference';out.mkdir(parents=True,exist_ok=True)
old=json.loads((ROOT/'build/spike-model/results.json').read_text())
for rel,h in old['model_libraries_sha256'].items():assert sha(ROOT/rel)==h,rel
adapter=ROOT/'tests/spike_zvbb_adapter.cc';binary=out/'spike-zvbb'
cmd=[str(x) for x in old['link_command']];cmd[cmd.index(str(ROOT/'tests/spike_adapter.cc'))]=str(adapter);cmd[-1]=str(binary)
with (out/'link.log').open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=f,check=True)
d=dict(status='PASS',isa='rv64gcv_zvfhmin_zvbb_zvl128b',semantics_modified=False,revision=old['revision'],binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),link_command=cmd,
    source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),adapter]},
    artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary,out/'link.log',ROOT/'build/spike-model/results.json',*map(lambda x:ROOT/x,old['model_libraries_sha256'])]})
(out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS independent Spike Zvbb transport')
