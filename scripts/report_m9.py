#!/usr/bin/env python3
"""Freeze tested same-width conversions and the independent TL reservation."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m9';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((ROOT/n).read_text())
old=read('archive/m8/reports/receipt.json')
unchanged={}
for top in ['IntegerMultiply','IntegerDivide','RamVector','RamVector16','RamVectorFlops']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==old['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel)
conversions=[]
for label,count,flush,rtl in [('rtl',5021,492,'build/rtl/FloatingPointConvert.sv'),
 ('lane',5019,492,'build/rtl/FloatingPointLane.sv'),('mapped',5021,60,'build/synth/FloatingPointConvert/mapped.v')]:
 d=read(f'build/test/fp-convert-{label}-results.json')
 assert d['status']=='PASS' and d['vectors']==count and d['flush_reset_cases']==flush and d['conversion_anchors']==14
 assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl)
 assert d['testbench_sha256']==sha(ROOT/f'build/test/fp-convert-{label}-tb.sv')
 conversions.append(d)
tl=[]
for label,rtl in [('rtl','build/rtl/TileLinkReservation.sv'),('mapped','build/synth/TileLinkReservation/mapped.v'),
 ('wrapper','build/rtl/LishiVpuTileLinkReserved.sv')]:
 d=read(f'build/test/tilelink-{label}-results.json');assert d['status']=='PASS' and d['coverage']['transactions']==600
 assert d['coverage']==dict(transactions=600,local_rejects=36,same_cycle_D=112,flush_cases=459,protocol_errors=41)
 assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl);tl.append(d)
fp=read('build/test/fp-lane-results.json');assert fp['status']=='PASS' and fp['vectors']==6811 and fp['flush_reset_cases']==205
vector=read('build/test/fp-vector-m9-convert-results.json')
assert vector['status']=='PASS' and vector['commands']==2157 and vector['coverage']['conversions']==270
assert vector['coverage']['flushes']==196 and vector['coverage']['context_write_flush']==2 and vector['write_stage_assertions_enabled']
integer=read('build/test/m7-div-fp-results.json');assert integer['commands']==1673 and 'cycles=284054' in integer['models']['RamVectorFp']
stream=read('build/test/streaming-rtl.json');assert stream['status']=='PASS' and stream['commands']==251
assert stream['rtl_or_netlist_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
cone=read('build/test/write-cone.json');assert cone['status']=='PASS'
summaries={n:read('build/synth/'+n+'/summary.json') for n in ['FloatingPointConvert','TileLinkReservation','RamVectorFp']}
paths={n:read('build/synth/'+n+'/paths.json') for n in summaries}
assert paths['RamVectorFp']['longest_data']['hops']<=16 and paths['FloatingPointConvert']['longest_data']['hops']<=15
cells=summaries['RamVectorFp']['mapped_cells'];assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==6
source=[p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
source += [ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
artifacts=[p for p in (ROOT/'build/rtl').rglob('*.sv')]
artifacts += [ROOT/n for n in ['build/test/fp-convert-rtl-results.json','build/test/fp-convert-lane-results.json','build/test/fp-convert-mapped-results.json',
 'build/test/fp-lane-results.json','build/test/fp-vector-m9-convert-results.json','build/test/m7-div-fp-results.json',
 'build/test/tilelink-rtl-results.json','build/test/tilelink-mapped-results.json','build/test/tilelink-wrapper-results.json',
 'build/test/streaming-rtl.json','build/test/write-cone.json','tools/fp/libfp-reference.so',
 'archive/m8/reports/receipt.json']]
for top in summaries:
 for n in ['summary.json','paths.json','mapped.v']:artifacts.append(ROOT/f'build/synth/{top}/{n}')
for result,rtl in [('fp-lane-results.json','build/rtl/FloatingPointLane.sv'),('fp-vector-m9-convert-results.json','build/rtl/RamVectorFp.sv'),
 ('m7-div-fp-results.json','build/rtl/RamVectorFp.sv')]:
 assert (ROOT/'build/test'/result).stat().st_mtime >= (ROOT/rtl).stat().st_mtime,result
for p in artifacts:
 if p.suffix=='.json' and p.name!='receipt.json':
  target=OUT/(p.parent.name+'-'+p.name if p.parent.name in summaries else p.name);shutil.copy2(p,target)
artifacts += [p for folder in [OUT,ROOT/'reports/cloud-m5'] for p in folder.rglob('*') if p.is_file() and p.name!='receipt.json']
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M9',status='CLOUD_CONVERSIONS_TILELINK_AND_STRUCTURAL_CHECKS_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 conversion_tests=conversions,tilelink_tests=tl,FP_lane_test=fp,vector_conversion_test=vector,integer_test=integer,streaming_test=stream,
 unchanged_execution_and_integer_top_RTL=unchanged,prior_receipt_sha256=sha(ROOT/'archive/m8/reports/receipt.json'),
 resources=summaries,paths=paths,TileLink_scope='INDEPENDENT_ONE_SOURCE_A_D_BRIDGE_AND_RESERVATION_WRAPPER; EXTERNAL_MEMORY_REQUEST; NO_VECTOR_LSU',
 mapping_test_scope='CONVERSION_UNIT_AND_TL_BRIDGE; NO_FULL_CORE_MAPPED_CONVERSION_REGRESSION',
 M9_Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 physical_baseline='M5 only; reports/cloud-m5/evaluation.md',
 missing_features=['vector LSU','translation/PMP/coherence and precise memory faults','widen/narrow conversions','FP32/64 cross-format conversion','full RVV','actual Valence core integration'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('logic LUT',sum(v for k,v in cells.items() if k.startswith('LUT')),'FF',sum(v for k,v in cells.items() if k.startswith('FD')))
