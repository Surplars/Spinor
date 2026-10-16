#!/usr/bin/env python3
"""Bind byte-mask throughput, regression and conditional timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m21';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m20/reports/receipt.json');include('archive/m20/reports/receipt.json');include('archive/m20/reports/evaluation.md')
for old,new in [('build/rtl/RamVectorFp.sv','archive/m20/rtl/RamVectorFp.sv'),('build/rtl/SpinorVpu.sv','archive/m20/rtl/SpinorVpu.sv'),('build/synth/SpinorVpu/mapped.json','archive/m20/synth-SpinorVpu/mapped.json')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old],new;include(new)
assert sha(ROOT/'archive/m20/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala'];include('archive/m20/source/RamVector.scala')
mask={}
for folder in ['mask-scalar','mask-scan']:
 mask[folder]={}
 labels=['RamVectorFp-full-rtl','RamVectorFp-full-rtl-m20-baseline','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']
 for label in labels:
  stem='build/'+folder+'/'+label;d=checked(stem+'-results.json');mask[folder][label]=d
  assert all(d['coverage'].values())
  for suffix in ['.log','-compile.log','-assert.sv']:
   if (ROOT/(stem+suffix)).exists():include(stem+suffix)
 for k in ['commands','coverage','types','performance','summary']:
  assert mask[folder]['RamVectorFp-smoke-rtl'][k]==mask[folder]['RamVectorFp-smoke-mapped'][k],(folder,k)
 full=mask[folder]['RamVectorFp-full-rtl'];old=mask[folder]['RamVectorFp-full-rtl-m20-baseline']
 for k in ['commands','coverage','types']:assert full[k]==old[k],(folder,k)
 assert len(full['types'])==22
assert mask['mask-scalar']['RamVectorFp-full-rtl']['commands']==10198
assert mask['mask-scalar']['RamVectorFp-full-rtl']['coverage']['flush']==79
assert mask['mask-scan']['RamVectorFp-full-rtl']['commands']==2894
assert mask['mask-scan']['RamVectorFp-full-rtl']['coverage']['flush']==36
mask_performance={}
for folder,entries in mask.items():
 old=entries['RamVectorFp-full-rtl-m20-baseline']['performance'];new=entries['RamVectorFp-full-rtl']['performance']
 assert len(old)==len(new);rows=[]
 for a,b in zip(old,new,strict=True):
  assert {k:v for k,v in a.items() if k!='cycles'}=={k:v for k,v in b.items() if k!='cycles'}
  rows.append(dict(**b,old_cycles=a['cycles'],speedup=a['cycles']/b['cycles']))
 mask_performance[folder]=rows
logic=[x for x in mask_performance['mask-scalar'] if x['vl']==128 and x['vstart']==0 and x['op'].startswith('vm') and x['op'] not in ['vmv.x.s','vmv.s.x']]
assert len(logic)>=8 and all(x['cycles']==121 and x['old_cycles']==1929 for x in logic)
assert all(x['cycles']==x['old_cycles'] for x in mask_performance['mask-scalar'] if x['op'] in ['vmv.x.s','vmv.s.x'])
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
# Reuse only the unchanged units and proofs after checking their exact input
# hashes. The changed FP lane has fresh numerical tests and recode proof below.
unchanged={}
for top in ['FloatingPointConvert','IntegerLaneSplit','IntegerMultiply','IntegerDivide','VectorMemoryEngine','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel);include(rel)
reused_proofs={k:checked('build/'+k+'/results.json') for k in ['round-proof','divider-proof']}
for k in reused_proofs:
 for file in ['generate.log','proof.log']:include('build/'+k+'/'+file)
reused_units={}
for label,top,ext in [('fp-convert-rtl','FloatingPointConvert','-results.json'),('integer-divide-rtl','IntegerDivide','.json'),('integer-divide-mapped','IntegerDivide','.json')]:
 stem='build/test/'+label;name=stem+ext;d=read(name);assert d['status']=='PASS';include(name)
 rtl=f'build/synth/{top}/mapped.v' if 'mapped' in label else f'build/rtl/{top}.sv'
 assert sha(ROOT/rtl)==d['rtl_or_netlist_sha256']==base['artifact_sha256'][rtl];include(rtl)
 tb='build/test/integer-divide-tb.sv' if label.startswith('integer-divide') else stem+'-tb.sv'
 assert sha(ROOT/tb)==d['testbench_sha256'];include(tb);reused_units[label]=d
 for suffix in ['.log','.compile.log']:include(stem+suffix)
recode=checked('build/recode-proof/results.json')
for file in ['generate.log','proof.log']:include('build/recode-proof/'+file)
fp_lane=[]
for label in ['fp-lane','fp-lane-smoke','fp-lane-mapped']:
 rtl='build/synth/FloatingPointLane/mapped.v' if label.endswith('mapped') else 'build/rtl/FloatingPointLane.sv'
 d=simulation('build/test/'+label,rtl);fp_lane.append(d)
 assert d['corrupt_result_rejected'] and d['flush_reset_cases']>0
assert fp_lane[0]['vectors']==6811 and fp_lane[0]['flush_reset_cases']==205
assert fp_lane[1]['vectors']==fp_lane[2]['vectors']==385
assert fp_lane[1]['observed_latency_cycles']==fp_lane[2]['observed_latency_cycles']==base['fp_lane'][1]['observed_latency_cycles']
perf=read('build/performance-m21/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m21/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M20']['rtl_sha256']==sha(ROOT/'archive/m20/rtl/RamVectorFp.sv')
assert perf['results']['M21']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M21']['cases'])==220 and perf['results']['M21']['cases']==perf['results']['M20']['cases']
for p in (ROOT/'build/performance-m21').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m20-baseline','m21-spinor','m21-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m21-spinor','m21-compute']:
 assert budgets[label]['weights_ps']==budgets['m20-baseline']['weights_ps']
 assert budgets[label]['provenance']==budgets['m20-baseline']['provenance']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M20' if old else 'M21'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m20-baseline']['scenarios'],budgets['m21-spinor']['scenarios'],budgets['m21-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
perf_table=[]
for op,hit,vm in [('vcpop',0,1),('vfirst',127,1),('vfirst',0,1),('vfirst',-1,1),('vcpop',-1,0)]:
 row=next(x for x in mask_performance['mask-scan'] if x['op']==op and x['vl']==128 and x['first']==hit and x['vm']==vm)
 perf_table.append(f"| {op}, first={hit}, vm={vm} | {row['old_cycles']} | {row['cycles']} | {row['speedup']:.2f}× |")
regressions=[x for x in mask_performance['mask-scan'] if x['cycles']>x['old_cycles']]
regression_max=max((x['cycles']-x['old_cycles'] for x in regressions),default=0)
evaluation='''# M21：字节并行掩码执行通路

将8种掩码逻辑与vcpop/vfirst从逐位执行改为每次处理8个掩码位。VLEN128/ELEN64、单条指令在途，基础整数元素可重叠；仍为部分RVV，尚未接入实际Orbital CPU或Linux计算驱动。

## 微架构与周期

版本化RAM和单读端口保持不变，只暂存源字节、结果字节及8位有效位。掩码逻辑绕过标量ALU，每字节7周期；先读两源，再读改写候选目的字节。非整字节vstart/VL、prestart/tail、源目的重叠和v0均按原合同保留。扫描先寄存有效源字节，下一拍进行8位PopCount/优先编码与低8位计数累加，每字节4周期；找到首位后提前结束。无整组FF快照、RF副本或新增DSP。

VL=128、vstart=0的8种掩码逻辑均从1929到121周期，15.94×。这是包含提交握手的命令延迟；并非整机或应用加速比。扫描对比如下，同一独立oracle/输入、无完成背压：

| 指令与活动首位 | M20周期 | M21周期 | 加速比 |
|---|---:|---:|---:|
'''+ '\n'.join(perf_table)+f'''

字节分级有固定开销：所测扫描基准中{len(regressions)}组增加周期，最大增加{regression_max}周期，完整明细在mask_performance。特别是首字节早命中与很短的全masked向量，不能套用长向量加速比。标量搬运周期不变；旧220组整数/FP性能基准全部结果和周期与M20相同，FP向量回归仍为225358周期。

## 验证

完整RTL：mask/scalar10198条命令，3017次mask逻辑、358次标量搬运、267次非法、79次撤销；扫描2894条命令，含36次撤销。两者覆盖全部22种合法SEW/LMUL，并核对全部32个寄存器、版本表、CSR与完成前不提交。新增所有字节内边界、跨字节、末位、VL外置位、v0/源目的别名、128个one-hot索引和每个字节执行阶段的撤销。相同完整oracle在冻结M20 RTL上通过并测周期。FP版smoke的RTL与映射功能、覆盖、周期一致；无FP和16位切分版另通过smoke。

旧整数归约3418、整数乘除1673、FP向量2157、旧向量789条和streaming251条通过。混合整数/FP/归约程序通过RTL与映射；公开顶层含monitor持续读取的254组RTL及94组RTL/映射访存通过，逐用例请求和周期与M20相同，并执行mask生成/消费、标量搬运、归约与扫描。monitor ABI1.0、ID=0x2101、caps=0x3ff，生产RTL/映射及8位回绕测试通过。

FP32输入规格化改用平衡前导零树，不增加周期。完整raw32字段对固定HardFloat的全输入组合SAT等价检查重新通过；SoftFloat位精确结果/flags回归6811组与205次flush/reset，以及385组RTL/映射子集重新通过，数值单元延迟与M20相同。SHA核对确认FP转换、整数乘除、基础lane、LSU、RF、TileLink预留和独立CPU边界RTL与M20完全一致；这些未修改单元的M20证据和舍入/进位局部SAT结果按输入SHA复用。局部证明不覆盖整条VPU；独立CPU边界仍未接入实际Orbital。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

Yosys xcup未布局映射。RAM数量是分布式LUTRAM原语，不是BRAM块数，LUTRAM本身也占用器件LUT。

## 云端300 MHz参考

| 每段假设连线ps | M20公开顶层ns | M21公开顶层ns | M21计算/访存封装ns |
|---:|---:|---:|---:|
'''+ '\n'.join(timing)+'''

100ps连线假设下，公开顶层3.232ns相对3.333ns有0.101ns算术余量；计算/访存封装3.391ns超出0.058ns。两者100ps预算与M20相同。200ps档公开顶层从4.332增至4.409ns，完整对照保留在表中。

300MHz周期3.333ns。以上是Yosys未布局网表、RapidWright家族最大单元参考弧及显式50/100/200ps连线、100ps建立假设；两版权重和参考来源相同。预算内路径不代表器件通过。DSP相关端点排除，未校准-2速度档，缺布局布线/时钟树/hold、RAM写和I/O时序，没有器件SDF、STA、WNS、Fmax或本轮Vivado结果。两个封装各自综合，预算不能混用。历史M5真实OOC结果不代表M21，passes_300MHz/500MHz仍为null。

## 复现与范围

make bootstrap；python3 scripts/verify_m21.py；python3 scripts/package.py --milestone m21。源码、冻结基线、RTL、网表、测试台与证据由receipt.json的SHA绑定。详见docs/m21-byte-mask.md与docs/isa-coverage.md。完整排列/宽窄/定点、FP归约、完整LSU、系统保护/上下文与实际SoC接入仍待实现。本轮没有运行Verilator或修改Valence源码。
'''
(OUT/'evaluation.md').write_text(evaluation);include('reports/m21/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M21',status='BYTE_MASK_MICROARCHITECTURE_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 mask=mask,mask_performance=mask_performance,mask_scan_cycle_regressions=regressions,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,monitor=monitors,
 unchanged_M20_RTL=unchanged,reused_M20_proofs=reused_proofs,reused_M20_units=reused_units,recode_proof=recode,fp_lane=fp_lane,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; BYTE_MASK_ENGINE; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
