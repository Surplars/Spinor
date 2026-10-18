#!/usr/bin/env python3
"""Build a separate wide-operation wrapper; retain the pinned SoftFloat library."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'tools/fp';source=out/'softfloat';lib=source/'build/Linux-x86_64-GCC/softfloat.a';wrapper=ROOT/'tests/fp_widen_reference.c'
 assert lib.exists(),'Run make fp-bootstrap first'
 # Verify the same downloaded source archive used by bootstrap_fp.py.
 assert hashlib.sha256((out/'softfloat.zip').read_bytes()).hexdigest()=='90493f9ad6c9760b2b1ca91251b8e7a3bb616b2935808d243e158a432a514f98'
 target=out/'libfp-widen-reference.so'
 subprocess.run(['gcc','-std=c11','-O2','-fPIC','-shared','-I'+str(source/'source/include'),str(wrapper),str(lib),'-o',str(target)],check=True)
 evidence=ROOT/'build/fp-widen-reference';evidence.mkdir(parents=True,exist_ok=True)
 files=[wrapper,Path(__file__).resolve()]
 (evidence/'results.json').write_text(json.dumps(dict(status='PASS',wrapper_library_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),softfloat_library_sha256=hashlib.sha256(lib.read_bytes()).hexdigest(),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2)+'\n')
if __name__=='__main__':main()
