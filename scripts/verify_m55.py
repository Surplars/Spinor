#!/usr/bin/env python3
"""Isolated M55 acceptance against current RTL, preserving historical artifacts."""
import argparse,json,subprocess,sys
from m55_baseline import ROOT,audit
from report_m55 import TOPS,checked
def run(*args):
    print('+',' '.join(map(str,args)),flush=True);subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def py(*args):run(sys.executable,*args)
def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args();audit()
    if a.check_only:
        checked(json.loads((ROOT/'reports/m55/receipt.json').read_text()));print('PASS current M55 bound evidence');return
    for top in ['IntegerLaneBaseline','IntegerLaneSplit','IntegerLaneSplit16','SpinorVpu','LishiVpuMemory','RamVectorFp','RamVectorFp16']:
        run(ROOT/'mill','Vpu.runMain','vpu.GenerateM55','build/m55/rtl',top)
    for top in TOPS:py('scripts/emit_gsim_m55.py','--top',top)
    for top,preset in [('SpinorStandard','standard'),('SpinorInteger','integer')]:
        run(ROOT/'mill','Vpu.runMain','vpu.GenerateConfigured','--out','build/m55/configured','--name',top,'--preset',preset)
    py('scripts/bootstrap_m55_references.py')
    py('scripts/synth_m55.py','SpinorVpu','LishiVpuMemory','IntegerLaneSplit','IntegerLaneSplit16')
    for top,label in [('SpinorVpu','spinor'),('LishiVpuMemory','compute')]:
        py('scripts/cloud_budget.py','--top',top,'--netlist',f'build/m55/synth/{top}/mapped.json','--output','build/m55/timing/'+label)
    py('scripts/check_timing_gate.py','--spinor','build/m55/timing/spinor/budget.json','--compute','build/m55/timing/compute/budget.json','--output','build/m55/timing/gate/results.json')
    py('tests/test_m55_lane.py');py('tests/test_m55_lane.py','--mapped');py('scripts/prove_m55_bits.py')
    for top in ['RamVectorFp','RamVectorFp16']:py('tests/test_fp_resize_m55.py','--compact','--top',top)
    # Generate Zvbb corpus once before any possible parallel consumers.
    for top in TOPS:
        for suite in ['arithmetic','memory','edges']+(['half'] if 'Integer' not in top else [])+['zvbb']:
            args=['tests/test_gsim_m55.py','--top',top,'--suite',suite]
            if 'Deep' in top and suite in ['arithmetic','memory']:args.append('--compact')
            py(*args)
        for script in ['test_gsim_reserved_m55.py','test_m55_public_checks.py','test_context_image_m55.py','test_m55_restart.py','test_m55_flush.py']:py('tests/'+script,'--top',top)
    py('scripts/check_m55_compiler.py');py('scripts/report_m55.py')
    checked(json.loads((ROOT/'reports/m55/receipt.json').read_text()))
if __name__=='__main__':main()
