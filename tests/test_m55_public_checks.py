#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_compiled_programs import ROOT,env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    out=ROOT/'build/m55/public-checks'/a.top;out.mkdir(parents=True,exist_ok=True);gdir=ROOT/'build/m55/gsim/rtl'/a.top;fp='Integer' not in a.top
    gold=out/'zero.hex';gold.write_text('0000000000000000\n'*64);binary=out/'run';harness=ROOT/'tests/m55_public_checks.cc'
    command=[ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-DENABLE_FP='+str(int(fp)),'-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
    for cmd,label in [(command,'compile.log'),([binary,gold],'run.log')]:
        with (out/label).open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=300)
    text=(out/'run.log').read_text().strip();assert 'disabled_FP_rejections='+('0' if fp else '320') in text
    d=dict(status='PASS',top=a.top,summary=text,monitor_implementation='0x5501',disabled_FP_rejections=0 if fp else 320,
           source_sha256={str(x.relative_to(ROOT)):sha(x) for x in [Path(__file__).resolve(),harness,ROOT/'tests/gsim_spike_driver.cc']},
           artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in [gold,binary,out/'compile.log',out/'run.log',gdir/'results.json']})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(text)
if __name__=='__main__':main()
