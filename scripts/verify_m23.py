#!/usr/bin/env python3
"""Cold M23 reproduction; preserved numerical-unit evidence is rebuilt too."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
py=sys.executable
run('make','rtl');run('make','fp-bootstrap')
for proof in ['prove_increment.py','prove_mask_prefix.py','prove_round.py','prove_recode.py','prove_divider_word.py']:run(py,'scripts/'+proof)
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:
 shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'tests/test_index_generate.py');run(py,'tests/test_index_generate.py','--smoke')
for top in ['RamVector','RamVector16']:run(py,'tests/test_index_generate.py','--smoke','--top',top)
run(py,'tests/test_mask_prefix.py');run(py,'tests/test_mask_prefix.py','--smoke')
for top in ['RamVector','RamVector16']:run(py,'tests/test_mask_prefix.py','--smoke','--top',top)
for test in ['test_mask_scalar.py','test_mask_scan.py','test_reductions.py','test_streaming.py','test_reduction_interleave.py']:run(py,'tests/'+test)
run(py,'tests/test_ram_vector.py','--fp','--multiply','--divide');run(py,'tests/test_ram_vector.py')
run(py,'tests/test_fp_vector.py','--convert','--multiply','--divide')
run(py,'tests/test_vector_memory.py')
run(py,'tests/test_monitored_memory.py','--spinor');run(py,'tests/test_monitored_memory.py','--spinor','--smoke')
run(py,'tests/test_monitor.py');run(py,'tests/test_monitor.py','--tiny');run(py,'tests/test_monitor_client.py')
# The report SHA-checks warm evidence; a fresh checkout recreates it here.
run(py,'tests/test_fp_lane.py');run(py,'tests/test_fp_lane.py','--smoke');run(py,'tests/test_fp_convert.py');run(py,'tests/test_integer_divide.py')
run(py,'tests/performance.py','--baseline','archive/m22/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv',
 '--baseline-label','M22','--current-label','M23','--output','build/performance-m23')
tops=['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
run(py,'scripts/synth.py',*tops);run(py,'scripts/path_depth.py',*tops)
run(py,'tests/test_index_generate.py','--smoke','--mapped')
run(py,'tests/test_mask_prefix.py','--smoke','--mapped');run(py,'tests/test_reduction_interleave.py','--mapped')
run(py,'tests/test_monitored_memory.py','--spinor','--smoke','--mapped');run(py,'tests/test_monitor.py','--mapped')
run(py,'tests/test_fp_lane.py','--smoke','--mapped');run(py,'tests/test_integer_divide.py','--mapped')
run(py,'scripts/rapidwright_probe.py');run(py,'scripts/prepare_m23_baseline.py')
for top,path,label in [('SpinorVpu','build/baseline-m22/SpinorVpu.json','m22-baseline'),
 ('SpinorVpu','build/synth/SpinorVpu/mapped.json','m23-spinor'),('LishiVpuMemory','build/synth/LishiVpuMemory/mapped.json','m23-compute')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',path,'--output','build/timing-budget/'+label)
run(py,'scripts/report_m23.py')
