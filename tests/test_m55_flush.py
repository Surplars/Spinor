#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from test_compiled_programs import ROOT,env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    out=ROOT/'build/m55/flush'/a.top;out.mkdir(parents=True,exist_ok=True);gdir=ROOT/'build/m55/gsim/rtl'/a.top;fp='Integer' not in a.top
    zero=out/'zero.hex';zero.write_text('0000000000000000\n'*64);binary=out/'run';harness=ROOT/'tests/m55_flush.cc'
    cmd=[ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-DENABLE_FP='+str(int(fp)),'-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
    for command,label in [(cmd,'compile.log'),([binary,zero],'run.log')]:
        with (out/label).open('w') as f:subprocess.run(list(map(str,command)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=300)
    text=(out/'run.log').read_text().strip();assert 'aborted=3536' in text
    with (out/'negative.log').open('w') as f:r=subprocess.run([binary,zero,'mutate-rf'],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
    assert r.returncode==1 and 'flush committed RF changed' in (out/'negative.log').read_text()
    d=dict(status='PASS',top=a.top,aborted=3536,execution_and_held_completion=True,summary=text,negative_controls={'mutate-committed-rf':'REJECTED'},
       source_sha256={str(x.relative_to(ROOT)):sha(x) for x in [__import__('pathlib').Path(__file__).resolve(),harness,ROOT/'tests/gsim_spike_driver.cc']},
       artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in [binary,zero,out/'compile.log',out/'run.log',out/'negative.log',gdir/'results.json']})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(text)
if __name__=='__main__':main()
