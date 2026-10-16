#!/usr/bin/env python3
"""Reproduce the optional SoC-monitor add-on using the M17 tool installation."""
import shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
py=sys.executable
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for top in ['VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:
 shutil.copy2(ROOT/f'build/monitor/rtl/{top}.sv',ROOT/f'build/rtl/{top}.sv')
run(py,'tests/test_monitor.py');run(py,'tests/test_monitor.py','--tiny')
run(py,'tests/test_monitored_memory.py')
run(py,'tests/test_monitored_memory.py','--smoke')
run(py,'scripts/synth.py','VpuMonitor','LishiVpuMonitored')
run(py,'tests/test_monitor.py','--mapped')
run(py,'tests/test_monitored_memory.py','--smoke','--mapped')
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/base-test','0xa0010000')
run(py,'tests/test_monitor.py','--base','0xa0010000','--rtl-dir','build/monitor/base-test')
run(py,'tests/test_monitor_client.py')
run(py,'scripts/path_depth.py','VpuMonitor','LishiVpuMonitored')
run(py,'scripts/cloud_budget.py','--top','LishiVpuMonitored','--netlist','build/synth/LishiVpuMonitored/mapped.json','--output','build/timing-budget/monitored')
run(py,'scripts/report_monitor.py')
