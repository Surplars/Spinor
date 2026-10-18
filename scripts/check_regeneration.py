#!/usr/bin/env python3
"""Re-elaborate the default bundle and compare hardware plus verification layers."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];GENERATED=ROOT/'build/m44-regen';OUT=ROOT/'build/m44-regeneration'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def compare():
 outputs={}
 for p in GENERATED.rglob('*.sv'):
  q=ROOT/'build/rtl'/p.relative_to(GENERATED)
  assert q.exists() and p.read_bytes()==q.read_bytes(),q
  outputs[str(q.relative_to(ROOT))]=sha(q)
 assert outputs,'Run vpu.Generate in build/m44-regen first'
 sources=[ROOT/'build.mill',ROOT/'.mill-version',Path(__file__).resolve(),*(ROOT/'src').rglob('*.scala')]
 OUT.mkdir(parents=True,exist_ok=True)
 result=dict(status='PASS',scope='CURRENT_SOURCE_REELABORATION_BYTE_IDENTICAL',sv_files=len(outputs),sha256=outputs,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources})
 (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS default regeneration:',len(outputs),'SV files byte-identical')
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 with (ROOT/'build/m44-regeneration.log').open('w') as log:subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.Generate','build/m44-regen'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
 compare()
if __name__=='__main__':main()
