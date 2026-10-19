#!/usr/bin/env python3
"""Execute M60 production-port tests, or audit the exact retained evidence."""
import argparse
import json
import subprocess
import sys
from m60_evidence import ROOT, baseline, check


def run(*args):
    print('+', ' '.join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--check-only', action='store_true'); a = p.parse_args()
    baseline()
    if a.check_only:
        d = json.loads((ROOT/'reports/m60/receipt.json').read_text())
        assert d['status'] == 'PASS' and not d['hardware_changed']; check(d)
        print('PASS current M60 exact source/artifact bindings'); return
    for sew in (8, 16, 32, 64):
        run('tests/test_m60_restart.py', '--sew', str(sew), '--prepare-only')
        for top in ('SpinorStandard', 'SpinorDeep'):
            run('tests/test_m60_restart.py', '--sew', str(sew), '--top', top)
    run('scripts/m60_clauses.py'); run('scripts/m60_act_intake.py'); run('scripts/report_m60.py')


if __name__ == '__main__': main()
