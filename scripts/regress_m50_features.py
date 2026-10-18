#!/usr/bin/env python3
"""M50 independent ISA differential and FP bit-select verification matrices."""
import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m50-features';OUT.mkdir(parents=True,exist_ok=True)
py=sys.executable
jobs={
 'spike-standard-full':['test_spike_differential.py'],
 'spike-integer-full':['test_spike_differential.py','--top','SpinorInteger'],
 'spike-deep':['test_spike_differential.py','--compact','--top','SpinorDeep'],
 'spike-integer-deep':['test_spike_differential.py','--compact','--top','SpinorIntegerDeep'],
 'spike-standard-bounded':['test_spike_differential.py','--compact','--bounded'],
 'spike-integer-bounded':['test_spike_differential.py','--compact','--bounded','--top','SpinorInteger'],
 'select-full':['test_fp_select.py'],
 'select-compact':['test_fp_select.py','--compact'],
 'select-deep':['test_fp_select.py','--compact','--top','RamVectorFp16'],
 'select-integer':['test_fp_select.py','--compact','--top','RamVector'],
 'select-integer-deep':['test_fp_select.py','--compact','--top','RamVector16'],
 'spike-standard-mapped':['test_spike_differential.py','--compact','--bounded','--mapped'],
 'spike-integer-mapped':['test_spike_differential.py','--compact','--bounded','--mapped','--top','SpinorInteger'],
 'select-mapped':['test_fp_select.py','--compact','--mapped'],
 'select-deep-mapped':['test_fp_select.py','--compact','--mapped','--top','RamVectorFp16'],
}
def run(item):
    name,args=item;path=OUT/(name+'.log');start=time.monotonic()
    with path.open('w') as log:result=subprocess.run([py,'tests/'+args[0],*args[1:]],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    print(name,result.returncode,flush=True)
    return name,dict(args=args,exit_code=result.returncode,seconds=round(time.monotonic()-start,2),log=str(path.relative_to(ROOT)))
ledger={}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for name,row in pool.map(run,jobs.items()):
        ledger[name]=row;(OUT/'results.json').write_text(json.dumps(ledger,indent=2)+'\n')
assert len(ledger)==len(jobs) and all(r['exit_code']==0 for r in ledger.values()),'See M50 feature logs'
