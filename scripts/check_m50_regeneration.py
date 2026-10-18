#!/usr/bin/env python3
"""Re-elaborate default and four presets without touching published evidence."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/m50-regeneration'
OUT.mkdir(parents=True,exist_ok=True)
outputs={}
jobs=[('default',['vpu.Generate',str(OUT/'default')],ROOT/'build/rtl')]
for preset,top in [('standard','SpinorStandard'),('deep','SpinorDeep'),('integer','SpinorInteger'),('integer-deep','SpinorIntegerDeep')]:
    jobs.append((top,['vpu.GenerateConfigured','--out',str(OUT/top),'--name',top,'--preset',preset],ROOT/f'build/profiles/rtl/{top}'))
for name,args,expected in jobs:
    with (OUT/(name+'.log')).open('w') as log:
        subprocess.run([str(ROOT/'mill'),'Vpu.runMain',*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    count=0
    for path in (OUT/name).rglob('*'):
        if not path.is_file() or path.suffix not in ['.sv','.json']:continue
        prior=expected/path.relative_to(OUT/name)
        assert path.read_bytes()==prior.read_bytes(),prior
        outputs[str(prior.relative_to(ROOT))]=hashlib.sha256(prior.read_bytes()).hexdigest();count+=1
    assert count
    print('PASS regeneration',name,count,'files byte-identical',flush=True)
sources=[ROOT/'build.mill',ROOT/'.mill-version',Path(__file__).resolve(),*(ROOT/'src').rglob('*.scala')]
result=dict(status='PASS',scope='CURRENT_DEFAULT_AND_PRESET_REELABORATION_BYTE_IDENTICAL',files=len(outputs),sha256=outputs,
            source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
