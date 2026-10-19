#!/usr/bin/env python3
"""Run the independently referenced public-port M59 matrix or audit its bindings."""
import argparse
import json
import subprocess
import sys
from m59_evidence import ROOT, baseline, check


def run(*args):
    print('+', ' '.join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    baseline()
    if a.check_only:
        d = json.loads((ROOT / 'reports/m59/receipt.json').read_text())
        assert d['status'] == 'PASS' and not d['hardware_changed']
        check(d)
        print('PASS current M59 exact source/artifact bindings')
        return
    for sew in (8, 16, 32, 64):
        run('tests/test_m59_arch.py', '--sew', str(sew), '--crosscheck-only')
        run('tests/test_m59_arch.py', '--sew', str(sew), '--prepare-only')
        for top in ('SpinorStandard', 'SpinorDeep'):
            run('tests/test_m59_arch.py', '--sew', str(sew), '--top', top)
    run('scripts/m59_clauses.py')
    run('scripts/report_m59.py')


if __name__ == '__main__': main()
