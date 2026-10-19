#!/usr/bin/env python3
"""Reexecute the ISA audit or check immutable current evidence."""
import argparse
import json
import subprocess
import sys
from m57_evidence import ROOT, check, baseline


def run(*args):
    print('+', ' '.join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    baseline()
    if a.check_only:
        d = json.loads((ROOT/'reports/m57/receipt.json').read_text())
        assert d['status'] == 'PASS' and not d['hardware_changed'] and d['new_DUT_executions']
        check(d)
        print('PASS current M57 bound evidence')
        return
    run('tests/m57_isa_catalog.py')
    # Sequential preparation protects the immutable shared expected fixtures.
    run('tests/test_m57_state.py', '--prepare-only')
    run('tests/test_m57_memory_forms.py', '--prepare-only')
    for top in ('SpinorStandard', 'SpinorDeep'):
        for sew in ('8', '16', '32', '64'):
            run('tests/test_m57_decode.py', '--top', top, '--sew', sew)
        for script in ('state', 'memory_forms', 'reserved'):
            run('tests/test_m57_'+script+'.py', '--top', top)
    run('scripts/report_m57.py')


if __name__ == '__main__':
    main()
