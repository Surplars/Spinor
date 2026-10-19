#!/usr/bin/env python3
"""Replay independent numeric cases against the production models, or audit hashes."""
import argparse
import json
import subprocess
import sys
from m58_evidence import ROOT,baseline,check


def run(*args):
    print('+',' '.join(args),flush=True);subprocess.run([sys.executable,*args],cwd=ROOT,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args()
    baseline()
    if a.check_only:
        d=json.loads((ROOT/'reports/m58/receipt.json').read_text());assert d['status']=='PASS' and not d['hardware_changed'];check(d)
        print('PASS current M58 bound evidence');return
    for policy in range(4):run('tests/test_m58_policies.py','--policy',str(policy),'--prepare-only')
    run('tests/test_m58_recovery.py','--prepare-only')
    for top in ('SpinorStandard','SpinorDeep'):
        for policy in range(4):run('tests/test_m58_policies.py','--policy',str(policy),'--top',top)
        run('tests/test_m58_recovery.py','--top',top)
    run('scripts/m58_clauses.py');run('scripts/report_m58.py')


if __name__=='__main__':main()
