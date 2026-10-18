#!/usr/bin/env python3
"""Direct GSIM/Spike acceptance, reusing exactly unchanged M50/M51 hardware."""
import argparse,json,subprocess,sys
from report_m52 import ROOT,TOPS,baseline_check
from report_m51 import check

def run(*args):
    print('+',' '.join(args),flush=True);subprocess.run([sys.executable,*args],cwd=ROOT,check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args();baseline_check()
    if a.check_only:
        check(json.loads((ROOT/'reports/m52/receipt.json').read_text()));print('PASS current M52 evidence');return
    for top in TOPS:run('scripts/emit_gsim_m52.py','--top',top)
    for top in TOPS:
        for suite in ['arithmetic','memory','edges']:
            args=['tests/test_gsim_spike.py','--top',top,'--suite',suite]
            if 'Deep' in top and suite!='edges':args.append('--compact')
            run(*args)
        run('tests/test_gsim_reserved_eew.py','--top',top)
    run('tests/test_gsim_spike.py','--suite','edges-bounded')
    run('tests/test_spike_memory_edges_rtl.py');run('scripts/check_spike_reserved_policy.py')
    run('scripts/check_timing_gate.py','--spinor','build/timing-budget/m50-spinor/budget.json','--compute','build/timing-budget/m50-compute/budget.json','--output','build/timing-budget/m52-gate/results.json')
    run('scripts/report_m52.py')
if __name__=='__main__':main()
