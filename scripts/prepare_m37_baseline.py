#!/usr/bin/env python3
"""Restore the hash-bound M36 timing graph from its compact frozen archive."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/baseline-m36';OUT.mkdir(parents=True,exist_ok=True)
base=ROOT/'archive/m36/reports/receipt.json';compressed=ROOT/'archive/m36/synth-SpinorVpu/mapped.json.gz'
raw=gzip.decompress(compressed.read_bytes());expected=json.loads(base.read_text())['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
assert hashlib.sha256(raw).hexdigest()==expected
out=OUT/'SpinorVpu.json';out.write_bytes(raw)
files=[base,compressed,Path(__file__).resolve()]
result=dict(status='PASS',restored_sha256=expected,restored_bytes=len(raw),input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},output='build/baseline-m36/SpinorVpu.json')
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS M36 timing baseline restored with exact graph SHA')
