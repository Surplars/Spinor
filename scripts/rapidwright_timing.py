#!/usr/bin/env python3
"""Build a reference timing graph from a matched DCP/EDIF/DSP export set."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--dsp-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'build/rapidwright/m4-timing')
    a=p.parse_args();dcp=a.checkpoint.resolve();dsp=a.dsp_dir.resolve();out=a.output.resolve()
    assert dcp.is_file() and dcp.with_suffix('.edf').is_file() and dsp.is_dir()
    spec=json.loads((ROOT/'tools.lock.json').read_text())['rapidwright']
    cache=ROOT/'tools/rapidwright-research';jar=cache/spec['artifact']['url'].rsplit('/',1)[1]
    assert jar.is_file() and sha(jar)==spec['artifact']['sha256'],'Run make rapidwright-probe first'
    out.mkdir(parents=True,exist_ok=True)
    jdk=next((ROOT/'tools/cache').rglob('javac')).resolve().parent
    source=ROOT/'scripts/java/RapidWrightTimingProbe.java'
    subprocess.run([str(jdk/'javac'),'-cp',str(jar),'-d',str(out),str(source)],check=True)
    cmd=[str(jdk/'java'),'-Xmx4g','-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts']
    for scheme in ['http','https']:
        proxy=urlsplit(os.environ.get(scheme.upper()+'_PROXY',''))
        if proxy.hostname:
            if proxy.username or proxy.password:raise SystemExit('Use the configured proxy authenticator')
            cmd.extend([f'-D{scheme}.proxyHost={proxy.hostname}',f'-D{scheme}.proxyPort={proxy.port or 80}'])
    cmd += ['-cp',str(out)+os.pathsep+str(jar),'com.xilinx.rapidwright.timing.RapidWrightTimingProbe',str(dcp),str(dsp)+os.sep]
    run=subprocess.run(cmd,env={**os.environ,'RAPIDWRIGHT_PATH':str(cache),
        'RW_AUTO_GENERATE_READABLE_EDIF':'0'},capture_output=True,text=True)
    log=run.stdout+run.stderr;(out/'probe.log').write_text(log)
    values={}
    for line in run.stdout.splitlines():
        if line.startswith('PROBE_'):
            key,_,value=line.partition(' ');values[key]=value
    inputs=[dcp,dcp.with_suffix('.edf'),jar,source,ROOT/'scripts/rapidwright_timing.py',*sorted(dsp.glob('*.txt'))]
    inputs += [cache/n for n in ['data/parts.db','data/unisim_data.dat',
        'data/devices/zynquplus/xczu15eg_db.dat','timing/ultrascaleplus/intrasite_delay_terms.txt',
        'timing/ultrascaleplus/intersite_delay_terms.txt'] if (cache/n).is_file()]
    result={'status':'BUILT_REFERENCE_GRAPH' if run.returncode==0 else 'REFERENCE_GRAPH_BUILD_BLOCKED',
        'scope':'M4_VIVADO_IMPLEMENTATION_ONLY_NOT_M5','exit_code':run.returncode,'observations':values,
        'passes_300MHz':None,'passes_500MHz':None,'signoff_STA':False,
        'source_or_artifact_sha256':{str(f):sha(f) for f in inputs}}
    (out/'probe.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['observations'],indent=2));print(result['status'])
    if run.returncode:print(log[-2500:])
    # Blocked experiments are evidence too; JSON and the full log are preserved.

if __name__=='__main__':main()
