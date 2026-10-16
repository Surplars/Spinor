#!/usr/bin/env python3
"""Freeze physical normal-RAM LSU proof; preserve arithmetic and clock boundaries."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m10';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
old=read('archive/m9/reports/receipt.json');unchanged={}
for top in ['RamVectorFp','FloatingPointLane','FloatingPointConvert','IntegerMultiply','IntegerDivide','TileLinkReservation','LishiVpuTileLinkReserved']:
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
summaries={n:read('build/synth/'+n+'/summary.json') for n in ['VectorMemoryEngine','LishiVpuMemory']}
paths={n:read('build/synth/'+n+'/paths.json') for n in summaries}
cells=summaries['LishiVpuMemory']['mapped_cells'];assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==6
assert paths['LishiVpuMemory']['longest_data']['hops']<=16 and paths['VectorMemoryEngine']['longest_data']['hops']<=12
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[p for p in (ROOT/'build/rtl').rglob('*.sv')]
for label in ['rtl','smoke','mapped']:
 for suffix in ['-results.json','-tb.sv','.log']:artifacts.append(ROOT/f'build/test/vector-memory-{label}{suffix}')
for label in ['rtl','smoke']:
 for module in ['VectorMemoryEngine','RamVectorFp']:artifacts.append(ROOT/f'build/test/vector-memory-{label}-{module}-assert.sv')
for top in summaries:
 for n in ['summary.json','paths.json','mapped.v']:artifacts.append(ROOT/f'build/synth/{top}/{n}')
artifacts += [ROOT/'archive/m9/reports/receipt.json']
for p in artifacts:
 if p.suffix=='.json' and p.name!='receipt.json':
  target=OUT/(p.parent.name+'-'+p.name if p.parent.name in summaries else p.name);shutil.copy2(p,target)
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M10',status='CLOUD_VECTOR_MEMORY_CLOSED_LOOP_AND_STRUCTURAL_CHECKS_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 memory_tests=tests,resources=summaries,paths=paths,unchanged_M9_RTL=unchanged,
 reused_M9_receipt_sha256=sha(ROOT/'archive/m9/reports/receipt.json'),
 memory_scope='PHYSICAL_IDEMPOTENT_NORMAL_RAM; UNIT_STRIDE; SINGLE_OUTSTANDING; PER_ELEMENT_PREFIX_COMMIT',
 flush_contract='MEMORY_STOP_IS_DEFERRED; HOST_MUST_RETAIN_TOKEN_AND_ACCEPT_COMPLETION_STATUS; ISSUED_STORES_NOT_ROLLBACKABLE',
 core_integration='NO_ACTUAL_VALENCE_INTEGRATION; HOST_TRANSLATION_PMP_COHERENCE_TRAPS_AND_DIRTY_STATE_NOT_IMPLEMENTED',
 performance_scope='REGISTERED_MEMORY_MODEL_ONLY; 24_CASES; OPTIONAL_300MHz_SCALING_NOT_MEASURED_FREQUENCY',
 M10_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['MMIO','translation/PMP/coherence','segments/strided/indexed/FOF','actual CPU precise trap/interrupt integration','full RVV','Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')))
