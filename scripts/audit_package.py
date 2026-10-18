#!/usr/bin/env python3
"""Audit the current delivery ZIP and restore its frozen timing graphs in isolation."""
import argparse,hashlib,json,re,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--milestone',required=True);a=p.parse_args()
assert re.fullmatch(r'm[0-9]+',a.milestone) and int(a.milestone[1:])>=44
receipt_path=ROOT/f'reports/{a.milestone}/receipt.json';receipt=json.loads(receipt_path.read_text());zpath=ROOT/f'spinor-vpu-{a.milestone}.zip';sha=lambda b:hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(zpath) as z:
 names=z.namelist();assert len(names)==len(set(names));assert z.testzip() is None
 for name in names:
  q=PurePosixPath(name);assert q.parts[0]=='spinor-vpu' and not q.is_absolute() and '..' not in q.parts,name
  assert not any(part in {'.git','.aws','.codex','.agents','__pycache__','node_modules'} for part in q.parts),name
  assert len(q.parts)<2 or q.parts[1] not in {'tools','out','target'},name
  assert q.suffix not in {'.bit','.dcp','.pem','.key','.pyc'},name
 assert z.read(f'spinor-vpu/reports/{a.milestone}/receipt.json')==receipt_path.read_bytes()
 for scope in ['source_sha256','artifact_sha256']:
  for rel,h in receipt[scope].items():assert sha(z.read('spinor-vpu/'+rel))==h,(scope,rel)
 with tempfile.TemporaryDirectory(prefix=f'spinor-{a.milestone}-cold-',dir='/tmp') as tmp:
  cold=Path(tmp)/'spinor-vpu';helpers=['prepare_m26_baseline.py',f'prepare_{a.milestone}_baseline.py'];paths=['scripts/'+h for h in helpers]
  for version in [25,40]:paths.extend([f'archive/m{version}/reports/receipt.json',f'archive/m{version}/synth-SpinorVpu/mapped.json.gz'])
  for rel in paths:
   target=cold/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read('spinor-vpu/'+rel))
  for helper in helpers:subprocess.run(['python3',str(cold/'scripts'/helper)],cwd=cold,check=True)
  for version in [25,40]:
   expected=json.loads((cold/f'archive/m{version}/reports/receipt.json').read_text())['artifact_sha256']['build/synth/SpinorVpu/mapped.json'];assert sha((cold/f'build/baseline-m{version}/SpinorVpu.json').read_bytes())==expected
result=dict(status='PASS',zip=zpath.name,zip_sha256=sha(zpath.read_bytes()),files=len(names),source_bindings=len(receipt['source_sha256']),artifact_bindings=len(receipt['artifact_sha256']),crc=True,safe_paths=True,cold_baselines=[25,40]);out=ROOT/f'build/{a.milestone}-final-audit.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
