#!/usr/bin/env python3
"""Freeze FP input staging, numerical regressions and conditional timing budgets."""
import csv,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m14';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
old=read('archive/m9/reports/receipt.json');unchanged={}
for top in ['IntegerDivide','TileLinkReservation']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==old['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel)
tests=[]
for label,cases,stops,combinations,path in [('rtl',222,77,78,'build/rtl/LishiVpuMemory.sv'),
 ('smoke',62,9,6,'build/rtl/LishiVpuMemory.sv'),('mapped',62,9,6,'build/synth/LishiVpuMemory/mapped.v')]:
 t=read(f'build/test/vector-memory-{label}-results.json')
 assert t['status']=='PASS' and (t['memory_cases'],t['stop_cases'],t['eew_emul_combinations'])==(cases,stops,combinations)
 assert t['rtl_or_netlist_sha256']==sha(ROOT/path)
 assert t['testbench_sha256']==sha(ROOT/f'build/test/vector-memory-{label}-tb.sv')
 if label!='mapped':assert t['assertions_enabled']
 tests.append(t)
assert tests[1]['summary']==tests[2]['summary']
assert tests[1]['metrics']==tests[2]['metrics']
oldrows=list(csv.DictReader((ROOT/'archive/m13/reports/memory-performance.csv').open()))
newrows=list(csv.DictReader((OUT/'memory-performance.csv').open()))
assert len(oldrows)==len(newrows)==24
for before,after in zip(oldrows,newrows):
 for key in ['case','service_wait','eew','vl','write','requests','bytes']:assert before[key]==after[key]
 assert int(after['cycles'])<=int(before['cycles'])
 metrics={m['case']:m for m in tests[0]['metrics']}
 assert int(after['cycles'])==metrics[int(after['case'])]['cycles']

for case in tests[0]['benchmark_cases']:assert tests[0]['context_reads'][str(case['case'])]==18

summaries={n:read('build/synth/'+n+'/summary.json') for n in ['IntegerMultiply','FloatingPointConvert','FloatingPointLane','LishiVpuMemory']}
paths={n:read('build/synth/'+n+'/paths.json') for n in summaries}
cells=summaries['LishiVpuMemory']['mapped_cells'];assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==6
assert paths['LishiVpuMemory']['longest_data']['hops']<=13 and paths['FloatingPointLane']['longest_data']['hops']<=14
budgetTest=read('build/test/cloud-budget-results.json');assert budgetTest['status']=='PASS'
for name,expected in budgetTest['source_sha256'].items():assert sha(ROOT/name)==expected
fpTests=[]
for label in ['fp-lane','fp-lane-smoke','fp-lane-mapped','fp-convert-lane','fp-vector-m9-convert']:
 t=read('build/test/'+label+'-results.json');assert t['status']=='PASS'
 top='RamVectorFp' if label.startswith('fp-vector') else 'FloatingPointLane'
 path=f'build/synth/{top}/mapped.v' if label=='fp-lane-mapped' else f'build/rtl/{top}.sv'
 assert t['rtl_or_netlist_sha256']==sha(ROOT/path)
 tb='build/test/'+label+'-tb.sv';assert t['testbench_sha256']==sha(ROOT/tb)
 fpTests.append(t)
assert fpTests[0]['vectors']==6811 and fpTests[0]['flush_reset_cases']==205
assert fpTests[1]['vectors']==fpTests[2]['vectors']==385
assert fpTests[1]['observed_latency_cycles']==fpTests[2]['observed_latency_cycles']
assert fpTests[1]['test_summary']==fpTests[2]['test_summary']
assert fpTests[3]['vectors']==5019 and fpTests[4]['commands']==2157
baselineBudget=read('build/timing-budget/m13-baseline/budget.json');currentBudget=read('build/timing-budget/m14/budget.json')
for budget in [baselineBudget,currentBudget]:
 assert budget['input_sha256']['scripts/cloud_budget.py']==sha(ROOT/'scripts/cloud_budget.py')
 for name,expected in budget['input_sha256'].items():assert sha(ROOT/name)==expected
 assert budget['passes_300MHz'] is None and budget['passes_500MHz'] is None
for a,b in zip(baselineBudget['scenarios'],currentBudget['scenarios']):
 assert a['assumed_link_ps']==b['assumed_link_ps'] and b['worst']['budget_ns']<a['worst']['budget_ns']
assert sha(ROOT/'build/rtl/VectorMemoryEngine.sv')==read('archive/m13/reports/receipt.json')['artifact_sha256']['build/rtl/VectorMemoryEngine.sv']
arithmeticTests=[]
for label in ['integer-multiply-rtl','integer-multiply-mapped','fp-convert-rtl','fp-convert-mapped']:
 suffix='.json' if label.startswith('integer') else '-results.json'
 t=read('build/test/'+label+suffix);assert t['status']=='PASS'
 top='IntegerMultiply' if label.startswith('integer') else 'FloatingPointConvert'
 path=f'build/synth/{top}/mapped.v' if label.endswith('mapped') else f'build/rtl/{top}.sv'
 assert t['rtl_or_netlist_sha256']==sha(ROOT/path)
 tb='build/test/integer-multiply-tb.sv' if label.startswith('integer') else 'build/test/'+label+'-tb.sv'
 assert t['testbench_sha256']==sha(ROOT/tb)
 assert t.get('checks',t.get('vectors'))==(2734 if label.startswith('integer') else 5021)
 arithmeticTests.append(t)
assert arithmeticTests[2]['latency']==arithmeticTests[3]['latency']
latencies=read('build/test/integer-multiply-latency.json');assert len(latencies)==16
for key,value in latencies.items():
 sew,op=map(int,key.split(':'));assert value==[[7,7,25,97][sew]+(0 if op==20 else 4)]
integerVector=read('build/test/m7-div-fp-results.json');assert integerVector['commands']==1673
assert integerVector['input_sha256']['RamVectorFp']['rtl']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert integerVector['input_sha256']['RamVectorFp']['testbench']==sha(ROOT/'build/test/m7-div-fp-tb.sv')
proof=read('build/recode-proof/results.json');assert proof['status']=='PASS'
for name,expected in proof['input_sha256'].items():assert sha(ROOT/name)==expected
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[ROOT/'build/test/cloud-budget-results.json',ROOT/'build/test/integer-multiply-tb.sv',ROOT/'build/test/integer-multiply-latency.json',ROOT/'build/test/integer-multiply-latency-tb.sv']+[p for p in (ROOT/'build/rtl').rglob('*.sv')]
for label in ['integer-multiply-rtl','integer-multiply-mapped']:
 for suffix in ['.json','.log']:artifacts.append(ROOT/('build/test/'+label+suffix))
for label in ['fp-convert-rtl','fp-convert-mapped']:
 for suffix in ['-results.json','-tb.sv','.log']:artifacts.append(ROOT/('build/test/'+label+suffix))
artifacts += [ROOT/'build/test/m7-div-fp-results.json',ROOT/'build/test/m7-div-fp-tb.sv',ROOT/'build/test/RamVectorFp.log']
for p in (ROOT/'build/recode-proof').iterdir():
 if p.is_file():shutil.copy2(p,OUT/('recode-'+p.name));artifacts.append(p)
for label in ['rtl','smoke','mapped']:
 for suffix in ['-results.json','-tb.sv','.log']:artifacts.append(ROOT/f'build/test/vector-memory-{label}{suffix}')
for label in ['rtl','smoke']:
 for module in ['VectorMemoryEngine','RamVectorFpMemory']:artifacts.append(ROOT/f'build/test/vector-memory-{label}-{module}-assert.sv')
for label in ['fp-lane','fp-lane-smoke','fp-lane-mapped','fp-convert-lane','fp-vector-m9-convert']:
 for suffix in ['-results.json','-tb.sv','.log']:artifacts.append(ROOT/('build/test/'+label+suffix))
for label in ['m13-baseline','m14']:
 for name in ['budget.json','budget.md']:
  original=ROOT/('build/timing-budget/'+label+'/'+name);target=OUT/(label+'-'+name);shutil.copy2(original,target);artifacts.append(original)
artifacts += [ROOT/'archive/m13/synth-LishiVpuMemory/mapped.json',ROOT/'build/synth/LishiVpuMemory/mapped.json']
for top in summaries:
 for n in ['summary.json','paths.json','mapped.v']:artifacts.append(ROOT/f'build/synth/{top}/{n}')
artifacts += [ROOT/'archive/m9/reports/receipt.json',ROOT/'archive/m13/reports/receipt.json',ROOT/'archive/m13/reports/memory-performance.csv']
for p in artifacts:
 if p.name in ["budget.json","mapped.json"]:continue
 if (p.suffix in ['.json','.log'] or p.name.endswith('-tb.sv') or p.name.endswith('-assert.sv')) and p.name!='receipt.json':
  target=OUT/(p.parent.name+'-'+p.name if p.parent.name in summaries else p.name);shutil.copy2(p,target)
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M14',status='CLOUD_MULTIPLY_AND_RECODE_TIMING_SCREEN_AND_SAT_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 memory_tests=tests,fp_tests=fpTests,arithmetic_tests=arithmeticTests,integer_latency_cycles=latencies,integer_vector=integerVector,recode_equivalence=proof,conditional_timing_budget=currentBudget,prior_conditional_timing_budget=baselineBudget,resources=summaries,paths=paths,unchanged_M9_RTL=unchanged,
 reused_M9_receipt_sha256=sha(ROOT/'archive/m9/reports/receipt.json'),
 memory_scope='PHYSICAL_IDEMPOTENT_NORMAL_RAM; UNIT_STRIDE; SINGLE_OUTSTANDING; PER_ELEMENT_PREFIX_COMMIT',
 flush_contract='MEMORY_STOP_IS_DEFERRED; HOST_MUST_RETAIN_TOKEN_AND_ACCEPT_COMPLETION_STATUS; ISSUED_STORES_NOT_ROLLBACKABLE',
 core_integration='NO_ACTUAL_VALENCE_INTEGRATION; HOST_TRANSLATION_PMP_COHERENCE_TRAPS_AND_DIRTY_STATE_NOT_IMPLEMENTED',
 performance_scope='REGISTERED_MEMORY_MODEL_ONLY; 24_CASES; OPTIONAL_300MHz_SCALING_NOT_MEASURED_FREQUENCY',
 M14_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['MMIO','translation/PMP/coherence','segments/strided/indexed/FOF','actual CPU precise trap/interrupt integration','full RVV','Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')))
