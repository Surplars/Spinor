#!/usr/bin/env python3
"""Pinned, separately implemented SoftFloat oracle; never modifies its sources."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
REV='a0c6494cdc11865811dec815d5c0049fba9d82a8'
DIGEST='90493f9ad6c9760b2b1ca91251b8e7a3bb616b2935808d243e158a432a514f98'

def main():
    out=ROOT/'tools/fp';out.mkdir(parents=True,exist_ok=True)
    archive=out/'softfloat.zip'
    if not archive.exists():
        with urllib.request.urlopen('https://codeload.github.com/ucb-bar/berkeley-softfloat-3/zip/'+REV,timeout=120) as s:
            archive.write_bytes(s.read())
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==DIGEST,'SoftFloat archive hash'
    source=out/'softfloat';prefix='berkeley-softfloat-3-'+REV+'/'
    hashes={}
    with ZipFile(archive) as z:
        for n in z.namelist():
            if n.endswith('/'):continue
            assert n.startswith(prefix)
            rel=n[len(prefix):];target=source/rel;data=z.read(n)
            assert target.resolve().is_relative_to(source.resolve())
            if target.exists():assert target.read_bytes()==data,'Modified independent oracle: '+rel
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            hashes[rel]=hashlib.sha256(data).hexdigest()
    manifest=json.loads((ROOT/'third_party/fp-dependencies.json').read_text())
    for n,h in manifest['local_sources_sha256'].items():
        assert hashlib.sha256((ROOT/'third_party/berkeley-hardfloat/src/main/scala'/n).read_bytes()).hexdigest()==h,n
    build=source/'build/Linux-x86_64-GCC'
    with (out/'softfloat-build.log').open('w') as log:
        subprocess.run(['make','-j4','SOFTFLOAT_OPTS=-fPIC -DSOFTFLOAT_ROUND_ODD -DINLINE_LEVEL=5 -DSOFTFLOAT_FAST_DIV32TO16 -DSOFTFLOAT_FAST_DIV64TO32'],
                       cwd=build,stdout=log,stderr=log,check=True)
    subprocess.run(['gcc','-std=c11','-O2','-fPIC','-shared','-I'+str(source/'source/include'),
                    str(ROOT/'tests/fp_reference.c'),str(build/'softfloat.a'),'-o',str(out/'libfp-reference.so')],check=True)
    (out/'oracle-source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print('Pinned SoftFloat oracle built; source archive and HardFloat imports verified')

if __name__=='__main__':main()
