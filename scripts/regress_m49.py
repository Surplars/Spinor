#!/usr/bin/env python3
"""Run the ordered compiler build, then independent public-preset program jobs."""
import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/m49-regression'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'results.json').unlink(missing_ok=True)
py=sys.executable
subprocess.run([py,'tests/test_program_scalar.py'],cwd=ROOT,check=True)
subprocess.run([py,'tests/test_compiled_programs.py','--build-only'],cwd=ROOT,check=True)
jobs=[]
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
    for mapped in [False,True]:
        jobs.append(['--top',top,'--compact',*(['--mapped'] if mapped else []),
                     *(['--negative-control'] if top=='SpinorInteger' and not mapped else [])])
for top in ['SpinorStandard','SpinorInteger']:
    jobs.append(['--top',top])

def run(args):
    label=args[1]+('-compact' if '--compact' in args else '-full')+('-mapped' if '--mapped' in args else '-rtl')
    log=OUT/(label+'.log');start=time.monotonic()
    with log.open('w') as f:
        result=subprocess.run([py,'tests/test_compiled_programs.py',*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    record=dict(args=args,exit_code=result.returncode,seconds=round(time.monotonic()-start,2),log=str(log.relative_to(ROOT)),results=f'build/programs/{label}/results.json')
    print(label,result.returncode,flush=True)
    return label,record

ledger={}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for label,record in pool.map(run,jobs):
        ledger[label]=record
        temporary=OUT/'results.tmp';temporary.write_text(json.dumps(ledger,indent=2)+'\n');temporary.replace(OUT/'results.json')
assert len(ledger)==10 and all(r['exit_code']==0 for r in ledger.values()),'See build/m49-regression logs'
