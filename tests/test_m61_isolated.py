#!/usr/bin/env python3
"""Run independent M60 numerical expectations on the new live isolated ports."""
import argparse
from collections import Counter
import gzip
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from m61_build import ROOT,OUT,TMP,MODELS,sha
from test_m60_restart import cases
from test_compiled_programs import env


def prepare(model):
    folder=OUT/'corpus'/model;folder.mkdir(parents=True,exist_ok=True)
    integer=model=='integer';ident=0;oldRm=oldSat=oldFrm=oldFlags=0;names=Counter();paths=[]
    with gzip.open(folder/'stimulus.txt.gz','wt') as out:
        for sew in (8,16,32,64):
            source=ROOT/f'build/m60/corpus/sew{sew}';manifest=source/'results.json';d=json.loads(manifest.read_text())
            for group in ('source_sha256','artifact_sha256'):
                for rel,h in d[group].items():assert sha(ROOT/rel)==h,rel
            paths.append(manifest)
            with gzip.open(source/'stimulus.txt.gz','rt') as stream:
                for c in cases(sew):
                    regs=[next(stream) for _ in range(32)];pairs=[(next(stream),next(stream)) for _ in range(5)]
                    selected=c['lmul']==0 and c['layout']==0 and c['profile'] in (0,2)
                    if integer and (c['raw']>>12&7) in (1,5):selected=False
                    if not selected:continue
                    names[c['name']]+=1;out.writelines(regs)
                    for step,(rf,command) in enumerate(pairs):
                        if integer and step==2:continue
                        fields=command.split();fields[1]=f'{ident:x}';ident+=1
                        if step in (0,3):
                            for index,value in zip((14,15,16,17),(oldRm,oldSat,oldFrm,oldFlags)):fields[index]=f'{value:x}'
                        if step==1:
                            fields[10]=f'{oldRm<<1|oldSat:x}';fields[16]=f'{oldFrm:x}';fields[17]=f'{oldFlags:x}'
                        if step==2:
                            fields[10]=f'{oldFrm<<5|oldFlags:x}';fields[14]=f'{oldRm:x}';fields[15]=f'{oldSat:x}'
                        oldRm,oldSat,oldFrm,oldFlags=[int(fields[i],16) for i in (14,15,16,17)]
                        out.write(rf);out.write(' '.join(fields[:18])+'\n')
    d=dict(status='PASS',model=model,commands=ident,scenarios=sum(names.values()),encodings=len(names),coverage=names,
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/test_m60_restart.py']},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [*paths,folder/'stimulus.txt.gz']})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS M61 corpus',model,ident,len(names),flush=True)


def execute(model):
    top,_,_=MODELS[model];gdir=TMP/model;out=OUT/'runs'/model;out.mkdir(parents=True,exist_ok=True)
    corpus=OUT/'corpus'/model/'results.json';manifest=json.loads(corpus.read_text())
    for group in ('source_sha256','artifact_sha256'):
        for rel,h in manifest[group].items():assert sha(ROOT/rel)==h,rel
    binary=out/'run';compiler=ROOT/'tools/llvm-program/usr/bin/clang++-19';harness=ROOT/'tests/m61_isolated_driver.cc'
    inputs=[harness,compiler,gdir/(top+'.h'),*sorted(gdir.glob(top+'[0-9]*.cpp'))]
    with (out/'compile.log').open('w') as f:
        subprocess.run([compiler,'-std=c++20','-O2','-DHOST_FCSR='+str(int(model in ('host','deep'))),'-DENABLE_FP='+str(int(model!='integer')),
                        '-DDUT_CLASS=S'+top,'-DDUT_HEADER="'+top+'.h"','-I'+str(gdir),*sorted(gdir.glob(top+'[0-9]*.cpp')),harness,'-ldl','-o',binary],cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=300)
    fixture=OUT/'corpus'/model/'stimulus.txt.gz'
    def run(mode,name,input_fixture=fixture):
        with (out/name).open('w') as log:
            p=subprocess.Popen([binary,*([mode] if mode else [])],cwd=ROOT,env=env(),stdin=subprocess.PIPE,stdout=log,stderr=log)
            try:
                with gzip.open(input_fixture,'rb') as source:
                    while block:=source.read(65536):
                        try:p.stdin.write(block)
                        except BrokenPipeError:break
                try:p.stdin.close()
                except BrokenPipeError:pass
                return p.wait(timeout=300)
            except BaseException:p.kill();p.wait();raise
    assert run(None,'run.log')==0,(out/'run.log').read_text()[-2000:]
    with (out/'directed.log').open('w') as f:
        direct=subprocess.run([binary,'--directed'],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=60)
    assert direct.returncode==0,(out/'directed.log').read_text()[-2000:]
    recovery=ROOT/'build/m58/recovery/stimulus.txt.gz'
    assert run(None,'recovery.log',recovery)==0,(out/'recovery.log').read_text()[-2000:]
    negatives={}
    for mode,diagnostic in [('wrong-grant','EXPECTED wrong grant rejected'),('wrong-rf','RF mismatch'),('wrong-csr','CSR mismatch')]:
        assert run(mode,mode+'.log')==1;assert diagnostic in (out/(mode+'.log')).read_text(),mode;negatives[mode]='REJECTED'
    summary=next(l for l in (out/'run.log').read_text().splitlines() if l.startswith('PASS isolated'))
    d=dict(status='PASS',model=model,summary=summary,trace_replay=False,checked_registers_per_command=32,negative_controls=negatives,
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),harness]},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary,fixture,recovery,ROOT/'build/m58/recovery/results.json',OUT/'corpus'/model/'results.json',*sorted(out.glob('*.log'))]},
           gsim_input_sha256={p.name:sha(p) for p in inputs})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',choices=MODELS,default='host');p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    (prepare if a.prepare_only else execute)(a.model)
