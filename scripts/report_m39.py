#!/usr/bin/env python3
"""Bind M39 configuration/FP transfers, old regressions and unchanged timing model."""
import hashlib,json,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m39';OUT.mkdir(parents=True,exist_ok=True)
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
 for key in ['case_specs','metrics']:
  assert current[key][:len(old[key])]==old[key],key
 assert current['benchmark_cases']==old['benchmark_cases']
 assert all(current['context_reads'][k]==v for k,v in old['context_reads'].items())
 assert current['stop_cases']==old['stop_cases']
 return []

base=read('archive/m38/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m38/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane','IntegerMultiply','FixedPointLane']:
 f=f'archive/m38/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala','IntegerMultiply.scala','FixedPointLane.scala']:
 f='archive/m38/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m38/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m39-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m38-baseline','m39-spinor','m39-compute']:
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
  for key in ['commands','coverage']:assert d[key]==old[key],(name,label,key)
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
perf=read('build/performance-m39/results.json');include('build/performance-m39/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m39/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M38']['rtl_sha256']==sha(ROOT/'archive/m38/rtl/RamVectorFp.sv')
assert perf['results']['M39']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M39']['cases'])==220
for old,new in zip(perf['results']['M38']['cases'],perf['results']['M39']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m39').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','FloatingPointLane','VpuMonitor','IntegerDivide','FixedPointLane','IntegerMultiplyFractional','RamVectorFp16','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
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
for label in ['rtl','mapped']:
 rows=read('build/m39-regression/'+label+'.json');include('build/m39-regression/'+label+'.json')
 assert sum(map(len,rows.values()))==(102 if label=='rtl' else 17),label
 for records in rows.values():
  for row in records:assert row['exit_code']==0,row;include(row['log'])
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
for label,d in wmac.items():same_performance(d['performance'],base['widening_mac'][label]['performance'],0)
for label,d in new.items():same_performance(d['performance'],base['m36_integer'][label]['performance'],0)
for label,d in fixed.items():
 old=base['fixed_point'][label]
 for key in ['commands','coverage','types','encodings']:assert d[key]==old[key],(label,key)
 same_performance(d['performance'],old['performance'],0)
resources_table=[]
for top in ['SpinorVpu','LishiVpuMemory','RamVectorFp']:
 old=base['resources'][top]['mapped_cells'];c=resources[top]['mapped_cells']
 assert all(c[k]==old[k] for k in ['DSP48E2','RAM64M8','RAM32M16'])
 resources_table.append(f"| {top} | {lut(c)} ({lut(c)-lut(old):+d}) | {ff(c)} ({ff(c)-ff(old):+d}) | {c['DSP48E2']} | {c['RAM64M8']} / {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m38-baseline']['scenarios'],budgets['m39-spinor']['scenarios'],budgets['m39-compute']['scenarios'],strict=True):
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
configuration=checked('build/configuration/results.json');assert len(configuration['negative_cases'])==7
for row in configuration['negative_cases']:include(row['log'])
profiles={};profile_table=[]
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
 data={}
 for label in ['rtl','mapped']:
  stem='build/profiles/'+top+'-'+label;data[label]=checked(stem+'-results.json');logs(stem)
 assert data['rtl']['summary']==data['mapped']['summary'] and data['rtl']['commands']==data['mapped']['commands']==10
 cfg=data['rtl']['config'];assert cfg==data['mapped']['config']
 assert cfg['vlen']==128 and cfg['elen']==64 and cfg['lanes']==1 and cfg['instruction_capacity']==1
 c=resources[top]['mapped_cells'];assert c['DSP48E2']==(9 if cfg['fp32_fp64'] else 1)
 assert c['RAM64M8']==32 and c['RAM32M16']==6
 budget=read(f'build/timing-budget/m39-{top}/budget.json')
 for p,h in budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 for ext in ['json','md']:include(f'build/timing-budget/m39-{top}/budget.{ext}')
 assert budget['weights_ps']==budgets['m39-spinor']['weights_ps'] and budget['provenance']==budgets['m39-spinor']['provenance']
 assert budget['passes_300MHz'] is None and not budget['placed'] and not budget['speed_grade_calibrated']
 scenario,=[s for s in budget['scenarios'] if s['assumed_link_ps']==100]
 ns=scenario['worst']['budget_ns'];assert ns<=1000/300,(top,ns)
 profiles[top]=dict(config=cfg,tests=data,conditional_budget=budget)
 profile_table.append(f"| {top} | {'FP32/64' if cfg['fp32_fp64'] else '整数'} | {cfg['alu_stage_bits']} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {ns:.3f} |")
assert sha(ROOT/'build/rtl/SpinorStandard.sv')==configuration['sha256']['build/rtl/SpinorStandard.sv']
profile_text='\n'.join(profile_table)
performance_table=[]
for kind in ['read','write','up','down']:
 for sew in [32,64]:
  row=next(x for x in full39['performance'] if x['kind']==kind and x['sew']==sew and x['vtype']&7==0)
  performance_table.append(f"| {kind} | {sew} | {row['vl']} | {row['cycles']} |")
performance_text='''# M39 性能与预设参考

新增指令为无外部阻塞RTL周期，包含完成，不含配置和context检查。仍单条指令在途。

| 操作 | SEW | VL | 周期 |
|---|---:|---:|---:|
'''+chr(10).join(performance_table)+'''

read/write为vfmv.f.s/vfmv.s.f，up/down为vfslide1up/down.vf。搬运复用既有RAM、slide地址与整数move；不调用FP计算单元。完整周期矩阵含type、vstart及frm，见receipt.fp_transfers。

旧220组基准与冻结M38逐项相同；包括M38分数乘法/裁剪、M37定点、旧整数/浮点族的性能记录也相同。LSU与公共顶层旧访存用例周期、请求数和RF读取计数相同。

下表为未布局的Yosys xcup映射与固定100ps/段条件预算。更深流水不等于更大吞吐；整数预设不包含FP，VLEN与VRF容量相同。

| 预设顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
'''+profile_text+'''

四个预设均通过定向公共接口RTL/网表测试；这不是各自完整ISA合规或器件300MHz签核。
'''
(OUT/'performance.md').write_text(performance_text);include('reports/m39/performance.md')
local_base=read('archive/m31/local-report/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m31/local-report/'+name)
evaluation=(ROOT/'docs/m39-configurations-and-fp-transfers.md').read_text().replace('(../reports/m39/evaluation.md)','(evaluation.md)').replace('(references/m39-fp-transfers-v1.0.txt)','(../../docs/references/m39-fp-transfers-v1.0.txt)')+f'''

## 验证结果

新增FP搬运完整RTL {full39['commands']}条命令、9种合法FP类型，4种编码；包含{full39['coverage']['flush']}次撤销和f0、VL0、NaN boxing、保留frm等情况。32位及16位ALU配置精简RTL/当前网表各{fp_transfers['RamVectorFp-compact-rtl']['commands']}条，所有架构状态和周期一致；无FP配置拒绝全部新FP形式。

102项RTL子进程、17项定向网表子进程通过。其中4个生产预设各运行公共命令/context/TL/monitor集成测试，明确为定向范围；默认核心重跑旧M38及全部既有RTL族，并运行旧M38/M37/M36精简网表、MAC、混合序列和LSU/公共顶层143组。默认公开顶层完整RTL303组访存后执行新FP位模式序列，覆盖sNaN、canonical NaN、f0与原地down。7项CLI拒绝测试通过，默认配置生成RTL与公开顶层逐字节相同（仅替换顶层名称）。回归日志与源输入SHA均绑定receipt。

旧220组及全部既有族性能记录相同。保留SHA绑定的8个旧数值/存储/边界单元RTL未改变；FP数值证据重用这些相同单元，FP向量集成矩阵重跑。增量/地址SAT重跑，不作为新FP搬运的形式证明。[性能与预设表](performance.md)。

## 默认配置资源（括号相对M38）

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 / RAM32M16 |
|---|---:|---:|---:|---:|
{chr(10).join(resources_table)}

## 四个生产预设

| 顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
{profile_text}

各预设RAM64M8/RAM32M16均32/6，架构VRF仍512字节；LUTRAM另计，不等于Vivado BRAM数量。整数预设删除FP而保留定点、整数乘除和物理LSU。接口缺失FP CSR端口和能力位已检查。

## 固定条件时序预算

| 连线ps/段 | M38公共ns | M39公共ns | M39计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

默认100ps/段下公共{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns；四个预设也各自要求≤3.333ns。M25权重、参考图和门槛未放宽。未布局、未按-2校准，排除DSP端点，未签核RAM写、hold、时钟树或IO。M39未执行Vivado/SDF，实际300/500MHz未知。
'''
(OUT/'evaluation.md').write_text(evaluation);include('reports/m39/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M39',status='CONFIGURATION_FP_TRANSFERS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 fp_transfers=fp_transfers,profiles=profiles,configuration=configuration,
 fractional_clip=fractional_clip,clip_units=clip_units,fractional_units=fractional_units,
 fixed_point=fixed,fixed_point_units=fixed_units,
 widening_mac=wmac,m36_integer=new,integer_mac=mac,integer_mac_netlist=mac_netlist,
 widening_arithmetic=widening,widening_multiply=multiply,narrowing_shifts=narrowing,integer_extensions=extensions,local_M31_baseline=local_base,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M38_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 current_top_mapped_scope=['FP-transfer-32-and-16-bit-ALU-compact','four-production-presets-directed','M38-8-encoding-compact','clip-unit-compact','fractional-unit-compact','M37-39-encoding-compact','fixed-point-unit-compact','M36-17-encoding-compact','integer-mac-compact-40','mixed-89','public-memory-and-FP-transfer','LSU','monitor'],scope='PARTIAL_RVV; ONE_INSTRUCTION; CONFIGURABLE_FP_ALU_STAGING; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
