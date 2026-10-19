#!/usr/bin/env python3
"""Normative opcode scope plus bounded public-interface timing comparison."""
import argparse,csv,hashlib,json,subprocess
from pathlib import Path
from test_compiled_programs import ROOT,env
from m56_diel_scope import rows
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorHost',choices=['SpinorHost','SpinorHostDeep']);a=p.parse_args()
    out=ROOT/'build/m56/diel'/a.top;out.mkdir(parents=True,exist_ok=True);scope=rows();table=out/'scope.csv'
    with table.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(scope[0]),lineterminator='\n');w.writeheader();w.writerows(scope)
    entries=[r for r in scope if r['scope']!='EXCLUDED'];fixture=out/'opcodes.txt';lines=[]
    for r in entries:
        n=r['name'];role=int(n.startswith('vrgather'))|(2 if n.startswith(('vrgather','vslideup','vslidedown')) else 0)|(4 if n.startswith('vmerge') else 0)
        lines.append(f'{n} {int(r["match"],16):x} {int(r["mask"],16):x} {role:x}')
    fixture.write_text('\n'.join(lines)+'\n');gdir=ROOT/'build/m56/gsim/rtl'/a.top;harness=ROOT/'tests/m56_diel.cc';binary=out/'run'
    cmd=[ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-DENABLE_FP=1','-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
    for command,label in [(cmd,'compile.log'),([binary,fixture],'run.log')]:
        with (out/label).open('w') as f:subprocess.run(list(map(str,command)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=180)
    summary=next(l for l in (out/'run.log').read_text().splitlines() if l.startswith('PASS DIEL'));legal={l.split()[1] for l in (out/'run.log').read_text().splitlines() if l.startswith('DIEL ') and l.split()[5]=='1'}
    assert legal=={r['name'] for r in entries},set(r['name'] for r in entries)-legal
    with (out/'negative.log').open('w') as f:r=subprocess.run([binary,fixture,'corrupt-latency'],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=30)
    assert r.returncode==1 and 'data-dependent completion latency' in (out/'negative.log').read_text()
    d=dict(status='PASS',top=a.top,scope='SAMPLED_PUBLIC_COMPLETION_TIMING_NOT_ZVKT_COMPLIANCE_PROOF',summary=summary,encodings=len(entries),required_encodings=sum(r['scope']=='REQUIRED' for r in entries),review_encodings=[r['name'] for r in entries if r['scope']=='REVIEW'],
       legal_encodings=sorted(legal),negative_controls={'corrupt-observed-latency':'REJECTED'},
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),harness,ROOT/'tests/m56_host_driver.cc',ROOT/'tests/m56_diel_scope.py',ROOT/'docs/references/m56-zvkt.adoc']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [table,fixture,binary,*out.glob('*.log'),gdir/'results.json']})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(summary,len(entries),'encodings')
if __name__=='__main__':main()
