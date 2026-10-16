#!/usr/bin/env python3
"""Bind M20 functionality and honest conditional timing to exact evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m20';OUT.mkdir(parents=True,exist_ok=True)
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
def simulation(name,rtl,tb):
 d=checked(name);assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),name
 assert d['testbench_sha256']==sha(ROOT/tb),name;include(rtl);include(tb);return d
base=read('archive/m19/reports/receipt.json')
for old,new in [('build/rtl/RamVectorFp.sv','archive/m19/rtl/RamVectorFp.sv'),
 ('build/rtl/SpinorVpu.sv','archive/m19/rtl/SpinorVpu.sv'),
 ('build/synth/SpinorVpu/mapped.json','archive/m19/synth-SpinorVpu/mapped.json')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old],new;include(new)
for name in ['RamVector.scala','VpuMonitor.scala','StagedRound.scala','FloatingPointLane.scala']:
 p='archive/m19/source/'+name;assert sha(ROOT/p)==base['source_sha256']['src/main/scala/vpu/'+name];include(p)
include('archive/m19/reports/receipt.json')
mask=[]
for label in ['RamVectorFp-full-rtl']:
 stem='build/mask-scalar/'+label;d=checked(stem+'-results.json');mask.append(d)
 assert all(d['coverage'].values()) and all(d['by_operation'].values())
 assert d['coverage']['flush']==60
 for suffix in ['.log','-compile.log']:include(stem+suffix)
 if (ROOT/(stem+'-assert.sv')).exists():include(stem+'-assert.sv')
assert mask[0]['commands']==5372 and len(mask[0]['types'])==22
assert (mask[0]['coverage']['mask'],mask[0]['coverage']['scalar_read'],mask[0]['coverage']['scalar_write'],mask[0]['coverage']['illegal'])==(1409,181,177,267)
scans=[]
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/mask-scan/'+label;d=checked(stem+'-results.json');scans.append(d)
 assert all(d['coverage'].values()) and d['coverage']['flush']==14
 for suffix in ['.log','-compile.log']:include(stem+suffix)
 if (ROOT/(stem+'-assert.sv')).exists():include(stem+'-assert.sv')
assert scans[0]['commands']==973 and len(scans[0]['types'])==22
assert (scans[0]['coverage']['pop'],scans[0]['coverage']['first'],scans[0]['coverage']['illegal'])==(177,177,90)
for key in ['coverage','types','performance','summary']:assert scans[1][key]==scans[2][key],key
proofs={}
for label in ['round-proof','recode-proof','divider-proof']:
 proofs[label]=checked('build/'+label+'/results.json')
 for filename in ['generate.log','proof.log']:include('build/'+label+'/'+filename)
lane=[]
for label in ['fp-lane','fp-lane-smoke','fp-lane-mapped']:
 rtl='build/synth/FloatingPointLane/mapped.v' if label.endswith('mapped') else 'build/rtl/FloatingPointLane.sv'
 stem='build/test/'+label;d=simulation(stem+'-results.json',rtl,stem+'-tb.sv');lane.append(d)
 assert d['corrupt_result_rejected'] and d['flush_reset_cases']>0
 for suffix in ['.log','.compile.log']:include(stem+suffix)
assert lane[0]['vectors']==6811 and lane[0]['flush_reset_cases']==205
assert lane[1]['observed_latency_cycles']==lane[2]['observed_latency_cycles']
assert lane[1]['vectors']==lane[2]['vectors']==385
convert=simulation('build/test/fp-convert-rtl-results.json','build/rtl/FloatingPointConvert.sv','build/test/fp-convert-rtl-tb.sv')
assert convert['vectors']==5021 and convert['flush_reset_cases']==492
for suffix in ['.log','.compile.log']:include('build/test/fp-convert-rtl'+suffix)
integer_divide=[]
for label in ['rtl','mapped']:
 stem='build/test/integer-divide-'+label
 rtl='build/synth/IntegerDivide/mapped.v' if label=='mapped' else 'build/rtl/IntegerDivide.sv'
 d=simulation(stem+'.json',rtl,'build/test/integer-divide-tb.sv');integer_divide.append(d)
 assert d['checks']==2894 and d['flushes']==270
 for suffix in ['.log','.compile.log']:include(stem+suffix)
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
assert fp['commands']==2157
fp_cycles=int(re.search(r'cycles=(\d+)',fp['test_summary'])[1])
old_fp_cycles=int(re.search(r'cycles=(\d+)',base['fp_vector']['test_summary'])[1])
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
 for inst in ['438021d7','4200efd7','43f021d7','6e112057','00880457','420821d7','4208a1d7','401821d7']:
  assert inst in (ROOT/(stem+'-tb.sv')).read_text(),inst
 for suffix in ['.log','.compile.log']:include(stem+suffix)
 if label!='mapped':
  assert d['assertions_enabled']
  for module in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+module+'-assert.sv')
def memory_delta(old,new):
 assert len(old)==len(new)
 delta=[]
 for before,after in zip(old,new,strict=True):
  assert before['case']==after['case'] and before['requests']==after['requests']
  if before!=after:delta.append(dict(case=after['case'],old_cycles=before['cycles'],new_cycles=after['cycles']))
 # Store immediately following the four-element FP add sees a changed modulo-3
 # A-ready phase. All explicitly controlled memory benchmark cases stay equal.
 assert delta==[dict(case=197,old_cycles=82,new_cycles=81)]
 return delta
memory_deltas={'spinor':memory_delta(base['spinor_integration'][0]['metrics'],soc[0]['metrics'])}
assert soc[1]['metrics']==soc[2]['metrics']
memory=simulation('build/test/vector-memory-rtl-results.json','build/rtl/LishiVpuMemory.sv','build/test/vector-memory-rtl-tb.sv')
assert memory['memory_cases']==254
memory_deltas['compute']=memory_delta(base['memory']['metrics'],memory['metrics'])
for suffix in ['.log','.compile.log','-VectorMemoryEngine-assert.sv','-RamVectorFpMemory-assert.sv']:include('build/test/vector-memory-rtl'+suffix)
monitors=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped']:
 stem='build/monitor/test/'+label;d=checked(stem+'-results.json');assert d['cycles']==2600;monitors.append(d)
 for suffix in ['.log','-compile.log']:include(stem+suffix)
assert monitors[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert monitors[0][k]==monitors[2][k]
software=checked('build/monitor/software/results.json');include('build/monitor/software/decoded.json')
perf=read('build/performance-m20/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m20/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M19']['rtl_sha256']==sha(ROOT/'archive/m19/rtl/RamVectorFp.sv')
assert perf['results']['M20']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M20']['cases'])==len(perf['results']['M19']['cases'])==220
performance_deltas=[]
for old,new in zip(perf['results']['M19']['cases'],perf['results']['M20']['cases'],strict=True):
 if old!=new:
  for k in ['id','operation','form','sew','lmul','vl','mask','active_elements','instructions']:assert old[k]==new[k]
  assert new['operation']=='vfadd' and new['cycles']-old['cycles']==new['instructions']*new['active_elements']
  performance_deltas.append(dict(id=new['id'],old_cycles=old['cycles'],new_cycles=new['cycles'],extra_per_active_element=1))
assert [d['id'] for d in performance_deltas]==[207,211,215,219]
for p in (ROOT/'build/performance-m20').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m19-baseline','m20-spinor','m20-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
assert budgets['m19-baseline']['weights_ps']==budgets['m20-spinor']['weights_ps']
assert budgets['m19-baseline']['provenance']==budgets['m20-spinor']['provenance']
unchanged={}
for top in ['IntegerLaneSplit','IntegerMultiply','VectorMemoryEngine','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
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
scan_reference=(ROOT/'docs/references/mask-scan-v1.0.txt').read_text()
for code,name in [(0x10,'vcpop'),(0x11,'vfirst')]:
 assert re.search(r'^'+name+r'\.m\s+31\.\.26=0x10 vm vs2 19\.\.15=0x'+f'{code:x}'+r' 14\.\.12=0x2 rd 6\.\.0=0x57$',scan_reference,re.M)
include('docs/references/mask-scan-v1.0.txt')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
def cells(top,old=False):return (base['resources'] if old else resources)[top]['mapped_cells']
table=[]
for top in ['LishiVpuMemory','SpinorVpu']:
 for old in [True,False]:
  c=cells(top,old);table.append(f"| {'M19' if old else 'M20'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for before,now in zip(budgets['m19-baseline']['scenarios'],budgets['m20-spinor']['scenarios'],strict=True):
 assert before['assumed_link_ps']==now['assumed_link_ps']
 timing.append(f"| {now['assumed_link_ps']} | {before['worst']['budget_ns']:.3f} | {now['worst']['budget_ns']:.3f} | {1000/300-now['worst']['budget_ns']:+.3f} |")
compute=budgets['m20-compute']['scenarios']
mid=budgets['m20-spinor']['scenarios'][1]['worst']
evaluation=f'''# M20：Spinor FP 路径优化与掩码扫描

新增vcpop.m/vfirst.m，优化FP舍入、FP32分类、除法与浮点转整数的进位、FMA规格化和monitor回绕检测。仍为VLEN128/ELEN64、容量1的部分RVV执行器，未接入实际Orbital或Linux计算驱动。

## 功能证据

掩码扫描完整RTL973条命令：vcpop和vfirst各177次、非法90次、撤销14次，覆盖22种合法SEW/LMUL。含masked、v0源、未对齐单寄存器源、rd=x0、vl=0、无置位、非零vstart非法。核对全部32个寄存器、版本表和CSR，完成背压禁止提前提交。映射smoke与同输入RTL的覆盖、周期一致；无FP与16位切分版本另通过smoke。

FP独立数值回归6811组，5种舍入模式、FP32/64、205次flush/reset，通过SoftFloat位精确结果和异常标志检查；385组映射子集与RTL延迟相同。浮点转换另通过5021组和492次flush/reset。整数除法符号修正改为8位分组，RTL/映射各2894组与270次flush通过，延迟不变。四种原始格式的StagedRound通过10步、单次稳定输入的有界SAT等价检查，含完成信号非空检查；这不等于完整流水线形式化。FP32/64重编码、FP32分类、23/52/54位平衡前导零编码和加法/递增含进位的组合等价证明通过，输入与模式约束见各proof结果。

M19的5372条mask/标量搬运测试（含1409次mask运算、358次标量读写、267次非法、60次flush）继续通过完整RTL。旧归约1411次、整数乘除1673条、FP向量2157条、旧版向量789条、streaming251条和7条混合INT/FP程序通过，混合程序另通过映射网表。220组性能用例全部校验结果，其中216组周期不变，4组vfadd按每活动元素增加1周期；差值记录在performance_cycle_deltas。

舍入多一级流水使使用它的算术/整数转浮点增加1周期，其余优化没有增加周期。FP向量回归从{old_fp_cycles}到{fp_cycles}周期，增加{fp_cycles-old_fp_cycles}。4组vfadd的额外周期为32/256/16/128，对应8条指令乘活动元素数；整数周期不变不代表FP吞吐不变。

默认访存顶层254组RTL通过。公开SpinorVpu在持续monitor读取时通过254组RTL与94组RTL/映射子集，另执行归约、标量搬运、mask生成/消费、vcpop/vfirst并检查monitor功能位。所有访存请求数量和独立吞吐基准周期与M19相同。FP加法后store的用例197从82变81周期：新增FP流水改变了测试台cycles%3控制A-ready的相位，不是LSU吞吐改善；其余逐用例周期不变。总周期也包含新增末尾指令。Monitor生产RTL/映射、8位回绕各2600周期通过。回绕预测增加13个标志寄存器，overflow仍在实际回绕当拍置位；clear行为不变。ABI1.0，ID=0x2001/caps=0x3ff。UIO工具只作编译/文件夹具测试。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

复用单RF读口和scalar completion。新增FF主要用于舍入分级与monitor回绕预测；不增加DSP、整组向量快照或RF副本。RAM数字是分布式映射原语而非BRAM块数。独立VpuHostBoundary源码/RTL与M19一致，仍不在Spinor顶层内，实际CPU接入未验证。

## 300 MHz 尚未确认通过

300 MHz周期为3.333 ns。公开SpinorVpu的云端条件预算如下，余量仅是算术差值：

| 每段假设连线ps | M19 ns | M20 ns | M20相对3.333 ns余量 |
|---:|---:|---:|---:|
'''+ '\n'.join(timing)+f'''

计算/访存顶层LishiVpuMemory的三档为{compute[0]['worst']['budget_ns']:.3f}/{compute[1]['worst']['budget_ns']:.3f}/{compute[2]['worst']['budget_ns']:.3f} ns。不同顶层综合优化产生不同映射，不能将其预算相加或混用。

公开顶层100 ps假设的最大预算为{mid['budget_ns']:.3f} ns，相对300MHz周期余量{1000/300-mid['budget_ns']:+.3f} ns。路径为{mid['start']}到{mid['end']}。独立计算/访存封装100 ps档仍为{compute[1]['worst']['budget_ns']:.3f} ns，不在3.333 ns预算内。两种封装的综合映射不同，不能选择较小数字当作全设计时序结论。

预算有正余量只说明该假设下覆盖路径在预算内，不能判定器件通过300MHz；负余量提示仍应处理的路径。两版使用相同的单元、连线及建立假设。

这是Yosys未布局网表、RapidWright家族参考弧及显式连线/建立假设。346个DSP相关端点排除，未做-2速度校准、时钟树/布线、hold、RAM写或I/O时序。没有器件SDF/STA、WNS、Fmax或本轮Vivado结果。RTL/映射功能仿真通过不等于满足给定MHz。历史M5的真实OOC结果不代表M20。

## 接入与复现

CPU合同见docs/cpu-spinor-contract.md，新指令与优化见docs/m20-timing-mask-scan.md，剩余范围见docs/isa-coverage.md。仍缺排列、宽窄/定点、FP归约、完整访存、上下文/保护/一致性和实际Orbital接入。

复现：make bootstrap，然后python3 scripts/verify_m20.py；打包python3 scripts/package.py --milestone m20。receipt.json绑定本轮源码、RTL、网表、测试台与证据。没有执行Verilator或修改Valence/Orbital源码。
'''
(OUT/'evaluation.md').write_text(evaluation)
for p in OUT.iterdir():
 if p.is_file() and p.name!='receipt.json':artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M20',status='CLOUD_FP_OPTIMIZATION_AND_MASK_SCAN_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 mask_scalar=mask,mask_scan=scans,proofs=proofs,fp_lane=lane,fp_convert=convert,integer_divide=integer_divide,reductions=red,integer=old_integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,memory_cycle_deltas=memory_deltas,
 monitor=monitors,software=software,performance=perf,performance_cycle_deltas=performance_deltas,resources=resources,paths=paths,conditional_budgets=budgets,unchanged_M19_RTL=unchanged,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; SERIAL_MASK_LOGIC; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(cells('SpinorVpu')),'FF',ff(cells('SpinorVpu')))
