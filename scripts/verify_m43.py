#!/usr/bin/env python3
"""Cold full reproduction; unchanged published M42 arithmetic evidence may be SHA-reused."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];py=sys.executable
def run(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
def proof_valid(name):
 p=ROOT/f'build/{name}/results.json'
 if not p.exists():return False
 d=json.loads(p.read_text());inputs={k:v for key in ['input_sha256','source_sha256','sha256'] for k,v in d.get(key,{}).items()}
 return d.get('status')=='PASS' and bool(inputs) and all((ROOT/k).is_file() and hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in inputs.items())
run(py,'tests/test_evidence_reuse.py');run('make','rtl');run(py,'scripts/check_regeneration.py');run('make','fp-bootstrap');run(py,'scripts/bootstrap_fp_widen.py');run(py,'scripts/bootstrap_fp_resize.py')
run(ROOT/'mill','Vpu.runMain','vpu.GenerateMonitor','build/monitor/rtl')
for name in ['SpinorVpu','VpuMonitor','VpuMonitorTiny','LishiVpuMonitored']:shutil.copy2(ROOT/f'build/monitor/rtl/{name}.sv',ROOT/f'build/rtl/{name}.sv')
run(py,'scripts/generate_profiles.py');run(py,'tests/test_configuration.py');run(py,'scripts/regress_m43.py','--jobs','4')
for name,script in [('increment-proof','prove_increment.py'),('mask-prefix-proof','prove_mask_prefix.py'),('round-proof','prove_round.py'),('unrecode-proof','prove_unrecode.py'),('recode-proof','prove_recode.py'),('divider-proof','prove_divider_word.py')]:
 if not proof_valid(name):run(py,'scripts/'+script)
cache=json.loads((ROOT/'build/m43-regression/reuse-inputs.json').read_text())['cache_available']
if not cache:
 for args in [('test_fp_lane.py',),('test_fp_lane.py','--smoke'),('test_fp_convert.py',),('test_integer_divide.py',)]:run(py,'tests/'+args[0],*args[1:])
run(py,'tests/performance.py','--baseline','archive/m40/rtl/RamVectorFp.sv','--current','build/rtl/RamVectorFp.sv','--baseline-label','M40','--current-label','M43','--output','build/performance-m43')
tops=['VectorMemoryEngine','LishiVpuMemory16','FloatingPointEstimate','FloatingPointConvertResize','FloatingPointLaneResize','FloatingPointLaneWiden','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','RamVectorFp16','IntegerMultiplyFractional','FixedPointLane','RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
run(py,'scripts/synth_m43.py',*tops);run(py,'scripts/regress_m43.py','--mapped','--jobs','4')
if not cache:run(py,'tests/test_fp_lane.py','--smoke','--mapped');run(py,'tests/test_integer_divide.py','--mapped')
run(py,'scripts/rapidwright_probe.py');run(py,'scripts/prepare_m26_baseline.py')
run(py,'scripts/cloud_budget.py','--top','SpinorVpu','--netlist','build/baseline-m25/SpinorVpu.json','--output','build/timing-budget/m25-baseline')
run(py,'tests/test_cloud_budget.py');run(py,'scripts/prepare_m43_baseline.py')
for top,path,label in [('SpinorVpu','build/baseline-m40/SpinorVpu.json','m40-baseline'),('SpinorVpu','build/synth/SpinorVpu/mapped.json','m43-spinor'),('LishiVpuMemory','build/synth/LishiVpuMemory/mapped.json','m43-compute')]:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist',path,'--output','build/timing-budget/'+label)
run(py,'scripts/check_timing_gate.py','--spinor','build/timing-budget/m43-spinor/budget.json','--compute','build/timing-budget/m43-compute/budget.json','--output','build/timing-budget/m43-gate/results.json')
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
 run(py,'scripts/cloud_budget.py','--top',top,'--netlist','build/synth/'+top+'/mapped.json','--output','build/timing-budget/m43-'+top)
run(py,'scripts/report_m43.py')
