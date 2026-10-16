#!/usr/bin/env python3
"""Bind integer-slide ISA, regressions and conditional timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m24';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m23/reports/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m23/reports/'+name)
for old,new in [('build/rtl/RamVectorFp.sv','archive/m23/rtl/RamVectorFp.sv'),('build/rtl/SpinorVpu.sv','archive/m23/rtl/SpinorVpu.sv')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old];include(new)
assert sha(ROOT/'archive/m23/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala'];include('archive/m23/source/RamVector.scala')
restored=checked('build/baseline-m23/results.json')
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
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/slide/'+label;d=checked(stem+'-results.json');slides[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
slide_full=slides['RamVectorFp-full-rtl'];assert len(slide_full['types'])==22 and slide_full['coverage']['huge_offset']>100
for k in ['commands','coverage','types','performance','summary']:assert slides['RamVectorFp-smoke-rtl'][k]==slides['RamVectorFp-smoke-mapped'][k],k
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
 stem='build/reduction-interleave/'+label;mixed.append(checked(stem+'-results.json'));assert mixed[-1]['vector_instructions']==13
 for suffix in ['.log','-compile.log']:include(stem+suffix)
soc=[]
for label,count in [('rtl',254),('smoke',94),('mapped',94)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=simulation(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 for instruction in ['5230a3d7','53f82457','5208a457','3a80b857','3f00b857','3b02ec57','3f82ec57','3a80b457']:
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
perf=read('build/performance-m24/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m24/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M23']['rtl_sha256']==sha(ROOT/'archive/m23/rtl/RamVectorFp.sv')
assert perf['results']['M24']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M24']['cases'])==220 and perf['results']['M24']['cases']==perf['results']['M23']['cases']
for p in (ROOT/'build/performance-m24').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m23-baseline','m24-spinor','m24-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m24-spinor','m24-compute']:
 assert budgets[label]['weights_ps']==budgets['m23-baseline']['weights_ps']
 assert budgets[label]['provenance']==budgets['m23-baseline']['provenance']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M23' if old else 'M24'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m23-baseline']['scenarios'],budgets['m24-spinor']['scenarios'],budgets['m24-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=budgets['m24-spinor']['scenarios'][1]['worst'];compute=budgets['m24-compute']['scenarios'][1]['worst']
evaluation=f"""# M24：整数滑移

新增vslideup.vx/.vi、vslidedown.vx/.vi、vslide1up.vx、vslide1down.vx。仍为VLEN128/ELEN64的部分RVV、单指令容量，继续完善VPU本体；未接入Orbital或Linux，不声明完整V/RVA23。

## 实现与边界

支持全部22种合法SEW/LMUL、mask、vstart恢复和tail/inactive保留。上移禁止源目的组重叠；下移允许完全别名，始终读已提交RAM，避免读取本条候选写。vslidedown以VLMAX判断源越界，允许读取VL外的源tail；超VLMAX才补0。标量滑移量保持XLEN64精度，立即数为无符号5位；slide1按VL位置插入截到SEW的标量。VL0与vstart>=VL不改目的，非法对齐、上移重叠与masked目的v0在VL0仍检查。

保留全部旧状态编码和5位状态宽度，增加一个slideAddress阶段。译码寄存8位低偏移和高位非零标志；以9位精确计算源索引，暂存在现有a操作数寄存器。随后独立做VLMAX比较与RAM行/元素选择，沿用同步RAM、整数Op.move、tag写回及版本提交。VLMAX复用未提交的nextVl暂存，kind=0不会发布该私有值。没有新增整组FF快照、RF副本或DSP。普通源读取比旧基础整数多一个地址阶段；标量插入/补0绕过源RAM读取。

## 验证

独立Python参考先取整个源组的不可变元素数组，再以完整64位数学偏移计算目的，不复制RTL的低位/高位标志与9位分级实现。完整RTL {slide_full['commands']}条命令，非法{slide_full['coverage']['illegal']}、撤销{slide_full['coverage']['flush']}；六种编码、22种类型、跨寄存器、VL/VLMAX差异、超大偏移、立即数16..31、上下行重叠规则、源/目的v0、mask、vstart、零VL、标量插入和抑制、完成背压均覆盖。逐条核对32个寄存器、版本及CSR。{slides['RamVectorFp-smoke-rtl']['commands']}条smoke在RTL与映射中功能、异常、撤销和周期完全一致；无FP和16位切分也通过smoke。

M23索引生成1674条、前缀掩码2888、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及旧向量789重新通过RTL；13条混合INT/FP/滑移/归约序列通过RTL/映射，检查滑移模式及私有VLMAX不会泄漏到旧操作。220组旧性能结果与周期保持M23值。新滑移的逐配置周期保存在slide证据中，不把周期数当作物理频率。

物理访存254组RTL通过；公开SpinorVpu在monitor流量下254组RTL及94组RTL/映射通过，末尾包含新旧mask/index，以及滑移→别名下移→标量插入、非法上移别名与撤销。逐访存请求/周期与M23一致。Monitor ABI1.0，ID0x2401/caps0x1fff，bit12表示整数滑移；生产RTL/映射及8位回绕检查通过。

9个未修改数值/RF/访存/CPU边界单元按RTL和网表SHA复用已绑定单测及局部证明；增量器组合证明重新执行以绑定当前源码。旧mask/index本轮完整RTL与公开顶层映射集成已检查，没有把旧完整顶层的映射证据冒充为当前网表结果。实际CPU、Linux和器件时序未验证。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；表中LUT是逻辑LUT计数，RAM另外占用器件LUT。RAM为LUTRAM，不能当作BRAM数量。

## 条件时序

| 每段假设连线ps | M23公开ns | M24公开ns | M24计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

100ps档公开顶层{mid['budget_ns']:.3f}ns，相对300MHz周期3.333ns算术余量{1000/300-mid['budget_ns']:+.3f}ns；路径{mid['start']}到{mid['end']}。计算/访存封装{compute['budget_ns']:.3f}ns。使用完全相同的权重及RapidWright家族表来源，M23图恢复后核对冻结SHA。

这不是器件STA或Fmax：没有布局布线、-2校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，无器件SDF、WNS或Vivado。300/500MHz通过状态仍为null，旧M5物理时序不自动继承。

## 复现与范围

make bootstrap；python3 scripts/verify_m24.py；python3 scripts/package.py --milestone m24。receipt.json绑定源码、RTL、网表、测试台、冻结基线与报告。继续补gather/compress、宽窄/定点、FP归约和访存模式；vfslide1 FP标量滑移、实际Orbital接入、VM/PMP/一致性及Linux上下文仍待完成。未修改Valence，未调用Verilator。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m24/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M24',status='INTEGER_SLIDE_INSTRUCTIONS_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 slides=slides,index_generation=index_generation,monitor_client=client,increment_proof=increment_proof,mask_prefix=prefix,mask_prefix_proof=prefix_proof,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,monitor=monitors,
 unchanged_M23_RTL=unchanged,reused_M23_proofs=reused_proofs,reused_M23_units=reused_units,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,restored_baseline=restored,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; RAM_SLIDE_AND_INDEX_ENGINE; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
