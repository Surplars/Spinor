#!/usr/bin/env python3
"""Run immutable independent memory oracles on the new host-FCSR production top."""
import argparse,hashlib,json,subprocess,gzip,shutil
from pathlib import Path
from test_compiled_programs import ROOT,env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorHost',choices=['SpinorHost','SpinorHostDeep']);a=p.parse_args()
    binary=ROOT/'build/m56/fcsr'/a.top/'run';result={};artifacts=[]
    driver=json.loads((binary.parent/'results.json').read_text())
    for rel,h in driver['source_sha256'].items():assert sha(ROOT/rel)==h,rel
    for suite in ['memory','edges']:
        # Same full corpus on both ALU presets; no FP operations/CSRs here.
        old=ROOT/f'build/m55/gsim/SpinorStandard-{suite}-full/stimulus.txt'
        out=ROOT/'build/m56/memory'/a.top/suite;out.mkdir(parents=True,exist_ok=True)
        stimulus=out/'stimulus.txt.gz';lines=['P 0 0']+[line+(' 0 0 0' if line.startswith('I ') else '') for line in old.read_text().splitlines()];stimulus.write_bytes(gzip.compress(('\n'.join(lines)+'\n').encode(),mtime=0))
        def execute(mode,label):
            with (out/label).open('w') as log,gzip.open(stimulus,'rb') as data:
                process=subprocess.Popen([binary,'-',*([mode] if mode else [])],cwd=ROOT,env=env(),stdin=subprocess.PIPE,stdout=log,stderr=log)
                try:
                    shutil.copyfileobj(data,process.stdin)
                    process.stdin.close()
                except BrokenPipeError:
                    try:process.stdin.close()
                    except BrokenPipeError:pass
                return process.wait(timeout=120)
        code=execute(None,'run.log')
        assert code==0,(out/'run.log').read_text()[-1500:]
        summary=next(x for x in (out/'run.log').read_text().splitlines() if x.startswith('PASS host FCSR'))
        negative={}
        for mode,diag in [('corrupt-load','RF mismatch'),('wrong-ram','RAM mismatch'),('wrong-tval','memory fault address mismatch')]:
            code=execute(mode,mode+'.log')
            assert code==1 and diag in (out/(mode+'.log')).read_text(),mode;negative[mode]='REJECTED'
        result[suite]=dict(summary=summary,commands=sum(l.startswith('I ') for l in lines),negative_controls=negative)
        artifacts.extend([old,stimulus,*out.glob('*.log')])
    d=dict(status='PASS',top=a.top,results=result,commands=sum(v['commands'] for v in result.values()),
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/m56_host_driver.cc']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary,binary.parent/'results.json',*artifacts]})
    target=ROOT/'build/m56/memory'/a.top/'results.json';target.write_text(json.dumps(d,indent=2)+'\n');print('PASS host FCSR full memory/edges',a.top,d['commands'])
if __name__=='__main__':main()
