#!/usr/bin/env python3
"""Rebuild current host acceptance; historical baselines stay immutable."""
import argparse,gzip,hashlib,json,subprocess,sys
from m56_baseline import ROOT,audit
from report_m56 import TOPS,checked
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):print('+',' '.join(map(str,args)),flush=True);subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def py(*args):run(sys.executable,*args)
def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');a=p.parse_args();audit()
    if a.check_only:checked(json.loads((ROOT/'reports/m56/receipt.json').read_text()));print('PASS current M56 bound evidence');return
    names=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']
    for top in names+TOPS+['LishiVpuMemoryHost']:run(ROOT/'mill','Vpu.runMain','vpu.GenerateM56','build/m56/rtl',top)
    rows=[]
    for top in names:
        archived=ROOT/f'archive/m55/pre-m56-rtl/{top}.sv.gz';after=ROOT/f'build/m56/rtl/{top}.sv';raw=gzip.decompress(archived.read_bytes());assert raw==after.read_bytes(),top
        before=ROOT/f'build/m56/baseline-rtl/{top}.sv';before.parent.mkdir(exist_ok=True,parents=True);before.write_bytes(raw)
        rows.append(dict(top=top,before=str(before.relative_to(ROOT)),after=str(after.relative_to(ROOT)),sha256=sha(before),archive=str(archived.relative_to(ROOT)),archive_sha256=sha(archived)))
    (ROOT/'build/m56/default-identity.json').write_text(json.dumps(dict(status='PASS',comparison='BYTE_IDENTICAL_SYSTEMVERILOG',tops=rows),indent=2)+'\n')
    for top in TOPS:py('scripts/emit_gsim_m56.py','--top',top)
    py('scripts/synth_m56.py','SpinorHost','LishiVpuMemoryHost')
    for top,label in [('SpinorHost','spinor'),('LishiVpuMemoryHost','compute')]:py('scripts/cloud_budget_m56.py','--top',top,'--netlist',f'build/m56/synth/{top}/mapped.json.gz','--output',f'build/m56/timing/{label}')
    py('scripts/check_timing_gate_m56.py','--spinor','build/m56/timing/spinor/budget.json','--compute','build/m56/timing/compute/budget.json','--output','build/m56/timing/gate/results.json')
    for top in TOPS:
        for script in ['test_m56_fcsr.py','test_m56_memory.py','test_context_image_m56.py','test_m56_flush.py','test_m56_diel.py']:py('tests/'+script,'--top',top)
    py('scripts/check_m56_configuration.py');py('scripts/report_m56.py');checked(json.loads((ROOT/'reports/m56/receipt.json').read_text()))
if __name__=='__main__':main()
