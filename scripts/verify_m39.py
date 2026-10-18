#!/usr/bin/env python3
"""Cold M39 reproduction; all reused numerical/proof evidence is rebuilt."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
py=sys.executable
run('make','rtl');run('make','fp-bootstrap')
for proof in ['prove_increment.py','prove_mask_prefix.py','prove_round.py','prove_unrecode.py','prove_recode.py','prove_divider_word.py']:run(py,'scripts/'+proof)
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'scripts/generate_profiles.py');run(py,'tests/test_configuration.py');run(py,'scripts/regress_m39.py')
run(py,'tests/test_fp_widen_lane.py');run(py,'tests/test_fp_widen_lane.py','--smoke')
run(py,'tests/test_fp_lane.py');run(py,'tests/test_fp_lane.py','--smoke');run(py,'tests/test_fp_convert.py');run(py,'tests/test_integer_divide.py')
run(py,'tests/performance.py','--baseline','archive/m38/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv',
 '--baseline-label','M38','--current-label','M39','--output','build/performance-m39')
tops=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','RamVectorFp16','IntegerMultiplyFractional','FixedPointLane','RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
run(py,'scripts/synth.py',*tops);run(py,'scripts/path_depth.py',*tops)
run(py,'scripts/regress_m39.py','--mapped','--jobs','2')
run(py,'tests/test_fp_widen_lane.py','--smoke','--mapped');run(py,'tests/test_fp_lane.py','--smoke','--mapped');run(py,'tests/test_integer_divide.py','--mapped')
run(py,'scripts/rapidwright_probe.py');run(py,'scripts/prepare_m26_baseline.py')
run(py,'scripts/cloud_budget.py','--top','SpinorVpu','--netlist','build/baseline-m25/SpinorVpu.json','--output','build/timing-budget/m25-baseline')
run(py,'tests/test_cloud_budget.py');run(py,'scripts/prepare_m39_baseline.py')
for top,path,label in [('SpinorVpu','build/baseline-m38/SpinorVpu.json','m38-baseline'),('SpinorVpu','build/synth/SpinorVpu/mapped.json','m39-spinor'),('LishiVpuMemory','build/synth/LishiVpuMemory/mapped.json','m39-compute')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',path,'--output','build/timing-budget/'+label)
run(py,'scripts/check_timing_gate.py','--spinor','build/timing-budget/m39-spinor/budget.json','--compute','build/timing-budget/m39-compute/budget.json','--output','build/timing-budget/m39-gate/results.json')
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist','build/synth/'+top+'/mapped.json','--output','build/timing-budget/m39-'+top)
run(py,'scripts/report_m39.py')
