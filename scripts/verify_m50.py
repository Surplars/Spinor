#!/usr/bin/env python3
"""Reproduce M50 hardware, independent ISA comparison and fixed cloud gate."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];py=sys.executable
TOPS=['VpuHostBoundary','VectorMemoryEngine','LishiVpuMemory16','FloatingPointEstimate','FloatingPointConvertResize','FloatingPointLaneResize','FloatingPointLaneWiden','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','RamVectorFp16','IntegerMultiplyFractional','FixedPointLane','RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
def proof_valid(name):
    p=ROOT/f'build/{name}/results.json'
    if not p.exists():return False
    d=json.loads(p.read_text());inputs={k:v for key in ['input_sha256','source_sha256','sha256'] for k,v in d.get(key,{}).items()}
    return d.get('status')=='PASS' and bool(inputs) and all((ROOT/k).is_file() and hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in inputs.items())

def main():
    run('make','rtl');run('make','fp-bootstrap')
    for script in ['bootstrap_fp_widen.py','bootstrap_fp_resize.py','bootstrap_spike.py']:run(py,'scripts/'+script)
    # Generate emits the public VPU but not the standalone monitor variants.
    run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
    for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:
        shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
    run(py,'scripts/generate_profiles.py');run(py,'tests/test_configuration.py')
    run(py,'scripts/check_m50_regeneration.py');run(py,'scripts/synth_m48.py',*TOPS)
    run(py,'scripts/rapidwright_probe.py');run(py,'scripts/prepare_m26_baseline.py');run(py,'scripts/prepare_m50_baseline.py')
    for label,netlist in [('m25-baseline','build/baseline-m25/SpinorVpu.json'),('m40-baseline','build/baseline-m40/SpinorVpu.json')]:
        run(py,'scripts/cloud_budget.py','--top','SpinorVpu','--netlist',netlist,'--output','build/timing-budget/'+label)
    run(py,'tests/test_cloud_budget.py')
    for top,label in [('SpinorVpu','spinor'),('LishiVpuMemory','compute'),*[(t,t) for t in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']],('VpuHostBoundary','host')]:
        run(py,'scripts/cloud_budget.py','--top',top,'--netlist',f'build/synth/{top}/mapped.json','--output',f'build/timing-budget/m50-{label}')
    run(py,'scripts/check_timing_gate.py','--spinor','build/timing-budget/m50-spinor/budget.json','--compute','build/timing-budget/m50-compute/budget.json','--output','build/timing-budget/m50-gate/results.json')
    # The M50 core differs from the frozen M42 input: arithmetic reuse must miss.
    run(py,'scripts/regress_m50.py','--jobs','3')
    for name,script in [('memory-geometry-proof','prove_memory_geometry.py'),('increment-proof','prove_increment.py'),('mask-prefix-proof','prove_mask_prefix.py'),('round-proof','prove_round.py'),('unrecode-proof','prove_unrecode.py'),('recode-proof','prove_recode.py'),('divider-proof','prove_divider_word.py')]:
        if not proof_valid(name):run(py,'scripts/'+script)
    for args in [('test_fp_lane.py',),('test_fp_lane.py','--smoke'),('test_fp_convert.py',),('test_integer_divide.py',)]:run(py,'tests/'+args[0],*args[1:])
    run(py,'tests/performance.py','--baseline','archive/m40/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv','--baseline-label','M40','--current-label','M50','--output','build/performance-m50')
    run(py,'scripts/regress_m50.py','--mapped','--jobs','3')
    run(py,'tests/test_fp_lane.py','--smoke','--mapped');run(py,'tests/test_integer_divide.py','--mapped')
    run(py,'scripts/regress_m50_features.py')
    run(py,'tests/test_spike_differential_negative.py')
    run(py,'tests/test_spike_fp_select.py');run(py,'tests/test_spike_fp_select.py','--mapped')
    run(py,'scripts/bootstrap_program.py');run(py,'scripts/regress_m49.py')
    run(py,'scripts/report_m50.py')

if __name__=='__main__':main()
