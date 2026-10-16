#!/usr/bin/env python3
"""M18 functional/SoC reference verification; no actual CPU or Vivado required."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*a):subprocess.run([str(x) for x in a],cwd=ROOT,check=True)
py=sys.executable
run('make','rtl')
run('make','fp-bootstrap')
run(ROOT/'mill','Vpu.runMain','vpu.GenerateHostBoundary','build/rtl/VpuHostBoundary.sv')
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:
 shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'tests/test_reductions.py')
run(py,'tests/test_reductions.py','--smoke')
run(py,'tests/test_reduction_interleave.py')
for top in ['RamVector','RamVector16']:run(py,'tests/test_reductions.py','--smoke','--top',top)
run(py,'tests/test_ram_vector.py','--fp','--multiply','--divide')
run(py,'tests/test_ram_vector.py')
run(py,'tests/test_fp_vector.py','--convert','--multiply','--divide')
run(py,'tests/test_streaming.py')
run(py,'tests/test_vector_memory.py');run(py,'tests/test_vector_memory.py','--smoke')
run(py,'tests/test_host_boundary.py')
run(py,'tests/test_monitor.py');run(py,'tests/test_monitor.py','--tiny')
run(py,'tests/test_monitored_memory.py','--spinor')
run(py,'tests/test_monitored_memory.py','--spinor','--smoke')
run(py,'tests/performance.py','--baseline','archive/m17/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv','--baseline-label','M17','--current-label','M18','--output','build/performance-m18')
tops=['RamVectorFp','LishiVpuMemory','SpinorVpu','VpuHostBoundary','VpuMonitor']
run(py,'scripts/synth.py',*tops);run(py,'scripts/path_depth.py',*tops)
run(py,'tests/test_reductions.py','--smoke','--mapped')
run(py,'tests/test_reduction_interleave.py','--mapped')
run(py,'tests/test_vector_memory.py','--smoke','--mapped')
run(py,'tests/test_host_boundary.py','--mapped')
run(py,'tests/test_monitor.py','--mapped')
run(py,'tests/test_monitored_memory.py','--spinor','--smoke','--mapped')
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/base-test','0xa0010000')
run(py,'tests/test_monitor.py','--base','0xa0010000','--rtl-dir','build/monitor/base-test')
run(py,'tests/test_monitor_client.py')
run(py,'scripts/rapidwright_probe.py')
run(py,'scripts/cloud_budget.py','--top','LishiVpuMemory','--netlist','archive/m17/synth-LishiVpuMemory/mapped.json','--output','build/timing-budget/m17-baseline')
for top,label in [('LishiVpuMemory','m18'),('SpinorVpu','spinor-m18')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',f'build/synth/{top}/mapped.json','--output',f'build/timing-budget/{label}')
run(py,'scripts/report_m18.py')
