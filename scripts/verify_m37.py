#!/usr/bin/env python3
"""Cold M37 reproduction; all reused numerical/proof evidence is rebuilt."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
py=sys.executable
run('make','rtl');run('make','fp-bootstrap')
for proof in ['prove_increment.py','prove_mask_prefix.py','prove_round.py','prove_unrecode.py','prove_recode.py','prove_divider_word.py']:run(py,'scripts/'+proof)
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'scripts/regress_m37.py')
run(py,'tests/test_fp_widen_lane.py');run(py,'tests/test_fp_widen_lane.py','--smoke')
run(py,'tests/test_fp_lane.py');run(py,'tests/test_fp_lane.py','--smoke');run(py,'tests/test_fp_convert.py');run(py,'tests/test_integer_divide.py')
run(py,'tests/performance.py','--baseline','archive/m36/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv',
 '--baseline-label','M36','--current-label','M37','--output','build/performance-m37')
tops=['FixedPointLane','RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
run(py,'scripts/synth.py',*tops);run(py,'scripts/path_depth.py',*tops)
run(py,'scripts/regress_m37.py','--mapped','--jobs','2')
run(py,'tests/test_fp_widen_lane.py','--smoke','--mapped');run(py,'tests/test_fp_lane.py','--smoke','--mapped');run(py,'tests/test_integer_divide.py','--mapped')
run(py,'scripts/rapidwright_probe.py');run(py,'scripts/prepare_m26_baseline.py')
run(py,'scripts/cloud_budget.py','--top','SpinorVpu','--netlist','build/baseline-m25/SpinorVpu.json','--output','build/timing-budget/m25-baseline')
run(py,'tests/test_cloud_budget.py');run(py,'scripts/prepare_m37_baseline.py')
for top,path,label in [('SpinorVpu','build/baseline-m36/SpinorVpu.json','m36-baseline'),('SpinorVpu','build/synth/SpinorVpu/mapped.json','m37-spinor'),('LishiVpuMemory','build/synth/LishiVpuMemory/mapped.json','m37-compute')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',path,'--output','build/timing-budget/'+label)
run(py,'scripts/check_timing_gate.py','--spinor','build/timing-budget/m37-spinor/budget.json','--compute','build/timing-budget/m37-compute/budget.json','--output','build/timing-budget/m37-gate/results.json')
run(py,'scripts/report_m37.py')
