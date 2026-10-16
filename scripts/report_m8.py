#!/usr/bin/env python3
"""Freeze checked element overlap and cycle performance, without clock signoff."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m8';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
def cycles(s):return int(re.search(r'cycles=(\d+)',s)[1])
old=read('archive/m7/reports/receipt.json')
for top in ['FloatingPointLane','IntegerMultiply','IntegerDivide']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==old['artifact_sha256'][rel],top
assert sha(ROOT/'archive/m7/rtl/RamVectorFp.sv')==old['artifact_sha256']['build/rtl/RamVectorFp.sv']
integer=read('build/test/m7-div-results.json');vector=read('build/test/m7-div-fp-results.json')
for data,models in [(integer,['RamVector','RamVector16','RamVectorFlops']),(vector,['RamVectorFp'])]:
 assert data['commands']==1673
 for name in models:assert 'PASS ram-vector commands=1673 reads=5126' in data['models'][name]
 for f in ['multiply_forms','divide_forms']:assert len(data['coverage'][f])==8 and set(data['coverage'][f].values())=={22}
smoke=read('build/test/m7-div-fp-smoke-results.json');assert smoke['commands']==200
assert cycles(smoke['models']['RamVectorFp'])==cycles(smoke['models']['RamVectorFp-mapped'])
stream=[read('build/test/streaming-'+s+'.json') for s in ['rtl','mapped']]
for s,count,flush,rtl in zip(stream,[251,73],[102,13],['build/rtl/RamVectorFp.sv','build/synth/RamVectorFp/mapped.v']):
 assert s['status']=='PASS' and s['commands']==count and s['flushes']==flush
 assert s['rtl_or_netlist_sha256']==sha(ROOT/rtl)
 name='streaming-mapped' if s['mapped'] else 'streaming-rtl'
 assert s['testbench_sha256']==sha(ROOT/f'build/test/{name}-tb.sv')
assert int(re.search(r'max_inflight=(\d+)',stream[0]['trace'])[1])>=2
assert int(re.search(r'overlap_rw=(\d+)',stream[0]['trace'])[1])>0
fp=read('build/test/fp-vector-m7-mixed-results.json')
assert fp['status']=='PASS' and fp['commands']==1681 and fp['write_stage_assertions_enabled']
assert fp['coverage']['multiply_interleave']==8 and fp['coverage']['divide_interleave']==8 and fp['coverage']['flushes']==102
perf=read('build/performance/results.json')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
for label,path in [('M7','archive/m7/rtl/RamVectorFp.sv'),('M8','build/rtl/RamVectorFp.sv')]:
 assert perf['results'][label]['rtl_sha256']==sha(ROOT/path) and len(perf['results'][label]['cases'])==220
cone=read('build/test/write-cone.json');assert cone['status']=='PASS'
summary=read('build/synth/RamVectorFp/summary.json');cells=summary['mapped_cells']
assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==6
paths=read('build/synth/RamVectorFp/paths.json');assert paths['longest_data']['hops']<=16
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[p for p in (ROOT/'build/rtl').rglob('*.sv')]
artifacts += [ROOT/n for n in ['build/test/m7-div-results.json','build/test/m7-div-fp-results.json','build/test/m7-div-fp-smoke-results.json',
 'build/test/fp-vector-m7-mixed-results.json','build/test/write-cone.json','build/test/streaming-rtl.json','build/test/streaming-mapped.json',
 'build/test/streaming-rtl-tb.sv','build/test/streaming-mapped-tb.sv',
 'build/synth/RamVectorFp/summary.json','build/synth/RamVectorFp/paths.json','build/synth/RamVectorFp/mapped.v',
 'archive/m7/reports/receipt.json','archive/m7/rtl/RamVectorFp.sv',
 'build/performance/results.json','build/performance/performance-tb.sv','build/performance/M7.log','build/performance/M8.log']]
for test,rtl in [('m7-div-results.json','build/rtl/RamVector.sv'),('m7-div-fp-results.json','build/rtl/RamVectorFp.sv'),
 ('m7-div-fp-smoke-results.json','build/synth/RamVectorFp/mapped.v'),('fp-vector-m7-mixed-results.json','build/rtl/RamVectorFp.sv')]:
 assert (ROOT/'build/test'/test).stat().st_mtime >= (ROOT/rtl).stat().st_mtime,test
for p in artifacts:
 if p.suffix=='.json' and p.name!='receipt.json':
  name='performance-results.json' if p.parent.name=='performance' else 'mapped-'+p.name if p.parent.name=='RamVectorFp' else p.name
  shutil.copy2(p,OUT/name)
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M8',status='CLOUD_FUNCTIONAL_STRUCTURAL_AND_CYCLE_PERFORMANCE_CHECKS_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 vector_RTL_test=vector,integer_RTL_test=integer,vector_mapped_smoke_test=smoke,streaming_tests=stream,
 mixed_fp_multiply_divide_test=fp,performance_cases_per_version=220,
 unchanged_unit_evidence=dict(scope='REUSED_M7_UNIT_EVIDENCE_BY_EXACT_STANDALONE_RTL_SHA_NOT_RERUN',prior_receipt_sha256=sha(ROOT/'archive/m7/reports/receipt.json')),
 mapped_resources=summary,data_hops=paths['longest_data']['hops'],M8_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 concurrency='ONE_INSTRUCTION; MULTIPLE_ELEMENTS_FOR_BASIC_INTEGER_NON_MASK_RESULTS; FP_MUL_DIV_MASK_RESULTS_SERIAL',
 physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['widening multiply/multiply-accumulate','LSU','FP conversions','full RVV','Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')))
