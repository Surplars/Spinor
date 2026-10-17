#!/usr/bin/env python3
"""Bind widening add/sub, frozen local baseline and fixed cloud timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m33';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m32/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m32/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane']:
 f=f'archive/m32/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m32/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m32/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m33-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m32-baseline','m33-spinor','m33-compute']:
 budgets[label]=read('build/timing-budget/'+label+'/budget.json')
 for suffix in ['json','md']:include(f'build/timing-budget/{label}/budget.{suffix}')
 for p,h in budgets[label]['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)

families={}
for folder in ['compress','gather','slide','index-generate','mask-prefix']:
 data={}
 labels=['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']
 if folder in ['compress','gather']:labels+=['RamVectorFp-smoke-mapped']
 for label in labels:
  stem=f'build/{folder}/{label}';d=checked(stem+'-results.json');logs(stem);data[label]=d
  assert all(d['coverage'].values()),(folder,label)
 assert len(data['RamVectorFp-full-rtl']['types'])==22
 families[folder]=data
for folder in ['compress','gather']:
 for k in ['commands','coverage','types','performance','summary']:
  assert families[folder]['RamVectorFp-smoke-rtl'][k]==families[folder]['RamVectorFp-smoke-mapped'][k]
assert families['slide']['RamVectorFp-full-rtl']['coverage']['masked_source_v0']==134
prefix=families['mask-prefix']['RamVectorFp-full-rtl'];assert prefix['commands']==2888
assert all(x['cycles']==105 for x in prefix['performance'] if x['vl']==128)
aliases={}
for label in ['RamVectorFp-rtl','RamVector-rtl','RamVector16-rtl','RamVectorFp-mapped']:
 stem='build/mask-source-alias/'+label;aliases[label]=checked(stem+'-results.json');logs(stem)
 assert aliases[label]['coverage']['legal_zero_fields']>0
for k in ['commands','reserved_cases','coverage','summary']:assert aliases['RamVectorFp-rtl'][k]==aliases['RamVectorFp-mapped'][k]
fp_widening_reductions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/fp-widening-reductions/'+label;d=checked(stem+'-results.json');logs(stem);fp_widening_reductions[label]=d
 assert d['reference_anchors']==52 and d['coverage']['flushes']>0
fpwide=fp_widening_reductions['RamVectorFp-full-rtl']
assert len(fpwide['by_type'])==5 and all(fpwide['coverage'].values()) and fpwide['commands']==1664
assert fpwide['coverage']['reductions']==442 and fpwide['coverage']['illegal']==194
for key in ['commands','coverage','by_operation','by_type','performance','summary']:
 assert fp_widening_reductions['RamVectorFp-smoke-rtl'][key]==fp_widening_reductions['RamVectorFp-smoke-mapped'][key],key
for label in ['RamVector-smoke-rtl','RamVector16-smoke-rtl']:assert fp_widening_reductions[label]['coverage']['reductions']==0
fp_widen_lane={}
for label in ['rtl','smoke','mapped']:
 stem='build/fp-widen-lane/'+label;d=checked(stem+'-results.json');logs(stem);fp_widen_lane[label]=d
 assert d['extra_reference_anchors']==7 and d['base_reference_anchors']==52
assert fp_widen_lane['rtl']['vectors']==1292
for key in ['vectors','flush_reset_cases','latency','summary']:assert fp_widen_lane['smoke'][key]==fp_widen_lane['mapped'][key],key
widening_reductions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/widening-reductions/'+label;d=checked(stem+'-results.json');logs(stem);widening_reductions[label]=d
 assert all(d['coverage'].values()) and all(d['by_operation'].values())
wide=widening_reductions['RamVectorFp-full-rtl']
assert len(wide['by_type'])==18 and wide['commands']==1025
assert wide['coverage']['reductions']==260 and wide['coverage']['illegal']==325 and wide['coverage']['flushes']==60
for key in ['commands','coverage','by_operation','by_type','performance','summary']:
 assert widening_reductions['RamVectorFp-smoke-rtl'][key]==widening_reductions['RamVectorFp-smoke-mapped'][key],key
fp_reductions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/fp-reductions/'+label;d=checked(stem+'-results.json');logs(stem);fp_reductions[label]=d
 assert d['reference_anchors']==52 and d['coverage']['flushes']>0
full=fp_reductions['RamVectorFp-full-rtl']
for row in full['performance']:
 if row['sew']==32 and row['vlmul']==3 and row['frm']==0:assert row['cycles']==(1229 if row['op'] in [1,3] else 301)
assert len(full['by_type'])==9 and all(full['by_operation'].values()) and all(full['coverage'].values())
for key in ['commands','coverage','by_operation','by_type','performance','summary']:
 assert fp_reductions['RamVectorFp-smoke-rtl'][key]==fp_reductions['RamVectorFp-smoke-mapped'][key],key
for label in ['RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 assert fp_reductions[label]['coverage']['reductions']==0
mask={}
for folder in ['mask-scalar','mask-scan']:
 stem=f'build/{folder}/RamVectorFp-full-rtl';d=checked(stem+'-results.json');logs(stem);mask[folder]=d
 for k in ['commands','coverage','types','performance','summary']:assert d[k]==base['mask'][folder][k],(folder,k)
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==58
memory=[]
for label,count in [('rtl',279),('smoke',119),('mapped',119)]:
 stem='build/test/vector-memory-'+label;rtl='build/synth/LishiVpuMemory/mapped.v' if label=='mapped' else 'build/rtl/LishiVpuMemory.sv'
 d=sim(stem,rtl);assert d['memory_cases']==count;memory.append(d)
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert memory[1]['metrics']==memory[2]['metrics']
soc=[]
for label,count in [('rtl',279),('smoke',119),('mapped',119)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=sim(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert soc[1]['metrics']==soc[2]['metrics']
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
for top in ['FloatingPointLane','IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary','FloatingPointConvert','VectorMemoryEngine']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m33/results.json');include('build/performance-m33/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m33/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M32']['rtl_sha256']==sha(ROOT/'archive/m32/rtl/RamVectorFp.sv')
assert perf['results']['M33']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M33']['cases'])==220
for old,new in zip(perf['results']['M32']['cases'],perf['results']['M33']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m33').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','FloatingPointLane','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M32' if old else 'M33'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m32-baseline']['scenarios'],budgets['m33-spinor']['scenarios'],budgets['m33-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=gate['results']['SpinorVpu'];compute=gate['results']['LishiVpuMemory']
compress=families['compress']['RamVectorFp-full-rtl']
smoke=families['compress']['RamVectorFp-smoke-rtl']
assert compress['commands']==1229 and smoke['commands']==189
assert compress['coverage']['reserved_start']>0 and compress['coverage']['cross_register']>0
bench128=[x for x in compress['performance'] if x['sew']==8 and x['vl']==128]
assert {x['selected'] for x in bench128}>={0,1,64,128}
assert all(x['cycles']==23+x['vl']+11*x['selected'] for x in bench128)
extensions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/integer-extensions/'+label;d=checked(stem+'-results.json');logs(stem);extensions[label]=d
 assert all(d['coverage'].values())
assert extensions['RamVectorFp-full-rtl']['commands']==4212 and len(extensions['RamVectorFp-full-rtl']['types'])==15
for key in ['commands','coverage','types','performance','summary']:
 assert extensions['RamVectorFp-smoke-rtl'][key]==extensions['RamVectorFp-smoke-mapped'][key],key
narrowing={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/narrowing-shifts/'+label;d=checked(stem+'-results.json');logs(stem);narrowing[label]=d
 assert all(d['coverage'].values())
full_narrow=narrowing['RamVectorFp-full-rtl']
assert full_narrow['commands']==4945 and len(full_narrow['types'])==15
assert full_narrow['coverage']['illegal']==1753 and full_narrow['coverage']['flush']==198
for key in ['commands','coverage','types','performance','summary']:
 assert narrowing['RamVectorFp-smoke-rtl'][key]==narrowing['RamVectorFp-smoke-mapped'][key],key
widening={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/widening-arithmetic/'+label;d=checked(stem+'-results.json');logs(stem);widening[label]=d
 assert all(d['coverage'].values())
widen_full=widening['RamVectorFp-full-rtl']
assert len(widen_full['types'])==15 and widen_full['commands']==11926
assert widen_full['coverage']['illegal']==4825 and widen_full['coverage']['flush']==608
assert {x['code'] for x in widen_full['performance']}==set(range(0x30,0x38))
assert {x['form'] for x in widen_full['performance']}=={2,6}
for key in ['commands','coverage','types','performance','summary']:
 assert widening['RamVectorFp-smoke-rtl'][key]==widening['RamVectorFp-smoke-mapped'][key],key
widen_performance=[]
for t in [0,8,16,2,10,18]:
 observed={f:{r['cycles'] for r in widen_full['performance'] if r['vtype']==t and r['form']==f and r['vm']==1} for f in [2,6]}
 assert all(len(c)==1 for c in observed.values())
 length=next(r['vl'] for r in widen_full['performance'] if r['vtype']==t)
 row=dict(source_sew=8<<(t>>3),lmul='m'+str(1<<(t&7)),vl=length,vector_cycles=next(iter(observed[2])),scalar_cycles=next(iter(observed[6])))
 row['target_300MHz_vector_us']=row['vector_cycles']/300;row['target_300MHz_scalar_us']=row['scalar_cycles']/300
 row['target_300MHz_vector_Melements_s']=length*300/row['vector_cycles'];row['target_300MHz_scalar_Melements_s']=length*300/row['scalar_cycles']
 widen_performance.append(row)
performance_rows=[f"| {r['source_sew']} | {r['lmul']} | {r['vl']} | {r['vector_cycles']} | {r['scalar_cycles']} | {r['target_300MHz_vector_us']:.3f} / {r['target_300MHz_scalar_us']:.3f} |" for r in widen_performance]
performance_text="""# M33 宽化加减性能参考

周期来自完整RTL回归，包含目的候选复制与指令执行/提交；不包含vset、访存或软件调用开销。vm=1、VL=VLMAX、完成端无停顿，16种宽化加减编码在所列组合的同类源形式下周期相同。smoke覆盖的组合另有当前综合网表一致性检查。

| 源SEW | LMUL | 元素数 | vv/wv周期 | vx/wx周期 | 按300MHz目标换算µs：向量源/标量源 |
|---|---|---:|---:|---:|---:|
"""+'\n'.join(performance_rows)+"""

300MHz仅用于目标换算，没有实际M33器件频率验证。e8/m4的64元素向量源约46.4M元素/秒、标量源约67.1M元素/秒，均为上述目标频率下的估计；不是应用吞吐率、带宽或上板实测。

旧220组性能用例按冻结M32与当前RTL执行，结果检查通过且周期相同；原始逐项数据包含于交付包的build/performance-m33/results.json。
"""
(OUT/'performance.md').write_text(performance_text);include('reports/m33/performance.md')
local_base=read('archive/m31/local-report/receipt.json')
assert local_base['passes_300MHz_current_OOC_constraints'] is True
assert local_base['routed']['WNS_ns']==0.392 and local_base['routed']['WHS_ns']==0.009
for name in ['receipt.json','evaluation.md']:include('archive/m31/local-report/'+name)
evaluation=(ROOT/'docs/m33-widening-arithmetic.md').read_text().replace('当前周期、完整测试计数与资源/时序结果由[本轮报告](../reports/m33/evaluation.md)给出。','完整测试计数与资源/时序结果列于下文。')+f"""

## 资源映射结果

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射，RAM另占LUT，不等于Vivado BRAM数。

## 固定条件时序结果

| 连线假设 ps/段 | M32公共ns | M33公共ns | M33计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段：公共{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns，余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，门槛3.333ns。冻结M25权重/锚点保持不变。

## 本轮验证计数

周期与目标频率换算见[性能参考](performance.md)。

宽化完整RTL {widen_full['commands']} 条命令、{len(widen_full['types'])}种合法类型，非法{widen_full['coverage']['illegal']}、取消{widen_full['coverage']['flush']}；smoke RTL/映射各{widening['RamVectorFp-smoke-rtl']['commands']}条，数值/版本/周期一致。完整窄化4945、扩展4212以及旧FP/INT归约、排列、掩码、访存与220组性能回归通过。58条混合指令RTL/映射通过，公共顶层279组完整RTL及119组RTL/映射访存通过。9个未改动数值/访存/RF/host单元的证据按原RTL散列复用；冷启动verify重跑数值单元。

M31本地OOC是历史基线：setup+0.392ns、hold+0.009ns，实际资源14173总LUT/11605FF/7DSP/2RAMB36；HD.CLK_SRC和接口延迟未设。M33未经过Vivado布局布线或SDF，实际300/500MHz未知，不能继承M31本地通过结论。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m33/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M33',status='WIDENING_INTEGER_ADD_SUB_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 widening_arithmetic=widening,widening_performance=widen_performance,narrowing_shifts=narrowing,integer_extensions=extensions,local_M31_baseline=local_base,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M32_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; WIDENING_INTEGER_ADD_SUB; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
