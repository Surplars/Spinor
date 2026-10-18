#!/usr/bin/env python3
"""Affected verification only; reuse M50 hardware evidence after exact hashing."""
import argparse,json,subprocess,sys
from pathlib import Path
from report_m51 import ROOT,baseline,check

def run(args):
    print('+',' '.join(args),flush=True)
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args()
    baseline()
    if a.check_only:
        check(json.loads((ROOT/'reports/m51/receipt.json').read_text()));print('PASS current M51 evidence');return
    run(['scripts/bootstrap_spike_memory.py'])
    for args in [['--compact'],[],['--compact','--top','SpinorIntegerDeep']]:run(['tests/test_spike_memory.py',*args])
    run(['tests/test_spike_memory_mapped.py'])
    run(['scripts/bootstrap_gsim.py']);run(['scripts/emit_gsim.py'])
    for args in [[],['--suite','memory','--case','compact']]:run(['tests/benchmark_gsim.py',*args])
    run(['scripts/report_m51.py'])
if __name__=='__main__':main()
