#!/usr/bin/env python3
"""Bind M44 indexed LSU, efficiency, exact evidence reuse and fixed timing model."""
import hashlib,json,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m44';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
artifacts=set()
def include(p):
 f=ROOT/p;assert f.is_file(),f;artifacts.add(f)
def checked(p):
 d=read(p);assert d['status']=='PASS',p;include(p)
 for key in ['sha256','input_sha256','source_sha256']:
  for f,h in d.get(key,{}).items():assert sha(ROOT/f)==h,(p,f);include(f)
 return d
def logs(stem):
 for suffix in ['.log','-compile.log','.compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
def sim(stem,rtl,suffix='-results.json',tb=None):
 d=checked(stem+suffix);assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),stem;include(rtl)
 tb=tb or stem+'-tb.sv';assert d['testbench_sha256']==sha(ROOT/tb),stem;include(tb);logs(stem)
 return d
def same_performance(current,old,delta):
 assert len(current)==len(old)
 for x,y in zip(current,old,strict=True):
  assert x.keys()==y.keys()
  for k in x:assert x[k]==y[k]+delta if k=='cycles' else x[k]==y[k],(k,x,y)

def compare_memory(current,old):
 for now,was in zip(current['case_specs'][:len(old['case_specs'])],old['case_specs'],strict=True):
  assert all(now[k]==v for k,v in was.items()),(now,was)
 assert current['benchmark_cases']==old['benchmark_cases'] and current['stop_cases']==old['stop_cases']
 specs={r['id']:r for r in current['case_specs']};old_metrics={r['case']:r for r in old['metrics']}
 for key,value in old['context_reads'].items():
  # Hierarchical context-read instrumentation exists only in RTL simulation.
  # Mapped tests report zero here; their values/requests/cycles are checked separately.
  if not current['assertions_enabled']:
   assert current['context_reads'][key]==value==0;continue
  ident=int(key);spec=specs[ident]
  removed=(2 if not spec['masked'] and not spec['illegal'] and spec['initial_vstart']<spec['vl'] else 0)
  if spec['eew']==64 and not spec['write']:removed+=old_metrics[ident]['requests']
  assert current['context_reads'][key]==value-removed,(ident,value,current['context_reads'][key],removed)
 for now,was in zip(current['metrics'][:len(old['metrics'])],old['metrics'],strict=True):
  assert now['case']==was['case'] and now['requests']==was['requests']
 # Integrated bus stalls are phase-dependent. Exact internal savings are
 # checked by replaying identical commands on both engines with fixed service.
 return [dict(case=a['case'],old_cycles=b['cycles'],new_cycles=a['cycles']) for a,b in zip(current['metrics'],old['metrics'])]

previous42=read('archive/m42/reports/receipt.json');include('archive/m42/reports/receipt.json')
previous43=read('archive/m43/reports/receipt.json');include('archive/m43/reports/receipt.json')
base=read('archive/m40/reports/receipt.json')
frozen41=read('archive/m41/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m40/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane','FloatingPointLaneWiden','FloatingPointConvert','IntegerMultiply','FixedPointLane']:
 f=f'archive/m40/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala','IntegerMultiply.scala','FixedPointLane.scala','FloatingPointConvert.scala','StagedFloatToInt.scala']:
 f='archive/m40/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m40/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m44-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m40-baseline','m44-spinor','m44-compute']:
 budgets[label]=read('build/timing-budget/'+label+'/budget.json')
 for suffix in ['json','md']:include(f'build/timing-budget/{label}/budget.{suffix}')
 for p,h in budgets[label]['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)

def family(folder,mapped=False,all_coverage=True):
 labels=['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']
 if mapped:labels+=['RamVectorFp-smoke-mapped']
 data={}
 for label in labels:
  stem=f'build/{folder}/{label}';d=checked(stem+'-results.json');logs(stem);data[label]=d
  if all_coverage:assert all(d['coverage'].values()),(folder,label)
 if mapped:
  for key in ['commands','coverage','types','performance','summary']:
   assert data['RamVectorFp-smoke-rtl'][key]==data['RamVectorFp-smoke-mapped'][key],(folder,key)
 return data
families={folder:family(folder) for folder in ['compress','gather','slide','index-generate','mask-prefix']}
assert all(len(d['RamVectorFp-full-rtl']['types'])==22 for d in families.values())
assert families['slide']['RamVectorFp-full-rtl']['coverage']['masked_source_v0']==134
prefix=families['mask-prefix']['RamVectorFp-full-rtl'];assert prefix['commands']==2888
assert all(x['cycles']==106 for x in prefix['performance'] if x['vl']==128)
aliases={}
for label in ['RamVectorFp-rtl','RamVector-rtl','RamVector16-rtl']:
 stem='build/mask-source-alias/'+label;aliases[label]=checked(stem+'-results.json');logs(stem)
 assert aliases[label]['coverage']['legal_zero_fields']>0
fp_widening_reductions=family('fp-widening-reductions',all_coverage=False)
fp_reductions=family('fp-reductions',all_coverage=False)
for data in [fp_widening_reductions,fp_reductions]:
 for d in data.values():assert d['reference_anchors']==52 and d['coverage']['flushes']>0
 for label in ['RamVector-smoke-rtl','RamVector16-smoke-rtl']:assert data[label]['coverage']['reductions']==0
fpwide=fp_widening_reductions['RamVectorFp-full-rtl']
assert len(fpwide['by_type'])==5 and all(fpwide['coverage'].values()) and fpwide['commands']==1664
assert fpwide['coverage']['reductions']==442 and fpwide['coverage']['illegal']==194
full=fp_reductions['RamVectorFp-full-rtl']
assert full['commands']==5771 and len(full['by_type'])==9 and all(full['by_operation'].values()) and all(full['coverage'].values())
for row in full['performance']:
 if row['sew']==32 and row['vlmul']==3 and row['frm']==0:assert row['cycles']==(1230 if row['op'] in [1,3] else 302)
widening_reductions=family('widening-reductions')
wide=widening_reductions['RamVectorFp-full-rtl'];assert len(wide['by_type'])==18 and wide['commands']==1025
assert wide['coverage']['reductions']==260 and wide['coverage']['illegal']==325 and wide['coverage']['flushes']==60
fp_widen_lane={}
for label in ['rtl','smoke','mapped']:
 stem='build/fp-widen-lane/'+label;d=checked(stem+'-results.json');logs(stem);fp_widen_lane[label]=d
 assert d['extra_reference_anchors']==7 and d['base_reference_anchors']==52
assert fp_widen_lane['rtl']['vectors']==1292
for key in ['vectors','flush_reset_cases','latency','summary']:assert fp_widen_lane['smoke'][key]==fp_widen_lane['mapped'][key],key
extensions=family('integer-extensions');narrowing=family('narrowing-shifts');widening=family('widening-arithmetic')
assert extensions['RamVectorFp-full-rtl']['commands']==4212 and len(extensions['RamVectorFp-full-rtl']['types'])==15
full_narrow=narrowing['RamVectorFp-full-rtl'];assert full_narrow['commands']==4945 and len(full_narrow['types'])==15
assert full_narrow['coverage']['illegal']==1753 and full_narrow['coverage']['flush']==198
widen_full=widening['RamVectorFp-full-rtl'];assert widen_full['commands']==11926 and len(widen_full['types'])==15
assert widen_full['coverage']['illegal']==4825 and widen_full['coverage']['flush']==608
mac=family('integer-mac')
mac_netlist={}
for label in ['rtl','mapped']:
 stem='build/integer-mac-netlist/'+label;mac_netlist[label]=checked(stem+'-results.json');logs(stem)
 assert mac_netlist[label]['mac_instructions']==40 and mac_netlist[label]['flushes']==8
for key in ['commands','mac_instructions','flushes','coverage','summary']:assert mac_netlist['rtl'][key]==mac_netlist['mapped'][key]
mac_full=mac['RamVectorFp-full-rtl']
assert len(mac_full['types'])==22 and mac_full['commands']==6778
assert mac_full['coverage']['illegal']==1370 and mac_full['coverage']['flush']==512
assert {r['code'] for r in mac_full['performance']}=={0x29,0x2b,0x2d,0x2f}
assert {r['form'] for r in mac_full['performance']}=={2,6}
multiply=family('widening-multiply')
multiply_full=multiply['RamVectorFp-full-rtl']
assert multiply_full['commands']==4467 and len(multiply_full['types'])==15
assert multiply_full['coverage']['illegal']==1857 and multiply_full['coverage']['flush']==246
assert {r['code'] for r in multiply_full['performance']}=={0x38,0x3a,0x3b}
assert {r['form'] for r in multiply_full['performance']}=={2,6}
for folder,data in families.items():
 for label,d in data.items():
  old=base['families'][folder][label]
  for key in ['commands','coverage','types']:assert d[key]==old[key],(folder,label,key)
  same_performance(d['performance'],old['performance'],0)
for name,data in [('integer_mac',mac),('widening_multiply',multiply),('integer_extensions',extensions),('narrowing_shifts',narrowing),('widening_arithmetic',widening),('fp_widening_reductions',fp_widening_reductions),('fp_reductions',fp_reductions),('widening_reductions',widening_reductions)]:
 for label,d in data.items():
  old=base[name][label]
  for key in ['commands','coverage']:
   expected=old[key]
   assert d[key]==expected,(name,label,key)
  same_performance(d['performance'],old['performance'],0)
mask={}
for folder in ['mask-scalar','mask-scan']:
 stem=f'build/{folder}/RamVectorFp-full-rtl';d=checked(stem+'-results.json');logs(stem);mask[folder]=d
 for k in ['commands','coverage','types']:assert d[k]==base['mask'][folder][k],(folder,k)
 same_performance(d['performance'],base['mask'][folder]['performance'],0)
stem='build/reductions/RamVectorFp-full-rtl';red=checked(stem+'-results.json');logs(stem)
assert red['commands']==3418 and red['coverage']['masked_source_v0']==176 and red['coverage']['reductions']==1235
integer={}
for label,count,tb in [('m7-div-fp',1673,'m7-div-fp-tb.sv'),('ram-vector',789,'ram_vector_tb.sv')]:
 name='build/test/'+label+'-results.json';d=read(name);include(name);include('build/test/'+tb);assert d['commands']==count
 for top,h in d['input_sha256'].items():
  path=f'build/rtl/{top}.sv';assert h['rtl']==sha(ROOT/path),top;assert h['testbench']==sha(ROOT/'build/test'/tb),top
  assert d['models'][top].startswith('PASS ram-vector');include(path)
 integer[label]=d
fp=sim('build/test/fp-vector-m9-convert','build/rtl/RamVectorFp.sv');assert fp['commands']==2157
stream=sim('build/test/streaming-rtl','build/rtl/RamVectorFp.sv',suffix='.json');assert stream['commands']==251
mixed=[]
for label in ['rtl','mapped']:
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==89
memory=[]
for label,count in [('rtl',303),('smoke',143),('mapped',143)]:
 stem='build/test/vector-memory-'+label;rtl='build/synth/LishiVpuMemory/mapped.v' if label=='mapped' else 'build/rtl/LishiVpuMemory.sv'
 d=sim(stem,rtl);assert d['memory_cases']==count;memory.append(d)
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert memory[1]['metrics']==memory[2]['metrics']
memory_phase_changes=[compare_memory(current,old) for current,old in zip(memory,base['memory'],strict=True)]
soc=[]
for label,count in [('rtl',303),('smoke',143),('mapped',143)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=sim(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert soc[1]['metrics']==soc[2]['metrics']
public_phase_changes=[compare_memory(current,old) for current,old in zip(soc,base['spinor_integration'],strict=True)]
monitors=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped']:
 stem='build/monitor/test/'+label;d=checked(stem+'-results.json');logs(stem);assert d['cycles']==2600;monitors.append(d)
assert monitors[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert monitors[0][k]==monitors[2][k]
client=checked('build/monitor/software/results.json')
include('build/monitor/software/decoded.json')
proofs={}
for name in ['round-proof','unrecode-proof','increment-proof','mask-prefix-proof','recode-proof','divider-proof']:
 proofs[name]=checked('build/'+name+'/results.json')
 for n in ['generate.log','proof.log']:include('build/'+name+'/'+n)
units={}
for label,top,ext in [('fp-lane','FloatingPointLane','-results.json'),('fp-lane-smoke','FloatingPointLane','-results.json'),('fp-lane-mapped','FloatingPointLane','-results.json'),('fp-convert-rtl','FloatingPointConvert','-results.json'),('integer-divide-rtl','IntegerDivide','.json'),('integer-divide-mapped','IntegerDivide','.json')]:
 rtl=f'build/synth/{top}/mapped.v' if 'mapped' in label else f'build/rtl/{top}.sv'
 tb='build/test/integer-divide-tb.sv' if label.startswith('integer-divide') else None
 units[label]=sim('build/test/'+label,rtl,suffix=ext,tb=tb)
assert units['fp-lane']['vectors']==6811 and units['fp-convert-rtl']['vectors']==5021
assert units['fp-lane-smoke']['observed_latency_cycles']==units['fp-lane-mapped']['observed_latency_cycles']
# Numerical equality is checked by SoftFloat; these checks also guard the cost
# and scope of the added pipeline stages against accidental global slowdowns.
old_lat=base['numerical_units']['fp-lane']['observed_latency_cycles']
for key,lat in units['fp-lane']['observed_latency_cycles'].items():
 op=int(re.search(r'_op(\d+)',key)[1]);delta=0
 assert lat==[x+delta for x in old_lat[key]],(key,lat,old_lat[key])
unchanged={}
for top in ['IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary','FloatingPointLane','FloatingPointConvert']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m44/results.json');include('build/performance-m44/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m44/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M40']['rtl_sha256']==sha(ROOT/'archive/m40/rtl/RamVectorFp.sv')
assert perf['results']['M44']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M44']['cases'])==220
for old,new in zip(perf['results']['M40']['cases'],perf['results']['M44']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m44').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['VectorMemoryEngine','LishiVpuMemory16','RamVectorFp','SpinorVpu','LishiVpuMemory','FloatingPointLaneResize','FloatingPointConvertResize','FloatingPointEstimate','FloatingPointLaneWiden','FloatingPointLane','VpuMonitor','IntegerDivide','FixedPointLane','IntegerMultiplyFractional','RamVectorFp16','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 graph=read('build/synth/'+top+'/mapped.json')['modules'][top]
 assert dict(Counter(c['type'] for c in graph['cells'].values()))==resources[top]['mapped_cells'],top
 assert set(resources[top]['input_sha256'])=={f'build/rtl/{top}.sv','scripts/synth.py'},top
 assert set(resources[top]['netlist_sha256'])=={f'build/synth/{top}/mapped.json',f'build/synth/{top}/mapped.v'},top
 assert set(paths[top]['input_sha256'])=={f'build/synth/{top}/mapped.json','scripts/path_depth.py'},top
 for key in ['input_sha256','netlist_sha256']:
  for f,h in resources[top].get(key,{}).items():assert sha(ROOT/f)==h,(top,f);include(f)
 for f,h in paths[top]['input_sha256'].items():assert sha(ROOT/f)==h,(top,f);include(f)
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
# New full and bounded mapped suites.
wmac=family('widening-mac')
new={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped']:
 stem='build/m36-integer/'+label;new[label]=checked(stem+'-results.json');logs(stem)
 assert len(new[label]['encodings'])==17
assert len(new['RamVectorFp-full-rtl']['types'])==22
assert len(wmac['RamVectorFp-full-rtl']['types'])==15
for key in ['commands','coverage','types','encodings','performance','summary']:
 assert new['RamVectorFp-compact-rtl'][key]==new['RamVectorFp-compact-mapped'][key],key
reuse=checked('build/m44-regression/reuse-inputs.json');cache_policy=checked('build/evidence-reuse-test/results.json');assert len(cache_policy['checks'])==7;regression_counts={}
for label in ['rtl','mapped']:
 rows=read('build/m44-regression/'+label+'.json');include('build/m44-regression/'+label+'.json')
 assert sum(map(len,rows.values()))==(145 if label=='rtl' else 39),label
 flat=[row for records in rows.values() for row in records]
 regression_counts[label]=dict(total=len(flat),reused=sum(row.get('reused_from')=='M42' for row in flat),executed=sum('reused_from' not in row for row in flat))
 for row in flat:
  assert row['exit_code']==0,row;include(row['log'])
  if 'reused_from' in row:
   assert reuse['cache_available'] and row['reused_from']=='M42'
   assert sha(ROOT/row['log'])==previous42['artifact_sha256'][row['log']]
   include(row['original_ledger'])
wmfull=wmac['RamVectorFp-full-rtl'];newfull=new['RamVectorFp-full-rtl']
assert {r['code'] for r in wmfull['performance']}>={0x3c,0x3d,0x3e,0x3f}
assert wmfull['commands']==5961 and wmfull['coverage']['illegal']==2744 and wmfull['coverage']['flush']==287
assert newfull['commands']==3732 and newfull['coverage']['flush']==60
assert all(r['coverage']['flush']>0 for r in wmac.values())
# New M37 evidence is independent of the unchanged M36 architectural suites.
fixed={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped']:
 stem='build/m37-fixed/'+label;fixed[label]=checked(stem+'-results.json');logs(stem)
 assert len(fixed[label]['encodings'])==39,label
fixedfull=fixed['RamVectorFp-full-rtl']
assert len(fixedfull['types'])==22 and all(fixedfull['coverage'].values())
for key in ['commands','coverage','types','encodings','performance','summary']:
 assert fixed['RamVectorFp-compact-rtl'][key]==fixed['RamVectorFp-compact-mapped'][key],key
fixed_units={}
for label in ['full-rtl','compact-rtl','compact-mapped']:
 stem='build/fixed-point-lane/'+label;fixed_units[label]=checked(stem+'-results.json');logs(stem)
 assert fixed_units[label]['modes']==14 and fixed_units[label]['sews']==4 and fixed_units[label]['rounding_modes']==4
assert fixed_units['full-rtl']['cases']==80956
assert re.search(r'cycles=(\d+)',fixed_units['compact-rtl']['summary'])[1]==re.search(r'cycles=(\d+)',fixed_units['compact-mapped']['summary'])[1]
for k in ['cases','modes','sews','rounding_modes','flush_cases']:
 assert fixed_units['compact-rtl'][k]==fixed_units['compact-mapped'][k],k
for data in [wmfull,newfull]:assert data['commands']==base['widening_mac' if data is wmfull else 'm36_integer']['RamVectorFp-full-rtl']['commands']
for label,d in wmac.items():
 old=base['widening_mac'][label]
 for key in ['commands','coverage','types']:
  expected=old[key]
  assert d[key]==expected,('widening_mac',label,key)
 same_performance(d['performance'],old['performance'],0)
for label,d in new.items():same_performance(d['performance'],base['m36_integer'][label]['performance'],0)
for label,d in fixed.items():
 old=base['fixed_point'][label]
 for key in ['commands','coverage','types','encodings']:assert d[key]==old[key],(label,key)
 same_performance(d['performance'],old['performance'],0)
resources_table=[]
for top in ['SpinorVpu','LishiVpuMemory','RamVectorFp']:
 old=previous43['resources'][top]['mapped_cells'];c=resources[top]['mapped_cells']
 assert all(c[k]==old[k] for k in ['DSP48E2','RAM64M8','RAM32M16'])
 resources_table.append(f"| {top} | {lut(c)} ({lut(c)-lut(old):+d}) | {ff(c)} ({ff(c)-ff(old):+d}) | {c['DSP48E2']} | {c['RAM64M8']} / {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m40-baseline']['scenarios'],budgets['m44-spinor']['scenarios'],budgets['m44-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=gate['results']['SpinorVpu'];compute=gate['results']['LishiVpuMemory']
# Eight new encodings, with source-width-aware architectural and unit evidence.
fractional_clip={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped']:
 stem='build/m38-fixed/'+label;d=checked(stem+'-results.json');logs(stem);fractional_clip[label]=d
 assert len(d['encodings'])==8,label
full38=fractional_clip['RamVectorFp-full-rtl']
assert full38['commands']==3470 and len(full38['types'])==52 and all(full38['coverage'].values())
assert dict(Counter(x[0] for x in full38['types']))=={39:22,46:15,47:15}
for key in ['commands','coverage','types','encodings','performance','summary']:
 assert fractional_clip['RamVectorFp-compact-rtl'][key]==fractional_clip['RamVectorFp-compact-mapped'][key],key
clip_units={};fractional_units={}
for folder,data,cases,modes,sews in [('clip-lane',clip_units,548396,2,3),('fractional-lane',fractional_units,266726,5,4)]:
 for label in ['full-rtl','compact-rtl','compact-mapped']:
  stem='build/'+folder+'/'+label;d=checked(stem+'-results.json');logs(stem);data[label]=d
  assert d['modes']==modes and d['sews']==sews and d['rounding_modes']==4
 assert data['full-rtl']['cases']==cases
 for key in ['cases','modes','sews','rounding_modes','flush_cases']:assert data['compact-rtl'][key]==data['compact-mapped'][key],(folder,key)
 assert re.search(r'cycles=(\d+)',data['compact-rtl']['summary'])[1]==re.search(r'cycles=(\d+)',data['compact-mapped']['summary'])[1],folder
for label,d in fractional_clip.items():
 old=base['fractional_clip'][label]
 for key in ['commands','coverage','types','encodings']:assert d[key]==old[key],(label,key)
 same_performance(d['performance'],old['performance'],0)
# New architectural FP-transfer matrix, including f0 and disabled-FP rejection.
fp_transfers={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVectorFp16-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped','RamVectorFp16-compact-mapped']:
 stem='build/fp-transfers/'+label;d=checked(stem+'-results.json');logs(stem);fp_transfers[label]=d
 if label.startswith(('RamVector-','RamVector16-')):assert not d['forms'] and d['coverage']['illegal']>0
 else:
  assert len(d['forms'])==4,label
  required=set(d['coverage'])-({'cross_register','single_register_unaligned'} if 'compact' in label else set())
  assert all(d['coverage'][k] for k in required),label
full39=fp_transfers['RamVectorFp-full-rtl'];assert full39['commands']==422 and len(full39['types'])==9
for top in ['RamVectorFp','RamVectorFp16']:
 for key in ['commands','coverage','types','forms','performance','summary']:assert fp_transfers[top+'-compact-rtl'][key]==fp_transfers[top+'-compact-mapped'][key],(top,key)
# Retained transfers are re-run in the new core; no cycle/coverage relaxation.
for label,d in fp_transfers.items():
 old=base['fp_transfers'][label]
 for key in ['commands','coverage','types','forms']:assert d[key]==old[key],('fp_transfers',label,key)
 same_performance(d['performance'],old['performance'],0)
wide_fp={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVectorFp16-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped','RamVectorFp16-compact-mapped']:
 stem='build/fp-wide-arithmetic/'+label;d=checked(stem+'-results.json');logs(stem);wide_fp[label]=d
 assert d['reference_anchors']==8
 if label.startswith(('RamVector-','RamVector16-')):assert not d['encodings'] and d['commands']==91
 else:assert len(d['encodings'])==18,label
full40=wide_fp['RamVectorFp-full-rtl']
assert full40['commands']==9282 and full40['types']==[16,17,18,23]
assert all(full40['coverage'].values()) and full40['coverage']['flush']==162
for top in ['RamVectorFp','RamVectorFp16']:
 assert wide_fp[top+'-compact-rtl']['commands']==157
 for key in ['commands','coverage','types','encodings','performance','summary']:
  assert wide_fp[top+'-compact-rtl'][key]==wide_fp[top+'-compact-mapped'][key],(top,key)
wide_fp_unit={}
for label in ['full-rtl','compact-rtl','compact-mapped']:
 stem='build/fp-wide-arithmetic-lane/'+label;d=checked(stem+'-results.json');logs(stem);wide_fp_unit[label]=d
 assert d['reference_anchors']==60
assert wide_fp_unit['full-rtl']['vectors']==13718 and wide_fp_unit['full-rtl']['flush_cases']==287
assert wide_fp_unit['compact-rtl']['vectors']==495
for key in ['vectors','width_counts','flush_cases','latency','summary']:
 assert wide_fp_unit['compact-rtl'][key]==wide_fp_unit['compact-mapped'][key],key
native_fp_unit={}
for label in ['fp-native','fp-native-smoke','fp-native-mapped']:
 native_fp_unit[label]=sim('build/test/'+label,'build/synth/FloatingPointLaneWiden/mapped.v' if label.endswith('mapped') else 'build/rtl/FloatingPointLaneWiden.sv')
assert native_fp_unit['fp-native']['vectors']==6811 and native_fp_unit['fp-native']['flush_reset_cases']==205
assert native_fp_unit['fp-native']['observed_latency_cycles']==base['numerical_units']['fp-lane']['observed_latency_cycles']
for key in ['vectors','flush_reset_cases','observed_latency_cycles','test_summary']:
 assert native_fp_unit['fp-native-smoke'][key]==native_fp_unit['fp-native-mapped'][key],key
wide_fp_reference=checked('build/fp-widen-reference/results.json')
assert sha(ROOT/'tools/fp/libfp-widen-reference.so')==wide_fp_reference['wrapper_library_sha256']
assert sha(ROOT/'tools/fp/softfloat/build/Linux-x86_64-GCC/softfloat.a')==wide_fp_reference['softfloat_library_sha256']
# Existing M40 widening arithmetic remains identical in the current core.
for label,d in wide_fp.items():
 for key in ['commands','coverage','types','encodings','performance','summary']:assert d[key]==base['wide_fp'][label][key],(label,key)
resize_fp={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVectorFp16-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped','RamVectorFp16-compact-mapped']:
 stem='build/fp-resize/'+label;d=checked(stem+'-results.json');logs(stem);resize_fp[label]=d
 assert d['reference_anchors']==8
 if label.startswith(('RamVector-','RamVector16-')):assert not d['encodings'] and d['coverage']['illegal']>0
 else:assert len(d['encodings'])==15,label
full41=resize_fp['RamVectorFp-full-rtl']
assert full41['commands']==11363 and full41['types']==[8,9,10,14,15,16,17,18,23]
assert all(full41['coverage'].values()) and full41['coverage']['flush']==150
for top in ['RamVectorFp','RamVectorFp16']:
 for key in ['commands','coverage','types','encodings','performance','summary']:
  assert resize_fp[top+'-compact-rtl'][key]==resize_fp[top+'-compact-mapped'][key],(top,key)
resize_unit={}
for top in ['FloatingPointConvertResize','FloatingPointLaneResize']:
 data={}
 for label in ['full-rtl','compact-rtl','compact-mapped']:
  stem='build/fp-resize-lane/'+top+'-'+label;d=checked(stem+'-results.json');logs(stem);data[label]=d
  assert d['reference_anchors']==8
 assert data['full-rtl']['vectors']==31897 and data['full-rtl']['flush_cases']==581
 for key in ['vectors','width_counts','flush_cases','latency','summary']:assert data['compact-rtl'][key]==data['compact-mapped'][key],(top,key)
 resize_unit[top]=data
resize_native={}
for label in ['fp-resize-native','fp-resize-native-smoke','fp-resize-native-mapped']:
 resize_native[label]=sim('build/test/'+label,'build/synth/FloatingPointLaneResize/mapped.v' if label.endswith('mapped') else 'build/rtl/FloatingPointLaneResize.sv')
assert resize_native['fp-resize-native']['vectors']==6811
assert resize_native['fp-resize-native']['observed_latency_cycles']==base['numerical_units']['fp-lane']['observed_latency_cycles']
for key in ['vectors','flush_reset_cases','observed_latency_cycles','test_summary']:
 assert resize_native['fp-resize-native-smoke'][key]==resize_native['fp-resize-native-mapped'][key],key
resize_wide_unit={}
for label in ['full-rtl','compact-rtl','compact-mapped']:
 stem='build/fp-wide-arithmetic-lane/resize-'+label;d=checked(stem+'-results.json');logs(stem);resize_wide_unit[label]=d
assert resize_wide_unit['full-rtl']['vectors']==13718
for key in ['vectors','width_counts','flush_cases','latency','summary']:
 assert resize_wide_unit['compact-rtl'][key]==resize_wide_unit['compact-mapped'][key],key
for key,latency in resize_wide_unit['full-rtl']['latency'].items():
 op=int(re.search(r'_op(\d+)',key)[1]);delta=-1 if key.startswith('FP32_') and op in [21,22,25,26] and '_illegal' not in key else 0
 if op not in [23,24] or '_illegal' in key:
  assert latency==[x+delta for x in base['wide_fp_unit']['full-rtl']['latency'][key]],(key,latency,delta)
resize_reference=checked('build/fp-resize-reference/results.json')
assert sha(ROOT/'tools/fp/libfp-resize-reference.so')==resize_reference['wrapper_library_sha256']
assert sha(ROOT/'tools/fp/softfloat/build/Linux-x86_64-GCC/softfloat.a')==resize_reference['softfloat_library_sha256']
estimates={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVectorFp16-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped','RamVectorFp16-compact-mapped']:
 stem='build/fp-estimate/'+label;d=checked(stem+'-results.json');logs(stem);estimates[label]=d
 assert d['reference_anchors']==8
 if label.startswith(('RamVector-','RamVector16-')):assert not d['encodings'] and d['coverage']['illegal']>0
 else:assert d['encodings']==[4,5]
full42=estimates['RamVectorFp-full-rtl'];assert all(full42['coverage'].values())
for top in ['RamVectorFp','RamVectorFp16']:
 for key in ['commands','coverage','types','encodings','performance','summary']:
  assert estimates[top+'-compact-rtl'][key]==estimates[top+'-compact-mapped'][key],(top,key)
estimate_unit={}
for label in ['full-rtl','compact-rtl','compact-mapped']:
 stem='build/fp-estimate-lane/'+label;d=checked(stem+'-results.json');logs(stem);estimate_unit[label]=d
 assert d['table_entries_independently_checked']==256
assert resources['FloatingPointEstimate']['mapped_cells'].get('DSP48E2',0)==0
assert estimate_unit['full-rtl']['vectors']==41820 and estimate_unit['full-rtl']['flush_cases']==300
for key in ['vectors','flush_cases','latency','summary']:
 assert estimate_unit['compact-rtl'][key]==estimate_unit['compact-mapped'][key],key
efficiency=checked('build/conversion-efficiency/results.json');assert efficiency['cases']==11340
for name in ['M41','M42']:
 for suffix in ['.log','-compile.log']:include('build/conversion-efficiency/'+name+suffix)
frozen41=read('archive/m41/reports/receipt.json');include('archive/m41/reports/receipt.json')
assert sha(ROOT/'archive/m41/rtl/FloatingPointConvertResize.sv')==frozen41['artifact_sha256']['build/rtl/FloatingPointConvertResize.sv']
for row in efficiency['specs']:assert row['old_cycles']-row['new_cycles']==row['saving']>=0
strided_engine={};strided_memory={}
for label in ['full-rtl','compact-rtl','full-mapped','compact-mapped']:
 stem='build/strided-engine/'+label;d=checked(stem+'-results.json');logs(stem);strided_engine[label]=d
 assert all(d['coverage'].values())
for first,second in [('full-rtl','full-mapped'),('compact-rtl','compact-mapped')]:
 for key in ['cases','coverage','case_specs','performance','summary']:assert strided_engine[first][key]==strided_engine[second][key],key
for label in ['strided-memory-rtl','strided-memory-smoke','strided-memory16-smoke','strided-memory-mapped','strided-memory16-mapped']:
 stem='build/strided-memory/'+label
 top='LishiVpuMemory16' if 'memory16' in label else 'LishiVpuMemory'
 d=sim(stem,'build/synth/'+top+'/mapped.v' if label.endswith('mapped') else 'build/rtl/'+top+'.sv');strided_memory[label]=d
 if not label.endswith('mapped'):
  for mod in ['VectorMemoryEngine','RamVectorFpMemory16' if top.endswith('16') else 'RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
for top in ['strided-memory','strided-memory16']:
 for key in ['metrics','case_specs','stop_specs','benchmark_cases']:
  assert strided_memory[top+'-smoke'][key]==strided_memory[top+'-mapped'][key],(top,key)
lsu_efficiency=checked('build/memory-efficiency/results.json')
for version in ['M42','M44']:
 for suffix in ['.log','-compile.log']:include('build/memory-efficiency/'+version+suffix)
assert len(lsu_efficiency['cases'])==352
for spec in lsu_efficiency['cases']:
 old=lsu_efficiency['results']['M42'][str(spec['id'])];new=lsu_efficiency['results']['M44'][str(spec['id'])]
 assert old['context_reads']-new['context_reads']==spec['saved_reads']
 assert old['cycles']-new['cycles']==2*spec['saved_reads']
assert sha(ROOT/'archive/m42/rtl/VectorMemoryEngine.sv')==previous42['artifact_sha256']['build/rtl/VectorMemoryEngine.sv']
for d in soc:
 assert set(d['strided_public_bus_sequences'])=={'-43','-44'} and all(len(rows)==4 for rows in d['strided_public_bus_sequences'].values())
assert resources['VectorMemoryEngine']['mapped_cells'].get('DSP48E2',0)==0
indexed_engine={};indexed_memory={}
for label in ['full-rtl','compact-rtl','full-mapped','compact-mapped']:
 stem='build/indexed-engine/'+label;d=checked(stem+'-results.json');logs(stem);indexed_engine[label]=d
 assert all(d['coverage'].values()) and len(d['encodings'])==16
for first,second in [('full-rtl','full-mapped'),('compact-rtl','compact-mapped')]:
 for key in ['cases','encodings','geometries','coverage','case_specs','performance','summary']:assert indexed_engine[first][key]==indexed_engine[second][key],key
for label in ['indexed-memory-rtl','indexed-memory-smoke','indexed-memory16-smoke','indexed-memory-mapped','indexed-memory16-mapped']:
 stem='build/indexed-memory/'+label;top='LishiVpuMemory16' if 'memory16' in label else 'LishiVpuMemory'
 d=sim(stem,'build/synth/'+top+'/mapped.v' if label.endswith('mapped') else 'build/rtl/'+top+'.sv');indexed_memory[label]=d
 if not label.endswith('mapped'):
  for mod in ['VectorMemoryEngine','RamVectorFpMemory16' if top.endswith('16') else 'RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert indexed_memory['indexed-memory-rtl']['register_check_scope']=='ALL_32'
for label,d in indexed_memory.items():
 if label!='indexed-memory-rtl':assert d['register_check_scope']=='DATA_INDEX_GROUPS_V0_AND_GUARDS_16_23_31'
for top in ['indexed-memory','indexed-memory16']:
 for key in ['metrics','case_specs','stop_specs','benchmark_cases']:assert indexed_memory[top+'-smoke'][key]==indexed_memory[top+'-mapped'][key],(top,key)
for d in soc:assert set(d['indexed_public_bus_sequences'])=={'-45','-46'} and all(len(rows)==4 for rows in d['indexed_public_bus_sequences'].values())
assert sha(ROOT/'archive/m43/rtl/VectorMemoryEngine.sv')==previous43['artifact_sha256']['build/rtl/VectorMemoryEngine.sv']
include('archive/m43/rtl/VectorMemoryEngine.sv')
regeneration=checked('build/m44-regeneration/results.json');include('build/m44-regeneration.log')
configuration=checked('build/configuration/results.json');assert len(configuration['negative_cases'])==7
for row in configuration['negative_cases']:include(row['log'])
profiles={};profile_table=[]
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
 data={}
 for label in ['rtl','mapped']:
  stem='build/profiles/'+top+'-'+label;data[label]=checked(stem+'-results.json');logs(stem)
 assert data['rtl']['summary']==data['mapped']['summary'] and data['rtl']['commands']==data['mapped']['commands']==16
 cfg=data['rtl']['config'];assert cfg==data['mapped']['config']
 assert cfg['vlen']==128 and cfg['elen']==64 and cfg['lanes']==1 and cfg['instruction_capacity']==1
 c=resources[top]['mapped_cells'];assert c['DSP48E2']==(9 if cfg['fp32_fp64'] else 1)
 assert c['RAM64M8']==32 and c['RAM32M16']==6
 budget=read(f'build/timing-budget/m44-{top}/budget.json')
 for p,h in budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 for ext in ['json','md']:include(f'build/timing-budget/m44-{top}/budget.{ext}')
 assert budget['weights_ps']==budgets['m44-spinor']['weights_ps'] and budget['provenance']==budgets['m44-spinor']['provenance']
 assert budget['passes_300MHz'] is None and not budget['placed'] and not budget['speed_grade_calibrated']
 scenario,=[s for s in budget['scenarios'] if s['assumed_link_ps']==100]
 ns=scenario['worst']['budget_ns'];assert ns<=1000/300,(top,ns)
 profiles[top]=dict(config=cfg,tests=data,conditional_budget=budget)
 profile_table.append(f"| {top} | {'FP32/64' if cfg['fp32_fp64'] else '整数'} | {cfg['alu_stage_bits']} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {ns:.3f} |")
assert sha(ROOT/'build/rtl/SpinorStandard.sv')==configuration['sha256']['build/rtl/SpinorStandard.sv']
profile_text='\n'.join(profile_table)
memory_table=[]
current_by_case={r['case']:r for r in memory[0]['metrics']};old_by_case={r['case']:r for r in previous43['memory'][0]['metrics']}
for spec in memory[0]['benchmark_cases']:
 if spec['service_wait']!=0:continue
 now=current_by_case[spec['case']];old=old_by_case[spec['case']]
 assert now['cycles']==old['cycles'],(spec,now,old)
 memory_table.append(f"| {spec['eew']} | {'store' if spec['write'] else 'load'} | {spec['vl']} | {old['cycles']} | {now['cycles']} |")
indexed_rows=[]
for sew in range(4):
 for iw in range(4):
  row,=[r for r in indexed_engine['full-rtl']['case_specs'] if r['vtype']==sew<<3 and r['index_eew']==8<<iw and not r['write'] and r['ordered'] and not r['masked'] and r['vstart']==1]
  perfrow=indexed_engine['full-rtl']['performance'][str(row['id'])]
  indexed_rows.append(f"| {8<<sew} | {8<<iw} | {row['vl']-row['vstart']} | {perfrow['cycles']} | {perfrow['context_reads']} |")
performance_text=f"""# M44 索引LSU性能参考

相同直接LSU输入的352组M42/当前回放逐项检查：无掩码且有工作量时省2次掩码RF读取、4周期；64位load另按每个有效请求省1次RF旧值读取、2周期。回放使用恒定ready和固定服务延迟，含VL0、vstart、mask和不同EEW。

真实TileLink集成模型有周期相关A通道反压，观察周期不能机械减去固定值。下表为m8、无掩码、服务等待0的同输入例子，不含配置/context检查：

| EEW | 方向 | VL | M43周期 | M44周期 |
|---|---|---:|---:|---:|
{chr(10).join(memory_table)}

索引load观察值：m1、vstart=1、无掩码、ordered，索引为非单调字节偏移。独立LSU fixture含周期性context/请求/进度反压、寄存响应和4周期完成背压；含整条指令开销，不是器件吞吐承诺。RTL和映射网表逐项一致。

| 数据位宽 | 索引位宽 | 有效元素 | 指令周期 | RF读取 |
|---|---|---:|---:|---:|
{chr(10).join(indexed_rows)}

索引每个有效元素先读一个RF块，再复用四段16位地址加法器；仍是单端口、逐元素访存。原跨步地址按四段16位加法递推；初始vstart用最多7轮移位加法定位，复用原RF暂存器，不增加DSP。负/零步长、64位回绕、每个有效元素的零步长访问均保留。当前仍单条指令在途。

| 预设 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
{profile_text}

纯算术生成RTL与M42逐字节相同；旧220组基准结果及现有算术族周期保持。复用证据经过RTL、参考/测试依赖及已发布输入/输出散列核对，未通过校验时回归入口自动重跑。当前账本：{regression_counts}。
"""
(OUT/'performance.md').write_text(performance_text);include('reports/m44/performance.md')
local_base=read('archive/m31/local-report/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m31/local-report/'+name)
evaluation=(ROOT/'docs/m44-indexed-memory.md').read_text().replace('(../reports/m44/evaluation.md)','(evaluation.md)').replace('(rvv-completion-plan.md)','(../../docs/rvv-completion-plan.md)').replace('(references/m44-indexed-v1.0.txt)','(../../docs/references/m44-indexed-v1.0.txt)')+f"""

## 验证结果

独立LSU完整RTL/网表各{strided_engine['full-rtl']['cases']}例，精简各{strided_engine['compact-rtl']['cases']}例；覆盖全部EEW/合法EMUL、正负零步长、x0、vstart、掩码、高位/回绕、五类响应错误、请求/进度/完成反压和停止/错误竞争。真实TL集成完整RTL{strided_memory['strided-memory-rtl']['memory_cases']}组访存、{strided_memory['strided-memory-rtl']['stop_cases']}种停止；两种ALU分段精简RTL/网表各{strided_memory['strided-memory-smoke']['memory_cases']}组、{strided_memory['strided-memory-smoke']['stop_cases']}种停止。公开SpinorVpu另检查跨步读和反向写字面量，以及完整64位地址/字节掩码序列。四个预设保留x0/非x0零步长，并新增索引gather/scatter路径，强制访问计数。

352组冻结M42/当前LSU回放数值与状态一致，RF读取和固定服务下的周期节省逐项精确核对。旧单位步长完整303例、精简143例、77/9种停止继续通过；其请求序列和原覆盖维持。旧算术220组周期保持，四个预设的配置拒绝与重生成167个SV逐字节检查通过。既有局部SAT只覆盖各自范围，不宣称新LSU已整体形式证明。

回归账本合计145项RTL、39项定向网表：本次执行RTL {regression_counts['rtl']['executed']}项、网表{regression_counts['mapped']['executed']}项；分别{regression_counts['rtl']['reused']}、{regression_counts['mapped']['reused']}项按M42逐字节RTL/依赖和证据散列复用，未重跑的部分如实标注。冷环境无缓存时执行完整矩阵。

独立索引LSU完整RTL/网表各{indexed_engine['full-rtl']['cases']}例，精简各{indexed_engine['compact-rtl']['cases']}例，覆盖16编码、全部合法宽度几何、零扩展、64位回绕、同宽与合法宽窄重叠、保留别名、五类错误和停止竞争。真实TileLink完整RTL{indexed_memory['indexed-memory-rtl']['memory_cases']}组访存、{indexed_memory['indexed-memory-rtl']['stop_cases']}种停止；两种ALU分段精简RTL/网表各{indexed_memory['indexed-memory-smoke']['memory_cases']}组、{indexed_memory['indexed-memory-smoke']['stop_cases']}种停止。公共顶层另验证高位16索引零扩展的字面量gather和逆序scatter总线序列。

## 默认资源（括号相对M43）

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 / RAM32M16 |
|---|---:|---:|---:|---:|
{chr(10).join(resources_table)}

## 四个预设

| 顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
{profile_text}

VRF仍为512架构字节、1024逻辑物理字节，RAM64M8/RAM32M16=32/6，是LUTRAM而非BRAM块。步长操作数需要64位捕获；定位暂存复用original，没有新增整组FF快照。

## 固定条件时序预算

| 连线ps/段 | M40公共ns | M44公共ns | M44计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段：公共{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns；四个预设均≤3.333ns。M25模型与门槛未变，未布局布线、未按-2校准、排除DSP端点，尚未签核RAM写/hold/IO/时钟树。M44未运行Vivado/SDF，实际300/500MHz未知。[周期详情](performance.md)。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m44/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M44',status='INDEXED_MEMORY_RAM_SHARED_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 indexed_engine=indexed_engine,indexed_memory=indexed_memory,estimates=estimates,estimate_unit=estimate_unit,conversion_efficiency=efficiency,strided_engine=strided_engine,strided_memory=strided_memory,lsu_efficiency=lsu_efficiency,evidence_reuse=reuse,evidence_reuse_policy_test=cache_policy,regression_counts=regression_counts,resize_fp=resize_fp,resize_unit=resize_unit,resize_native=resize_native,resize_wide_unit=resize_wide_unit,resize_reference=resize_reference,
 wide_fp=wide_fp,wide_fp_unit=wide_fp_unit,native_fp_unit=native_fp_unit,wide_fp_reference=wide_fp_reference,
 fp_transfers=fp_transfers,profiles=profiles,configuration=configuration,regeneration=regeneration,
 fractional_clip=fractional_clip,clip_units=clip_units,fractional_units=fractional_units,
 fixed_point=fixed,fixed_point_units=fixed_units,
 widening_mac=wmac,m36_integer=new,integer_mac=mac,integer_mac_netlist=mac_netlist,
 widening_arithmetic=widening,widening_multiply=multiply,narrowing_shifts=narrowing,integer_extensions=extensions,local_M31_baseline=local_base,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M40_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 current_top_mapped_scope=['indexed-16-encodings-full-independent-LSU','indexed-real-TL-both-ALU-widths','indexed-cross-width-alias-and-restart','strided-LSU-full-independent-model','strided-real-TL-both-ALU-widths','x0-zero-stride-all-presets','estimate-two-encodings-both-ALU-widths','estimate-unit-compact','width-conversion-15-encodings-32-and-16-bit-ALU-compact','resize-converter-and-lane-compact','resize-native-and-wide-FP-compact','wide-FP-18-encodings-32-and-16-bit-ALU-compact','wide-FP-unit-compact','native-FP-unit-smoke','FP-transfer-32-and-16-bit-ALU-compact','four-production-presets-directed','M38-8-encoding-compact','clip-unit-compact','fractional-unit-compact','M37-39-encoding-compact','fixed-point-unit-compact','M36-17-encoding-compact','integer-mac-compact-40','mixed-89','public-memory-and-FP-transfer','LSU','monitor'],scope='PARTIAL_RVV; ONE_INSTRUCTION; CONFIGURABLE_FP_ALU_STAGING; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
