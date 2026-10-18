#!/usr/bin/env python3
"""Portable context acceptance on unchanged M52 public production tops."""
import argparse,json,subprocess,sys
from report_m53 import ROOT,TOPS,baseline_check
from report_m51 import check

def run(*args):
    print('+',' '.join(args),flush=True)
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args()
    baseline_check()
    if a.check_only:
        check(json.loads((ROOT/'reports/m53/receipt.json').read_text()))
        print('PASS current M53 context and unchanged M50/M51/M52 evidence');return
    for top in TOPS:run('tests/test_context_image.py','--top',top)
    run('scripts/check_context_cross_compile.py')
    run('scripts/check_timing_gate.py','--spinor','build/timing-budget/m50-spinor/budget.json',
        '--compute','build/timing-budget/m50-compute/budget.json','--output','build/timing-budget/m53-gate/results.json')
    run('scripts/report_m53.py')
if __name__=='__main__':main()
