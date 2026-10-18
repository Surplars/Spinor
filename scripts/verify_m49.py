#!/usr/bin/env python3
"""Reuse exact M48 execution evidence, or rebuild it, then run the M49 matrix."""
import json
import subprocess
import sys
from pathlib import Path
from m49_evidence import base_evidence

ROOT=Path(__file__).resolve().parents[1]
py=sys.executable
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)

try:
    _,reuse=base_evidence()
except (AssertionError,FileNotFoundError):
    print('M48 execution evidence unavailable; rebuilding the full prerequisite matrix',flush=True)
    run(py,'scripts/verify_m48.py')
    _,reuse=base_evidence()
print('PASS M48 prerequisite evidence',json.dumps(reuse),flush=True)
run(py,'tests/test_m49_evidence.py')
run(py,'scripts/bootstrap_program.py')
run(py,'scripts/check_m49_regeneration.py')
for top,label in [('SpinorVpu','spinor'),('LishiVpuMemory','compute'),('SpinorStandard','SpinorStandard'),('SpinorDeep','SpinorDeep'),('SpinorInteger','SpinorInteger'),('SpinorIntegerDeep','SpinorIntegerDeep'),('VpuHostBoundary','host')]:
    run(py,'scripts/cloud_budget.py','--top',top,'--netlist',f'build/synth/{top}/mapped.json','--output',f'build/timing-budget/m49-{label}')
run(py,'scripts/check_timing_gate.py','--spinor','build/timing-budget/m49-spinor/budget.json','--compute','build/timing-budget/m49-compute/budget.json','--output','build/timing-budget/m49-gate/results.json')
run(py,'scripts/regress_m49.py')
run(py,'scripts/report_m49.py')
