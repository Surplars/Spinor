#!/usr/bin/env python3
"""Verify explicit ownership, retained defaults, and rejection of bad presets."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m56/configured';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
artifacts=[];rows=[]
for name,preset,owner in [('SpinorHost','standard','host'),('SpinorHostDeep','deep','host'),('SpinorStandard','standard','standalone'),('SpinorInteger','integer','standalone')]:
    folder=OUT/name;log=OUT/(name+'.log');cmd=[ROOT/'mill','Vpu.runMain','vpu.GenerateConfigured','--out',folder,'--name',name,'--preset',preset,'--fcsr-owner',owner]
    with log.open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=f,stderr=f,check=True,timeout=180)
    meta=json.loads((folder/(name+'.json')).read_text());text=(folder/(name+'.sv')).read_text()
    assert meta['fcsr_owner']==owner and meta['fflags_delta_port']==(owner=='host')
    assert ('io_core_fcsrHost_frm' in text)==(owner=='host')
    assert meta['monitor_implementation']==('0x5602' if owner=='host' else '0x5501')
    if preset!='integer':
        module=re.search(r'module RamVectorFpMemory(?:16)?\((.*?)endmodule',text,re.S)[1]
        local=bool(re.search(r'\breg\s+\[4:0\]\s+fflags\s*;',module))
        assert local==(owner=='standalone'),(name,local)
    rows.append(meta);artifacts.extend([folder/(name+'.json'),folder/(name+'.sv'),log])
negative={}
for label,opts,message in [('integer-host',['--preset','integer','--fcsr-owner','host'],'Host FCSR mode requires'),('bad-owner',['--fcsr-owner','shared'],'--fcsr-owner must be host or standalone')]:
    folder=OUT/label;log=OUT/(label+'.log');cmd=[ROOT/'mill','Vpu.runMain','vpu.GenerateConfigured','--out',folder,*opts]
    with log.open('w') as f:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=f,stderr=f,timeout=180)
    assert r.returncode and message in log.read_text() and not list(folder.glob('*.sv'));negative[label]='REJECTED';artifacts.append(log)
d=dict(status='PASS',configurations=rows,invalid_configurations=negative,architectural_fflags_register_removed_in_host=True,
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'src/main/scala/vpu/generate/GenerateConfigured.scala',ROOT/'src/main/scala/vpu/config/SpinorParams.scala']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
(OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS explicit FCSR ownership and no duplicate architectural fflags register')
