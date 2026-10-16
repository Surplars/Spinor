#!/usr/bin/env python3
"""Bind timing cuts, reserved-encoding fixes and current regression evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m27';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m26/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m26/reports/'+name)
for name in ['RamVectorFp','SpinorVpu']:
 f=f'archive/m26/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m26/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m26/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m27-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m26-baseline','m27-spinor','m27-compute']:
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==24
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
for top in ['IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary','FloatingPointLane','FloatingPointConvert','VectorMemoryEngine']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m27/results.json');include('build/performance-m27/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m27/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M26']['rtl_sha256']==sha(ROOT/'archive/m26/rtl/RamVectorFp.sv')
assert perf['results']['M27']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M27']['cases'])==220
for old,new in zip(perf['results']['M26']['cases'],perf['results']['M27']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m27').iterdir():
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
  table.append(f"| {'M26' if old else 'M27'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m26-baseline']['scenarios'],budgets['m27-spinor']['scenarios'],budgets['m27-compute']['scenarios'],strict=True):
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
evaluation=f"""# M27：RAM式vcompress与组边界检查优化

新增vcompress.vm；仍为VLEN128/ELEN64、单条指令容量的部分RVV，不声明完整V/RVA23。公开顶层SpinorVpu，目标ZU15EG-2，尚未接实际Orbital或Linux。

## 实现

显式vs1为EEW1掩码，选中vs2中VL以内的元素，保持顺序压紧到目的组前部，其后按tail策略允许的undisturbed选择保留。支持22种SEW/LMUL，vm=0和非零vstart报非法；目的不得重叠数据组或掩码，掩码与数据源的不同EEW物理寄存器重叠也拒绝。检查在VL0同样执行，非法保持架构状态。

复用已有indexGenerate模式3、scalarResult的8位计数和slideAddress地址阶段，没有新增状态、状态宽度或寄存器。掩码读取一次进入已有128位缓存；未选中元素不读数据，选中元素从已提交RAM读取，独立一拍计算密集目的地址，复用整数move单元串行写候选版本，完成握手才发布。flush抛弃候选写入与计数owner；没有整组快照或新增读端口。显式掩码缓存不会延续到下一条普通指令，原指令会重新取v0。

组边界检查利用1/2/4/8个寄存器的对齐条件，以地址高位匹配替代compress、gather、mask目的和viota的组end-address加法/比较；alignment使用布尔形式，EI16显式拒绝不支持的count=0。Yosys SAT对所有5位基址/寄存器号、四种组尺寸及合法基址对齐证明成员、不同组尺寸重叠、alignment与末端不溢出等价；这是局部组合证明，不是整机或完整ISA证明。

Monitor ABI1.0，ID0x2701/caps0x7fff，bit14表示compress；容量仍为一条指令。RF保持双版本64×128、字节写使能和同步读LUTRAM；FP数值单元和物理LSU RTL按SHA确认与M26相同。

## 验证

独立Python参考从不可变完整源组取VL前缀，用显式掩码过滤列表，不复制RTL的计数、模式编码或RAM地址算法。完整RTL {compress['commands']}条命令，非法{compress['coverage']['illegal']}、撤销{compress['coverage']['flush']}，覆盖22种类型、空/满/稀疏/随机掩码、每个源索引单独选择、跨寄存器压紧、VL/VLMAX边界、tail保留、掩码高于VL位忽略、v0作为三种合法角色、未按LMUL对齐的掩码、非法重叠/对齐/vm/vstart、VL0检查、完成背压及CSR保持；逐条读取32个寄存器并检查版本。smoke {smoke['commands']}条在当前RTL与映射网表结果和周期一致，无FP及16位切分版smoke通过。

旧gather3675、滑移5576、索引1674、前缀mask2888、mask/scalar10198、scan2894、归约3418、INT乘除1673、旧整数789、FP向量2157、streaming251重新通过RTL。558个保留源别名反例及合法零字段专项RTL/映射通过。24条混合序列交替compress、FP、viota、gather及原INT/MUL/归约/滑移，通过当前RTL/映射，检查共享模式/计数/地址/掩码缓存无泄漏。原220组性能的结果与周期均保持M26。e8/m8、VL128、无完成背压时，选中0/1/64/128个元素分别151/162/855/1559拍；该类型测试精确核对23+VL+11×选中数，包含准备开销，不是每拍压紧一个元素。

物理访存279组RTL及119组RTL/映射通过。公开SpinorVpu并发monitor流量下279组RTL及119组RTL/映射通过，末尾执行compress取消、稀疏压紧、四类非法编码，随后回到普通整数流水。Monitor2600周期RTL/映射、tiny回绕及用户态文件fixture通过。M26数值单元RTL与相应测试台/网表SHA均保持，复用6811组FP、5021组转换及局部数值证明的绑定证据；它们没有冒充当前完整顶层的网表测试。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射，RAM另消耗器件LUT，原语数量不是BRAM块数。

## 固定云端门槛

| 每段连线假设ps | M26公开ns | M27公开ns | M27计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

100ps/段固定假设下公开{mid['budget_ns']:.3f}ns、余量{mid['budget_residual_ns']:.3f}ns，计算/访存{compute['budget_ns']:.3f}ns、余量{compute['budget_residual_ns']:.3f}ns，均≤300MHz周期3.333ns。门槛仍锚定冻结M25权重/家族参考，M26冻结图另按SHA恢复用于上表比较，没有通过更改参数取巧。

仅为条件参考预算。没有布局布线或ZU15EG-2器件校准，DSP相关端点排除，无时钟树/hold、RAM写、IO或SDF检查；物理300/500MHz通过仍为null，不能继承旧M5物理结果。200ps档不满足300MHz周期。

## 复现

make bootstrap；python3 scripts/verify_m27.py；python3 scripts/package.py --milestone m27。receipt绑定源码、当前RTL/网表、独立参考测试台、局部证明、冻结基线和报告。未修改Valence或调用Verilator。后续继续宽窄整数、FP归约及更多访存模式与SoC集成。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m27/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M27',status='RAM_COMPRESS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M26_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; RAM_COMPRESS_AND_GROUP_LEGALITY; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
