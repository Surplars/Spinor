#!/usr/bin/env python3
"""Isolated current-hardware M54 acceptance; preserve accepted historical inputs."""
import argparse,json,subprocess,sys
from m54_baseline import ROOT,audit
from report_m54 import TOPS,checked
def run(*args):
    print('+',' '.join(map(str,args)),flush=True);subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def py(*args):run(sys.executable,*args)
def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args();audit()
    if a.check_only:
        checked(json.loads((ROOT/'reports/m54/receipt.json').read_text()));print('PASS current M54 bound evidence');return
    for top in ['FloatingPointConvertResize','SpinorVpu','LishiVpuMemory','RamVectorFp','RamVectorFp16']:
        run(ROOT/'mill','Vpu.runMain','vpu.GenerateM54','build/m54/rtl',top)
    for top in TOPS:py('scripts/emit_gsim_m54.py','--top',top)
    for top,preset in [('SpinorStandard','standard'),('SpinorInteger','integer')]:
        run(ROOT/'mill','Vpu.runMain','vpu.GenerateConfigured','--out','build/m54/configured','--name',top,'--preset',preset)
    py('scripts/bootstrap_m54_references.py');py('scripts/bootstrap_m54_resize.py')
    py('scripts/synth_m54.py','SpinorVpu','LishiVpuMemory','FloatingPointConvertResize')
    for top,label in [('SpinorVpu','spinor'),('LishiVpuMemory','compute')]:
        py('scripts/cloud_budget.py','--top',top,'--netlist',f'build/m54/synth/{top}/mapped.json','--output','build/m54/timing/'+label)
    py('scripts/check_timing_gate.py','--spinor','build/m54/timing/spinor/budget.json','--compute','build/m54/timing/compute/budget.json','--output','build/m54/timing/gate/results.json')
    py('tests/test_m54_half_unit.py');py('tests/test_m54_half_unit.py','--mapped');py('scripts/prove_half_round.py')
    py('tests/test_fp_resize_m54.py');py('tests/test_fp_resize_m54.py','--compact','--top','RamVectorFp16')
    for top in TOPS:
        for suite in ['arithmetic','memory','edges']+(['half'] if 'Integer' not in top else []):
            args=['tests/test_gsim_m54.py','--top',top,'--suite',suite]
            if 'Deep' in top and suite in ['arithmetic','memory']:args.append('--compact')
            py(*args)
        py('tests/test_gsim_reserved_m54.py','--top',top);py('tests/test_m54_public_checks.py','--top',top);py('tests/test_context_image_m54.py','--top',top)
    py('scripts/check_m54_compiler.py');py('scripts/report_m54.py')
if __name__=='__main__':main()
