#!/usr/bin/env python3
"""Bind RAM gather/splat ISA, regressions and conditional timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m25';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m24/reports/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m24/reports/'+name)
for old,new in [('build/rtl/RamVectorFp.sv','archive/m24/rtl/RamVectorFp.sv'),('build/rtl/SpinorVpu.sv','archive/m24/rtl/SpinorVpu.sv')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old];include(new)
assert sha(ROOT/'archive/m24/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala'];include('archive/m24/source/RamVector.scala')
restored=checked('build/baseline-m24/results.json')
assert restored['restored_sha256']==sha(ROOT/restored['output'])==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json'];include(restored['output'])
prefix={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/mask-prefix/'+label;d=checked(stem+'-results.json');prefix[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
full=prefix['RamVectorFp-full-rtl'];assert full['commands']==2888 and len(full['types'])==22
assert full['coverage']['flush']==75 and full['coverage']['illegal']==429
assert sum(full['coverage'][k] for k in ['before','only','including'])==1505
long=[x for x in full['performance'] if x['vl']==128];assert len(long)>=9 and all(x['cycles']==105 for x in long)
assert {x['first'] for x in long}=={-1,0,127}
index_generation={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/index-generate/'+label;d=checked(stem+'-results.json');index_generation[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
idx=index_generation['RamVectorFp-full-rtl'];assert len(idx['types'])==22 and idx['coverage']['iota']>300 and idx['coverage']['vid']>200
slides={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/slide/'+label;d=checked(stem+'-results.json');slides[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
slide_full=slides['RamVectorFp-full-rtl'];assert len(slide_full['types'])==22 and slide_full['coverage']['huge_offset']>100
gathers={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/gather/'+label;d=checked(stem+'-results.json');gathers[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
gather_full=gathers['RamVectorFp-full-rtl'];assert len(gather_full['types'])==22 and gather_full['coverage']['ei16']>100
for k in ['commands','coverage','types','performance','summary']:assert gathers['RamVectorFp-smoke-rtl'][k]==gathers['RamVectorFp-smoke-mapped'][k],k
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
 stem='build/reduction-interleave/'+label;mixed.append(checked(stem+'-results.json'));assert mixed[-1]['vector_instructions']==19
 for suffix in ['.log','-compile.log']:include(stem+suffix)
soc=[]
for label,count in [('rtl',254),('smoke',94),('mapped',94)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=simulation(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 for instruction in ['5230a3d7','53f82457','3a80b857','3f82ec57','33840857','3382c457','3380b857','3b8f8857','33840c57','33880857','3382c857']:
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
perf=read('build/performance-m25/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m25/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M24']['rtl_sha256']==sha(ROOT/'archive/m24/rtl/RamVectorFp.sv')
assert perf['results']['M25']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M25']['cases'])==220 and perf['results']['M25']['cases']==perf['results']['M24']['cases']
for p in (ROOT/'build/performance-m25').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m24-baseline','m25-spinor','m25-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m25-spinor','m25-compute']:
 assert budgets[label]['weights_ps']==budgets['m24-baseline']['weights_ps']
 assert budgets[label]['provenance']==budgets['m24-baseline']['provenance']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M24' if old else 'M25'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m24-baseline']['scenarios'],budgets['m25-spinor']['scenarios'],budgets['m25-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=budgets['m25-spinor']['scenarios'][1]['worst'];compute=budgets['m25-compute']['scenarios'][1]['worst']
evaluation=f"""# M25：RAM gather与标量广播

新增vrgather.vv/.vx/.vi、vrgatherei16.vv。继续完善VPU本体，仍为VLEN128/ELEN64、单条指令容量的部分RVV，未接Orbital或Linux，不声明完整V/RVA23。

## 语义与实现

支持正常22种SEW/LMUL；EI16索引按EEW16、EMUL=(16/SEW)*LMUL计算，e8/m8因索引EMUL16而按规范报非法。索引可访问VL之外、VLMAX之内的数据，超VLMAX补0。vx保持完整64位索引，vi为无符号5位；支持mask、vstart恢复和tail/inactive保留。

目的不得重叠数据或索引组，索引按自己的EMUL对齐；不同EEW的索引/数据源不能读同一物理寄存器，执行mask与v0数据/索引源的双EEW别名同样检查。同EEW的两个源可以别名，非masked的源v0与目的v0可使用。非法检查在VL0仍执行。

没有新增状态或扩大状态宽度。复用readB/captureB读取索引，a操作数暂存完整索引，slideAddress阶段做高位OR和8位比较、数据RAM地址选择，再经原整数move流水和tag写回。索引组计数由5输入位常量表计算，在FP版译码阶段寄存后再检查几何。VLMAX沿用nextVl私有暂存。

vx/vi首次取源后用已有b寄存器缓存广播值，仅新增一个valid位；后续元素不重复读RAM，零值广播也缓存。正常矢量索引每个有效元素两次RAM读取，广播源至多读取一次；不增加整组快照、读端口、RF或DSP。所有写入仍到候选RAM，完成握手才发布版本，flush撤销。

## 验证

独立Python参考从不可变全源组数组按数学索引取值，以索引字节数推导EMUL占用，不复制RTL的常量表或高位/低位比较实现。完整RTL {gather_full['commands']}条命令，非法{gather_full['coverage']['illegal']}、撤销{gather_full['coverage']['flush']}，覆盖22种类型、四种编码、跨行、重复索引、VL/VLMAX边界、所有8位索引值、64位高位索引、EI16的256/257与高位、独立对齐及部分组重叠、mask/vstart、VL0、完成背压与CSR保持。逐条检查32寄存器和版本。

{gathers['RamVectorFp-smoke-rtl']['commands']}条smoke在RTL和映射网表功能、异常、撤销及周期一致，覆盖8种类型；无FP和16位切分版另通过smoke。广播基准的周期上限检查防止退回逐元素重复RAM读取。

旧滑移5576、索引生成1674、前缀掩码2888、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及旧向量789重新通过RTL。19条INT/FP/归约/滑移/gather交替序列通过RTL/映射，检查新模式与缓存不会泄漏到旧操作。原220组性能结果与周期和M24一致。

物理访存254组RTL通过；公开SpinorVpu在monitor流量下254组RTL及94组RTL/映射通过，末尾执行四类gather、源/索引重叠非法、超大索引、取消，并保留旧mask/index/slide检查。逐访存请求和周期与M24一致。Monitor ABI1.0，ID0x2501/caps0x3fff，bit13表示gather。

9个数值/RF/访存/CPU边界单元RTL按SHA确认未变，复用已绑定单测及局部证明；增量器组合证明重新执行以绑定当前源码。旧完整顶层的映射证据没有冒充当前网表结果。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；表中是逻辑LUT，RAM另占器件LUT。RAM为LUTRAM，不是BRAM数量。

## 条件时序

| 每段连线假设ps | M24公开ns | M25公开ns | M25计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

100ps档公开顶层{mid['budget_ns']:.3f}ns，300MHz周期3.333ns的算术余量{1000/300-mid['budget_ns']:+.3f}ns；路径{mid['start']}到{mid['end']}。计算/访存封装{compute['budget_ns']:.3f}ns。保持同一权重及RapidWright家族参考，基线冻结图恢复后校验SHA。FP32仍为参考最慢路径，新增gather没有取代它。

没有布局布线、-2校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，没有器件STA/SDF、WNS或Vivado。300/500MHz通过仍为null，不能继承旧M5物理结果，也不能把映射变化解释成确定的Fmax变化。

## 范围与复现

make bootstrap；python3 scripts/verify_m25.py；python3 scripts/package.py --milestone m25。receipt.json绑定源码、RTL、网表、测试台、冻结基线和报告。后续继续compress、宽窄/定点、FP归约及访存模式。旧普通算术/滑移的v0数据源与执行mask双EEW别名约束尚未统一，旧正向回归不构成这些编码的架构合法性证明；该已知限制列入ISA矩阵。实际Orbital接入、VM/PMP/一致性与Linux上下文仍未完成。未修改Valence，未调用Verilator。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m25/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M25',status='RAM_GATHER_AND_SPLAT_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 gathers=gathers,slides=slides,index_generation=index_generation,monitor_client=client,increment_proof=increment_proof,mask_prefix=prefix,mask_prefix_proof=prefix_proof,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,monitor=monitors,
 unchanged_M24_RTL=unchanged,reused_M24_proofs=reused_proofs,reused_M24_units=reused_units,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,restored_baseline=restored,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; RAM_GATHER_SPLAT_SLIDE_AND_INDEX_ENGINE; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
