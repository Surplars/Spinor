#!/usr/bin/env python3
"""Freeze Lishi M7 evidence without inheriting old implementation timing claims."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m7';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
def cycles(text):return int(re.search(r'cycles=(\d+)',text)[1])
units=[read('build/test/integer-divide-'+s+'.json') for s in ['rtl','mapped']]
for u in units:assert u['status']=='PASS' and u['checks']==2894 and u['flushes']==270
latency=read('build/test/integer-divide-latency.json');assert len(latency)==16
for key,value in latency.items():assert value==[4*(8<<int(key.split(':')[0]))+8]
integer=read('build/test/m7-div-results.json');vector=read('build/test/m7-div-fp-results.json')
for data,models in [(integer,['RamVector','RamVector16','RamVectorFlops']),(vector,['RamVectorFp'])]:
 assert data['commands']==1673
 for field in ['multiply_forms','divide_forms']:
  assert len(data['coverage'][field])==8 and set(data['coverage'][field].values())=={22}
 assert data['coverage']['divide_flushes']==12 and data['coverage']['multiply_flushes']==9
 for name in models:assert 'PASS ram-vector commands=1673 reads=5126' in data['models'][name]
smoke=read('build/test/m7-div-fp-smoke-results.json')
assert smoke['commands']==200 and set(smoke['coverage']['divide_forms'].values())=={3}
for name in ['RamVectorFp','RamVectorFp-mapped']:assert 'PASS ram-vector commands=200 reads=410' in smoke['models'][name]
assert cycles(smoke['models']['RamVectorFp'])==cycles(smoke['models']['RamVectorFp-mapped'])
fp=read('build/test/fp-vector-m7-mixed-results.json')
assert fp['status']=='PASS' and fp['commands']==1681 and fp['coverage']['multiply_interleave']==8 and fp['coverage']['divide_interleave']==8
assert fp['coverage']['flushes']==102 and fp['coverage']['context_write_flush']==2 and fp['write_stage_assertions_enabled']
old=read('archive/m6/reports/receipt.json')
for top in ['FloatingPointLane','IntegerMultiply']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==old['artifact_sha256'][rel],top
cone=read('build/test/write-cone.json');assert cone['status']=='PASS'
summary=read('build/synth/RamVectorFp/summary.json');cells=summary['mapped_cells']
assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==5
paths=read('build/synth/RamVectorFp/paths.json');divpaths=read('build/synth/IntegerDivide/paths.json')
assert paths['longest_data']['hops']<=16
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[p for p in (ROOT/'build/rtl').rglob('*.sv')]
artifacts += [ROOT/n for n in ['build/test/integer-divide-rtl.json','build/test/integer-divide-mapped.json','build/test/integer-divide-latency.json',
 'build/test/m7-div-results.json','build/test/m7-div-fp-results.json','build/test/m7-div-fp-smoke-results.json',
 'build/test/fp-vector-m7-mixed-results.json','build/test/write-cone.json',
 'build/synth/RamVectorFp/summary.json','build/synth/RamVectorFp/paths.json','build/synth/RamVectorFp/mapped.v',
 'build/synth/IntegerDivide/summary.json','build/synth/IntegerDivide/paths.json','build/synth/IntegerDivide/mapped.v',
 'archive/m6/reports/receipt.json']]
for test,rtl in [('integer-divide-rtl.json','build/rtl/IntegerDivide.sv'),
 ('integer-divide-mapped.json','build/synth/IntegerDivide/mapped.v'),
 ('m7-div-results.json','build/rtl/RamVector.sv'),
 ('m7-div-fp-results.json','build/rtl/RamVectorFp.sv'),
 ('m7-div-fp-smoke-results.json','build/synth/RamVectorFp/mapped.v'),
 ('fp-vector-m7-mixed-results.json','build/rtl/RamVectorFp.sv')]:
 assert (ROOT/'build/test'/test).stat().st_mtime >= (ROOT/rtl).stat().st_mtime,test
for p in artifacts:
 if p.suffix=='.json' and p.name!='receipt.json':
  shutil.copy2(p,OUT/(p.parent.name+'-'+p.name if p.parent.name in ['IntegerDivide','RamVectorFp'] else p.name))
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M7',status='CLOUD_FUNCTIONAL_AND_STRUCTURAL_CHECKS_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},
 artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 vector_RTL_test=vector,integer_RTL_test=integer,vector_mapped_smoke_test=smoke,
 unit_tests=units,accept_to_output_latency=latency,mixed_fp_multiply_divide_test=fp,
 unchanged_unit_evidence=dict(scope='REUSED_M6_UNIT_TESTS_BY_EXACT_STANDALONE_RTL_SHA_NOT_RERUN',
  prior_receipt_sha256=sha(ROOT/'archive/m6/reports/receipt.json'),
  integer_multiply_tests=old['unit_tests'],fp_regression=old['fp_regression']),
 mapped_resources=summary,data_hops=paths['longest_data']['hops'],divider_data_hops=divpaths['longest_data']['hops'],
 mapped_integration_scope='200-command representative SEW8/32/64 LMUL1; all22 legal configurations checked in current RTL; allSEW divider arithmetic checked mapped',
 M7_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['widening multiply/multiply-accumulate','LSU','FP conversions','full RVV','Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['project'],receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')),'DSP',cells['DSP48E2'])
