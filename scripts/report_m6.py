#!/usr/bin/env python3
"""Freeze evidence for the cloud-screened integer multiply milestone."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m6';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
unit=[read('build/test/integer-multiply-'+s+'.json') for s in ['rtl','mapped']]
for u in unit:assert u['status']=='PASS' and u['checks']==2734 and u['flushes']==110
integer=read('build/test/m6-multiply-vector-results.json');vector=read('build/test/m6-multiply-fp-vector-results.json')
for data,models in [(integer,['RamVector','RamVector16','RamVectorFlops']),(vector,['RamVectorFp','RamVectorFp-mapped'])]:
 assert data['commands']==1231 and len(data['coverage']['multiply_forms'])==8
 assert set(data['coverage']['multiply_forms'].values())=={22}
 assert data['coverage']['multiply_flushes']==9
 for name in models:assert 'PASS ram-vector commands=1231 reads=4044' in data['models'][name]
assert re.search(r'cycles=(\d+)',vector['models']['RamVectorFp'])[1]==re.search(r'cycles=(\d+)',vector['models']['RamVectorFp-mapped'])[1]
fp=read('build/test/fp-vector-results.json');assert fp['status']=='PASS' and fp['commands']==1649
assert fp['coverage']['flushes']==102 and fp['coverage']['context_write_flush']==2 and fp['write_stage_assertions_enabled']
mixed=read('build/test/fp-vector-multiply-results.json');assert mixed['status']=='PASS' and mixed['commands']==1665 and mixed['coverage']['multiply_interleave']==8
assert sha(ROOT/'build/rtl/FloatingPointLane.sv')==read('archive/m5/reports/m5-tested-rtl-sha256.json')['build/rtl/FloatingPointLane.sv']
cone=read('build/test/write-cone.json');assert cone['status']=='PASS'
summary=read('build/synth/RamVectorFp/summary.json');cells=summary['mapped_cells']
assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==5
paths=read('build/synth/RamVectorFp/paths.json');mulpaths=read('build/synth/IntegerMultiply/paths.json')
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[p for p in (ROOT/'build/rtl').rglob('*.sv')]
artifacts += [ROOT/n for n in ['build/test/integer-multiply-rtl.json','build/test/integer-multiply-mapped.json','build/test/integer-multiply-latency.json',
 'build/test/m6-multiply-vector-results.json','build/test/m6-multiply-fp-vector-results.json',
 'build/test/fp-vector-results.json','build/test/fp-vector-multiply-results.json','build/test/write-cone.json',
 'build/synth/RamVectorFp/summary.json','build/synth/RamVectorFp/paths.json','build/synth/RamVectorFp/mapped.v',
 'build/synth/IntegerMultiply/summary.json','build/synth/IntegerMultiply/paths.json','build/synth/IntegerMultiply/mapped.v']]
# Evidence must postdate the exact RTL/mapping it claims to exercise.
for test,rtl in [('integer-multiply-rtl.json','build/rtl/IntegerMultiply.sv'),
 ('integer-multiply-mapped.json','build/synth/IntegerMultiply/mapped.v'),
 ('m6-multiply-vector-results.json','build/rtl/RamVector.sv'),
 ('m6-multiply-fp-vector-results.json','build/synth/RamVectorFp/mapped.v'),
 ('fp-vector-results.json','build/rtl/RamVectorFp.sv')]:
 assert (ROOT/'build/test'/test).stat().st_mtime >= (ROOT/rtl).stat().st_mtime,test
for p in artifacts:
 if p.suffix=='.json' and p.name!='mapped.json':shutil.copy2(p,OUT/(p.parent.name+'-'+p.name if p.parent.name in ['IntegerMultiply','RamVectorFp'] else p.name))
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(milestone='M6',status='CLOUD_FUNCTIONAL_AND_STRUCTURAL_CHECKS_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},
 artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 vector_test=vector,integer_test=integer,unit_tests=unit,fp_regression=fp,mixed_fp_multiply_regression=mixed,
 mapped_resources=summary,data_hops=paths['longest_data']['hops'],multiplier_data_hops=mulpaths['longest_data']['hops'],
 M6_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['integer divide/remainder','widening multiply/multiply-accumulate','LSU','FP conversions','full RVV','Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')),'DSP',cells['DSP48E2'])
