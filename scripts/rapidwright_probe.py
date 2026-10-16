#!/usr/bin/env python3
"""Small standalone RapidWright capability check; NOT design STA or a placer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
from urllib.parse import urlsplit
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',action='store_true');args=parser.parse_args()
    spec=json.loads((ROOT/'tools.lock.json').read_text())['rapidwright']
    out=ROOT/'tools/rapidwright-research';out.mkdir(parents=True,exist_ok=True)
    jar=out/spec['artifact']['url'].rsplit('/',1)[1]
    if not jar.exists():
        temporary=jar.with_suffix('.partial')
        with urllib.request.urlopen(spec['artifact']['url'],timeout=120) as src,temporary.open('wb') as dst:
            while chunk:=src.read(1024*1024):dst.write(chunk)
        assert sha(temporary)==spec['artifact']['sha256'];temporary.rename(jar)
    assert sha(jar)==spec['artifact']['sha256']
    extracted=['data/parts.db','data/parts.db.md5','timing/ultrascaleplus/intrasite_delay_terms.txt',
               'timing/ultrascaleplus/intersite_delay_terms.txt']
    with ZipFile(jar) as z:
        for n in extracted:
            if n not in z.namelist():continue
            target=out/n;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(n))
    compiler=shutil.which('javac')
    if not compiler:compiler=next((str(p) for p in (ROOT/'tools/cache').rglob('javac')),None)
    if not compiler:raise SystemExit('JDK21 compiler required; run the Mill build or provide javac on PATH')
    jdk=Path(compiler).resolve().parent;classes=out/'classes';classes.mkdir(exist_ok=True)
    subprocess.run([str(jdk/'javac'),'-cp',str(jar),'-d',str(classes),str(ROOT/'scripts/java/RapidWrightProbe.java')],check=True)
    cmd=[str(jdk/'java'),'-Xmx4G']
    for proto in ['http','https']:
        url=os.environ.get(proto.upper()+'_PROXY')
        if url:
            u=urlsplit(url)
            if u.username or u.password:raise SystemExit('Credentialed JVM proxy requires an authenticator')
            cmd += [f'-D{proto}.proxyHost={u.hostname}',f'-D{proto}.proxyPort={u.port or 80}']
    if Path('/etc/ssl/certs/java/cacerts').exists():cmd += ['-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
    cmd += ['-cp',str(classes)+os.pathsep+str(jar),'com.xilinx.rapidwright.timing.RapidWrightProbe']
    if args.device:cmd+=['--device']
    run=subprocess.run(cmd,env={**os.environ,'RAPIDWRIGHT_PATH':str(out)},capture_output=True,text=True,check=True,timeout=180)
    target=ROOT/'build/rapidwright';target.mkdir(parents=True,exist_ok=True)
    (target/'probe.log').write_text(run.stdout+run.stderr)
    assert 'PART xczu15eg-ffvb1156-2-i xczu15eg -2 UltraScalePlus' in run.stdout
    if args.device:assert 'DEVICE xczu15eg rows=435 cols=455' in run.stdout
    arcs={}
    for line in run.stdout.splitlines():
        if line.startswith('ARC_PS '):
            _,bel,source,sink,value=line.split();arcs[bel+':'+source+'->'+sink]=int(value)
    assert arcs and all(v>=0 for v in arcs.values())
    inputs={str(jar.relative_to(ROOT)):sha(jar)}
    inputs.update({str((out/n).relative_to(ROOT)):sha(out/n) for n in extracted if (out/n).exists()})
    device=out/'data/devices/zynquplus/xczu15eg_db.dat'
    if args.device:inputs[str(device.relative_to(ROOT))]=sha(device)
    result={'status':'PASS_CAPABILITY_PROBE','version':spec['version'],'target':'xczu15eg-ffvb1156-2-i',
            'device_loaded':args.device,'family_model':'UltraScalePlus','family_logic_arcs_ps':arcs,
            'placed_or_routed_VPU':False,'device_speed_grade_calibrated':False,
            'DSP_delays_available':False,'passes_300MHz':None,'passes_500MHz':None,'input_sha256':inputs}
    (target/'probe.json').write_text(json.dumps(result,indent=2)+'\n')
    print(run.stdout,end='');print('Saved build/rapidwright/probe.json; this is not a VPU timing report')

if __name__=='__main__':main()
