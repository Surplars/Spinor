#!/usr/bin/env python3
"""Bind M19 functionality and honest conditional timing to exact evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m19';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((ROOT/name).read_text())
artifacts=set()
def include(name):
 p=ROOT/name;assert p.is_file(),p;artifacts.add(p)
def checked(name):
 d=read(name);assert d['status']=='PASS',name;include(name)
 for p,h in d.get('sha256',{}).items():assert sha(ROOT/p)==h,p;include(p)
 return d
def simulation(name,rtl,tb):
 d=checked(name);assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),name
 assert d['testbench_sha256']==sha(ROOT/tb),name;include(rtl);include(tb);return d
base=read('archive/m18/reports/receipt.json')
for old,new in [('build/rtl/RamVectorFp.sv','archive/m18/rtl/RamVectorFp.sv'),
 ('build/rtl/SpinorVpu.sv','archive/m18/rtl/SpinorVpu.sv'),
 ('build/synth/SpinorVpu/mapped.json','archive/m18/synth-SpinorVpu/mapped.json')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old],new;include(new)
for name in ['RamVector.scala','VpuMonitor.scala']:
 p='archive/m18/source/'+name;assert sha(ROOT/p)==base['source_sha256']['src/main/scala/vpu/'+name];include(p)
include('archive/m18/reports/receipt.json')
mask=[]
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/mask-scalar/'+label;d=checked(stem+'-results.json');mask.append(d)
 assert all(d['coverage'].values()) and all(d['by_operation'].values())
 assert d['coverage']['flush']==60
 for suffix in ['.log','-compile.log']:include(stem+suffix)
 if (ROOT/(stem+'-assert.sv')).exists():include(stem+'-assert.sv')
assert mask[0]['commands']==5372 and len(mask[0]['types'])==22
assert (mask[0]['coverage']['mask'],mask[0]['coverage']['scalar_read'],mask[0]['coverage']['scalar_write'],mask[0]['coverage']['illegal'])==(1409,181,177,267)
for key in ['coverage','by_operation','types','performance','summary']:assert mask[1][key]==mask[2][key],key
red=checked('build/reductions/RamVectorFp-full-rtl-results.json')
assert red['coverage']['reductions']==1411 and red['coverage']['illegal']==210
for suffix in ['.log','-compile.log','-assert.sv']:include('build/reductions/RamVectorFp-full-rtl'+suffix)
old_integer={}
for label,count,tb in [('m7-div-fp',1673,'m7-div-fp-tb.sv'),('ram-vector',789,'ram_vector_tb.sv')]:
 name='build/test/'+label+'-results.json';d=read(name);include(name);include('build/test/'+tb)
 assert d['commands']==count
 for top,hashes in d['input_sha256'].items():
  rtl=f'build/rtl/{top}.sv';assert hashes['rtl']==sha(ROOT/rtl),top
  assert hashes['testbench']==sha(ROOT/'build/test'/tb),top
  assert d['models'][top].startswith('PASS ram-vector'),top
  include(rtl)
 old_integer[label]=d
fp=simulation('build/test/fp-vector-m9-convert-results.json','build/rtl/RamVectorFp.sv','build/test/fp-vector-m9-convert-tb.sv')
assert fp['commands']==2157 and fp['test_summary'].splitlines()[0]==base['fp_vector']['test_summary'].splitlines()[0]
stream=simulation('build/test/streaming-rtl.json','build/rtl/RamVectorFp.sv','build/test/streaming-rtl-tb.sv');assert stream['commands']==251
mixed=[]
for label in ['rtl','mapped']:
 mixed.append(checked('build/reduction-interleave/'+label+'-results.json'));assert mixed[-1]['vector_instructions']==7
 for suffix in ['.log','-compile.log']:include('build/reduction-interleave/'+label+suffix)
soc=[]
for label,count in [('rtl',254),('smoke',94),('mapped',94)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 rtl='build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv'
 d=simulation(stem+'-results.json',rtl,stem+'-tb.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 log=(ROOT/(stem+'.log')).read_text();assert 'PASS monitored-mmio' in log
 for inst in ['438021d7','4200efd7','43f021d7','6e112057','00880457']:
  assert inst in (ROOT/(stem+'-tb.sv')).read_text(),inst
 for suffix in ['.log','.compile.log']:include(stem+suffix)
 if label!='mapped':
  assert d['assertions_enabled']
  for module in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+module+'-assert.sv')
assert soc[0]['metrics']==base['spinor_integration'][0]['metrics']
assert soc[1]['metrics']==soc[2]['metrics']
memory=simulation('build/test/vector-memory-rtl-results.json','build/rtl/LishiVpuMemory.sv','build/test/vector-memory-rtl-tb.sv')
assert memory['memory_cases']==254 and memory['metrics']==base['memory'][0]['metrics']
for suffix in ['.log','.compile.log','-VectorMemoryEngine-assert.sv','-RamVectorFpMemory-assert.sv']:include('build/test/vector-memory-rtl'+suffix)
monitors=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped']:
 stem='build/monitor/test/'+label;d=checked(stem+'-results.json');assert d['cycles']==2600;monitors.append(d)
 for suffix in ['.log','-compile.log']:include(stem+suffix)
assert monitors[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert monitors[0][k]==monitors[2][k]
software=checked('build/monitor/software/results.json');include('build/monitor/software/decoded.json')
perf=read('build/performance-m19/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m19/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M18']['rtl_sha256']==sha(ROOT/'archive/m18/rtl/RamVectorFp.sv')
assert perf['results']['M19']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M19']['cases'])==220 and perf['results']['M18']['cases']==perf['results']['M19']['cases']
for p in (ROOT/'build/performance-m19').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m18-baseline','m19-spinor','m19-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
unchanged={}
for top in ['IntegerLaneSplit','FloatingPointLane','IntegerMultiply','IntegerDivide','FloatingPointConvert','VectorMemoryEngine','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel);include(rel)
assert sha(ROOT/'src/main/scala/vpu/VpuHostBoundary.scala')==base['source_sha256']['src/main/scala/vpu/VpuHostBoundary.scala']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory']:
 c=resources[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
reference=(ROOT/'docs/references/mask-scalar-v1.0.txt').read_text()
for code,name in enumerate(['vmandn','vmand','vmor','vmxor','vmorn','vmnand','vmnor','vmxnor'],0x18):
 assert re.search(r'^'+name+r'\.mm\s+31\.\.26=0x'+f'{code:x}'+r' 25=1 vs2 vs1 14\.\.12=0x2 vd 6\.\.0=0x57$',reference,re.M)
assert 'vmv.x.s        31..26=0x10 25=1 vs2 19..15=0 14..12=0x2 rd 6..0=0x57' in reference
assert 'vmv.s.x        31..26=0x10 25=1 24..20=0 rs1 14..12=0x6 vd 6..0=0x57' in reference
include('docs/references/mask-scalar-v1.0.txt')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
def cells(top,old=False):return (base['resources'] if old else resources)[top]['mapped_cells']
table=[]
for top in ['LishiVpuMemory','SpinorVpu']:
 for old in [True,False]:
  c=cells(top,old);table.append(f"| {'M18' if old else 'M19'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for before,now in zip(budgets['m18-baseline']['scenarios'],budgets['m19-spinor']['scenarios'],strict=True):
 assert before['assumed_link_ps']==now['assumed_link_ps']
 timing.append(f"| {now['assumed_link_ps']} | {before['worst']['budget_ns']:.3f} | {now['worst']['budget_ns']:.3f} | {1000/300-now['worst']['budget_ns']:+.3f} |")
compute=budgets['m19-compute']['scenarios']
evaluation='''# M19：Spinor 掩码逻辑、整数标量搬运与 300 MHz 参考

新增8种mask逻辑.mm和2种整数标量搬运，仍为VLEN128/ELEN64、容量1的部分RVV执行器。未接入实际Orbital、Linux计算驱动或实验OoO窗口。

## 功能证据

完整RTL：5372条命令，1409次合法mask逻辑、181次标量读、177次标量写、267次非法编码、60次flush，覆盖22种合法SEW/LMUL。所有32个寄存器、版本表、vstart和非零FP/定点CSR均核对；完成背压不得提前提交，撤销时同时拉高completion-ready。映射子集与同输入RTL的覆盖、结果和周期完全相同；无FP及16位分段版本另通过smoke。它们是有限差分验证，不是形式化或ISA全合规。

原有1411次整数归约、1673条整数乘除、2157条FP向量、789条旧版向量、251条streaming和7条归约/INT/MUL/FP混合程序通过，混合程序也通过映射网表。220组旧性能用例逐项周期与M18相同。标量搬运无完成背压时读6周期、写8周期；mask逻辑为逐位串行，非并行布尔向量单元。

默认访存顶层254组RTL通过。公开SpinorVpu在持续monitor读取时通过254组RTL与94组RTL/映射子集，另外执行真实归约、符号扩展标量读写、mask XOR生成v0、masked vadd并检查尾部。访存逐用例性能指标与M18相同；总周期包含新增末尾指令。Monitor生产RTL/映射和8位回绕各2600周期通过；UIO用户态工具通过编译及文件夹具，未测试实际内核/设备。ABI仍1.0，ID=0x1901、caps=0x1ff。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

LishiVpuMemory计算/访存顶层增加707 LUT、9 FF；含monitor的SpinorVpu增加665 LUT、9 FF。复用整数lane、单RF读口、候选写回和scalar completion；不增加DSP、向量FF快照或RF副本。上述RAM是分布式映射原语，不是BRAM块数。独立VpuHostBoundary仍不在Spinor顶层内，源码及RTL与M18一致，复用已记录的单元证据；实际CPU握手未验证。

## 300 MHz 尚未确认通过

300 MHz周期为3.333 ns。公开SpinorVpu的云端条件预算如下，余量仅是算术差值：

| 每段假设连线ps | M18 ns | M19 ns | M19相对3.333 ns余量 |
|---:|---:|---:|---:|
'''+ '\n'.join(timing)+f'''

计算/访存顶层LishiVpuMemory的三档为{compute[0]['worst']['budget_ns']:.3f}/{compute[1]['worst']['budget_ns']:.3f}/{compute[2]['worst']['budget_ns']:.3f} ns。不同顶层综合优化产生不同映射，不能将其预算相加或混用。

公开顶层50/100 ps假设下的最大链仍是FP64舍入路径；200 ps时最大链变为vtype到状态寄存器的控制路径，比M18预算增加0.077 ns。100 ps假设下3.732 ns已经超过3.333 ns，因此不能说云端参考已通过300 MHz；50 ps档虽有正余量，也不能证明器件达标。

这是Yosys未布局网表、RapidWright家族参考弧及显式连线/建立假设。346个DSP相关端点排除，未做-2速度校准、时钟树/布线、hold、RAM写或I/O时序。没有器件SDF/STA、WNS、Fmax或本轮Vivado结果。RTL/映射功能仿真通过不等于满足给定MHz。历史M5的真实OOC结果不代表M19。

## 接入与复现

CPU合同见docs/cpu-spinor-contract.md，新指令与剩余范围见docs/m19-mask-scalar.md和docs/isa-coverage.md。仍缺vcpop/vfirst、排列、宽窄/定点、FP归约、完整访存、上下文/保护/一致性和实际Orbital接入。

复现：make bootstrap，然后python3 scripts/verify_m19.py；打包python3 scripts/package.py --milestone m19。receipt.json绑定本轮源码、RTL、网表、测试台与证据。没有执行Verilator或修改Valence/Orbital源码。
'''
(OUT/'evaluation.md').write_text(evaluation)
for p in OUT.iterdir():
 if p.is_file() and p.name!='receipt.json':artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M19',status='CLOUD_MASK_SCALAR_FUNCTIONAL_AND_BUDGET_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 mask_scalar=mask,reductions=red,integer=old_integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,
 monitor=monitors,software=software,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,unchanged_M18_RTL=unchanged,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; SERIAL_MASK_LOGIC; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(cells('SpinorVpu')),'FF',ff(cells('SpinorVpu')))
