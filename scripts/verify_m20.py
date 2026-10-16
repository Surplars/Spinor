#!/usr/bin/env python3
"""M20 functional, mapping and conditional timing reproduction; no device STA."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
py=sys.executable
run('make','rtl');run('make','fp-bootstrap')
for proof in ['prove_round.py','prove_recode.py','prove_divider_word.py']:run(py,'scripts/'+proof)
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:
 shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'tests/test_mask_scalar.py')
run(py,'tests/test_mask_scan.py');run(py,'tests/test_mask_scan.py','--smoke')
for top in ['RamVector','RamVector16']:run(py,'tests/test_mask_scan.py','--smoke','--top',top)
run(py,'tests/test_fp_lane.py');run(py,'tests/test_fp_lane.py','--smoke');run(py,'tests/test_fp_convert.py')
run(py,'tests/test_integer_divide.py')
run(py,'tests/test_reductions.py')
run(py,'tests/test_ram_vector.py','--fp','--multiply','--divide');run(py,'tests/test_ram_vector.py')
run(py,'tests/test_fp_vector.py','--convert','--multiply','--divide')
run(py,'tests/test_streaming.py');run(py,'tests/test_reduction_interleave.py')
run(py,'tests/test_vector_memory.py')
run(py,'tests/test_monitored_memory.py','--spinor');run(py,'tests/test_monitored_memory.py','--spinor','--smoke')
run(py,'tests/test_monitor.py');run(py,'tests/test_monitor.py','--tiny');run(py,'tests/test_monitor_client.py')
run(py,'tests/performance.py','--baseline','archive/m19/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv',
 '--baseline-label','M19','--current-label','M20','--output','build/performance-m20')
tops=['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
run(py,'scripts/synth.py',*tops);run(py,'scripts/path_depth.py',*tops)
run(py,'tests/test_mask_scan.py','--smoke','--mapped');run(py,'tests/test_fp_lane.py','--smoke','--mapped')
run(py,'tests/test_integer_divide.py','--mapped')
run(py,'tests/test_reduction_interleave.py','--mapped')
run(py,'tests/test_monitored_memory.py','--spinor','--smoke','--mapped');run(py,'tests/test_monitor.py','--mapped')
run(py,'scripts/rapidwright_probe.py')
for top,path,label in [('SpinorVpu','archive/m19/synth-SpinorVpu/mapped.json','m19-baseline'),
 ('SpinorVpu','build/synth/SpinorVpu/mapped.json','m20-spinor'),('LishiVpuMemory','build/synth/LishiVpuMemory/mapped.json','m20-compute')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',path,'--output','build/timing-budget/'+label)
run(py,'scripts/report_m20.py')
