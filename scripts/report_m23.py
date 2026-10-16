#!/usr/bin/env python3
"""Bind index-generation ISA, regression and conditional timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m23';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((ROOT/name).read_text())
artifacts=set()
def include(name):
 p=ROOT/name;assert p.is_file(),p;artifacts.add(p)
def checked(name):
 d=read(name);assert d['status']=='PASS',name;include(name)
 for key in ['sha256','input_sha256']:
  for p,h in d.get(key,{}).items():assert sha(ROOT/p)==h,p;include(p)
 return d
def simulation(stem,rtl,tb=None):
 d=checked(stem+('-results.json' if not stem.endswith(('streaming-rtl',)) else '.json'))
 assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),stem;include(rtl)
 tb=tb or stem+'-tb.sv';assert d['testbench_sha256']==sha(ROOT/tb),stem;include(tb)
 for suffix in ['.log','.compile.log']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
 return d
base=read('archive/m22/reports/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m22/reports/'+name)
for old,new in [('build/rtl/RamVectorFp.sv','archive/m22/rtl/RamVectorFp.sv'),('build/rtl/SpinorVpu.sv','archive/m22/rtl/SpinorVpu.sv')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old];include(new)
assert sha(ROOT/'archive/m22/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala'];include('archive/m22/source/RamVector.scala')
restored=checked('build/baseline-m22/results.json')
assert restored['restored_sha256']==sha(ROOT/restored['output'])==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json'];include(restored['output'])
prefix={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/mask-prefix/'+label;d=checked(stem+'-results.json');prefix[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
full=prefix['RamVectorFp-full-rtl'];assert full['commands']==2888 and len(full['types'])==22
assert full['coverage']['flush']==75 and full['coverage']['illegal']==429
assert sum(full['coverage'][k] for k in ['before','only','including'])==1505
for k in ['commands','coverage','types','performance','summary']:assert prefix['RamVectorFp-smoke-rtl'][k]==prefix['RamVectorFp-smoke-mapped'][k],k
long=[x for x in full['performance'] if x['vl']==128];assert len(long)>=9 and all(x['cycles']==105 for x in long)
assert {x['first'] for x in long}=={-1,0,127}
index_generation={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/index-generate/'+label;d=checked(stem+'-results.json');index_generation[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
idx=index_generation['RamVectorFp-full-rtl'];assert len(idx['types'])==22 and idx['coverage']['iota']>300 and idx['coverage']['vid']>200
for k in ['commands','coverage','types','performance','summary']:assert index_generation['RamVectorFp-smoke-rtl'][k]==index_generation['RamVectorFp-smoke-mapped'][k],k
client=checked('build/monitor/software/results.json')
for name in ['client.log','compile.log']:
 if (ROOT/'build/monitor/software'/name).exists():include('build/monitor/software/'+name)
increment_proof=checked('build/increment-proof/results.json')
for name in ['generate.log','proof.log']:include('build/increment-proof/'+name)
prefix_proof=checked('build/mask-prefix-proof/results.json')
for name in ['generate.log','proof.log']:include('build/mask-prefix-proof/'+name)
mask={}
for folder in ['mask-scalar','mask-scan']:
 stem='build/'+folder+'/RamVectorFp-full-rtl';d=checked(stem+'-results.json');mask[folder]=d
 for k in ['commands','coverage','types','performance','summary']:assert d[k]==base['mask'][folder][k],(folder,k)
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
red=checked('build/reductions/RamVectorFp-full-rtl-results.json');assert red['coverage']['reductions']==1411
for suffix in ['.log','-compile.log','-assert.sv']:include('build/reductions/RamVectorFp-full-rtl'+suffix)
integer={}
for label,count,tb in [('m7-div-fp',1673,'m7-div-fp-tb.sv'),('ram-vector',789,'ram_vector_tb.sv')]:
 name='build/test/'+label+'-results.json';d=read(name);include(name);include('build/test/'+tb);assert d['commands']==count
 for top,h in d['input_sha256'].items():
  path=f'build/rtl/{top}.sv';assert h['rtl']==sha(ROOT/path),top;assert h['testbench']==sha(ROOT/'build/test'/tb),top
  assert d['models'][top].startswith('PASS ram-vector');include(path)
 integer[label]=d
fp=simulation('build/test/fp-vector-m9-convert','build/rtl/RamVectorFp.sv');assert fp['commands']==2157
assert re.search(r'cycles=(\d+)',fp['test_summary'])[1]==re.search(r'cycles=(\d+)',base['fp_vector']['test_summary'])[1]
stream=simulation('build/test/streaming-rtl','build/rtl/RamVectorFp.sv');assert stream['commands']==251
mixed=[]
for label in ['rtl','mapped']:
 stem='build/reduction-interleave/'+label;mixed.append(checked(stem+'-results.json'));assert mixed[-1]['vector_instructions']==7
 for suffix in ['.log','-compile.log']:include(stem+suffix)
soc=[]
for label,count in [('rtl',254),('smoke',94),('mapped',94)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=simulation(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 for instruction in ['5230a3d7','00880457','53f82457','5208a457','428021d7']:
  assert instruction in (ROOT/(stem+'-tb.sv')).read_text(),instruction
 if label!='mapped':
  assert d['assertions_enabled']
  for module in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+module+'-assert.sv')
assert soc[0]['metrics']==base['spinor_integration'][0]['metrics']
assert soc[1]['metrics']==soc[2]['metrics']
memory=simulation('build/test/vector-memory-rtl','build/rtl/LishiVpuMemory.sv');assert memory['memory_cases']==254
assert memory['metrics']==base['memory']['metrics']
for module in ['VectorMemoryEngine','RamVectorFpMemory']:include('build/test/vector-memory-rtl-'+module+'-assert.sv')
monitors=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped']:
 stem='build/monitor/test/'+label;d=checked(stem+'-results.json');assert d['cycles']==2600;monitors.append(d)
 for suffix in ['.log','-compile.log']:include(stem+suffix)
assert monitors[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert monitors[0][k]==monitors[2][k]
unchanged={}
for top in ['FloatingPointLane','FloatingPointConvert','IntegerLaneSplit','IntegerMultiply','IntegerDivide','VectorMemoryEngine','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel);include(rel)
reused_proofs={}
for name in ['round-proof','recode-proof','divider-proof']:
 reused_proofs[name]=checked('build/'+name+'/results.json')
 for file in ['generate.log','proof.log']:include('build/'+name+'/'+file)
reused_units={}
for label,top,ext in [('fp-lane','FloatingPointLane','-results.json'),('fp-lane-smoke','FloatingPointLane','-results.json'),('fp-lane-mapped','FloatingPointLane','-results.json'),('fp-convert-rtl','FloatingPointConvert','-results.json'),('integer-divide-rtl','IntegerDivide','.json'),('integer-divide-mapped','IntegerDivide','.json')]:
 stem='build/test/'+label;d=read(stem+ext);assert d['status']=='PASS';include(stem+ext)
 rtl=f'build/synth/{top}/mapped.v' if 'mapped' in label else f'build/rtl/{top}.sv'
 assert sha(ROOT/rtl)==d['rtl_or_netlist_sha256']==base['artifact_sha256'][rtl];include(rtl)
 tb='build/test/integer-divide-tb.sv' if label.startswith('integer-divide') else stem+'-tb.sv'
 assert sha(ROOT/tb)==d['testbench_sha256'];include(tb);reused_units[label]=d
 for suffix in ['.log','.compile.log']:include(stem+suffix)
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
perf=read('build/performance-m23/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m23/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M22']['rtl_sha256']==sha(ROOT/'archive/m22/rtl/RamVectorFp.sv')
assert perf['results']['M23']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M23']['cases'])==220 and perf['results']['M23']['cases']==perf['results']['M22']['cases']
for p in (ROOT/'build/performance-m23').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m22-baseline','m23-spinor','m23-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m23-spinor','m23-compute']:
 assert budgets[label]['weights_ps']==budgets['m22-baseline']['weights_ps']
 assert budgets[label]['provenance']==budgets['m22-baseline']['provenance']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M22' if old else 'M23'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m22-baseline']['scenarios'],budgets['m23-spinor']['scenarios'],budgets['m23-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=budgets['m23-spinor']['scenarios'][1]['worst'];compute=budgets['m23-compute']['scenarios'][1]['worst']
evaluation=f"""# M23：向量索引生成

新增viota.m、vid.v，完善VPU本体；仍为部分RVV、VLEN128/ELEN64和单指令容量，不声明完整V/RVA23、Orbital接入或Linux运行。

## 实现

viota.m输出每个元素之前的有效源mask置位数；masked-out元素不计数。源为单mask寄存器，目的按正常LMUL分组。非零vstart、源位于目的组内、masked目的v0和目的未对齐非法，零VL仍检查。vid.v输出原始元素索引，支持mask和vstart恢复，vs2非零编码非法。全部22种合法SEW/LMUL均支持；保留tail和inactive值。

复用整数流水线、版本化RAM与已有scalarResult低8位作私有前缀计数；没有整组快照和新增RF副本。viota每个有效元素读取源mask，8位独立前缀进位完成计数更新；vid略过RAM源读取。新值进入原有Op.move流水和带tag写回。候选版本仅在完成握手后发布，flush取消，既有整数/FP周期基准保持一致。

## 验证

独立Python模型对整条有效索引集合求数学前缀和，不复制RTL逐元素反馈。完整新指令RTL {idx['commands']}条命令，viota {idx['coverage']['iota']}、vid {idx['coverage']['vid']}、非法{idx['coverage']['illegal']}、撤销{idx['coverage']['flush']}；覆盖22种类型、全部128个one-hot源位、部分tail、分数LMUL、源v0、目的v0、源未对齐、目的组内部重叠、非零vstart/恢复及完成背压。所有32寄存器、版本与CSR逐条核对。smoke RTL/映射网表功能和周期一致，无FP及16位切分另通过smoke。

8位前缀计数递增连同原32/55/109位增量器、地址与配置比较由SAT全输入检查；这是局部组合证明。旧前缀掩码回归2888条、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及混合INT/FP/归约通过。旧前缀保留1505次合法操作；16/17两个selector现归新指令，旧reserved检查改由专门的新指令模型覆盖。原220组性能结果及周期与M22一致。

物理访存封装254组RTL；公开SpinorVpu在持续monitor流量下254组RTL及94组RTL/映射通过，末尾新增viota→标量提取→vid并核对RAM。逐访存请求/周期和M22一致。monitor ID=0x2301/caps=0xfff，新增bit11索引生成，ABI仍1.0；生产RTL/映射和8位计数回绕通过。

SHA核对9个数值、RF、访存与CPU边界单元RTL未变，复用已绑定输入的单元验证和舍入/重编码/除法证明；新顶层功能回归重新执行。真实CPU未参与测试。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；RAM为分布式LUTRAM，不能当成BRAM数量。

## 条件时序预算

| 每段连线假设ps | M22公开ns | M23公开ns | M23计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

100ps档公开顶层{mid['budget_ns']:.3f}ns，300MHz周期3.333ns的算术余量{1000/300-mid['budget_ns']:+.3f}ns；路径{mid['start']}到{mid['end']}。计算/访存封装{compute['budget_ns']:.3f}ns。保持相同权重和RapidWright家族表来源，对M22冻结图核对SHA后重新分析。

这不是器件STA或Fmax：无放置布线、-2校准、DSP相关端点、时钟树/hold、RAM写及I/O路径检查，无器件SDF、WNS或Vivado运行。300/500MHz通过状态仍为null，M5物理结果不能继承。

## 复现和范围

make bootstrap；python3 scripts/verify_m23.py；python3 scripts/package.py --milestone m23。receipt.json绑定源码、RTL、映射图、测试台、冻结基线与报告。后续继续排列、宽窄/定点、FP归约和LSU模式；Orbital集成、VM/PMP/一致性和Linux计算驱动仍待完成。未使用Verilator或修改Valence。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m23/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M23',status='INDEX_GENERATION_INSTRUCTIONS_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 index_generation=index_generation,monitor_client=client,increment_proof=increment_proof,mask_prefix=prefix,mask_prefix_proof=prefix_proof,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,monitor=monitors,
 unchanged_M22_RTL=unchanged,reused_M22_proofs=reused_proofs,reused_M22_units=reused_units,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,restored_baseline=restored,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; RAM_INDEX_GENERATION_AND_MASK_ENGINE; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
