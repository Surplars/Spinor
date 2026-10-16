#!/usr/bin/env python3
"""Freeze integer reductions, public Spinor top, host boundary and telemetry."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m18';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
artifacts=set()
def include(name):
 p=ROOT/name;assert p.is_file(),p;artifacts.add(p)
def checked(name):
 d=read(name);assert d['status']=='PASS',name
 for p,h in d.get('sha256',{}).items():assert sha(ROOT/p)==h,p;include(p)
 include(name);return d
def result(name,rtl,tb):
 d=checked(name);assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),name
 assert d['testbench_sha256']==sha(ROOT/tb),name
 include(rtl);include(tb);return d
base=read('archive/m17/reports/receipt.json')
assert sha(ROOT/'archive/m17/rtl/RamVectorFp.sv')==base['artifact_sha256']['build/rtl/RamVectorFp.sv']
assert sha(ROOT/'archive/m17/synth-LishiVpuMemory/mapped.json')==base['artifact_sha256']['build/synth/LishiVpuMemory/mapped.json']
assert sha(ROOT/'archive/m17/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala']
for n in ['archive/m17/reports/receipt.json','archive/m17/rtl/RamVectorFp.sv','archive/m17/synth-LishiVpuMemory/mapped.json','archive/m17/source/RamVector.scala']:include(n)
oldzip=ROOT/'lishi-vpu-m17.zip'
if oldzip.exists():assert sha(oldzip)=='6dfa23549faa6739f403bf64225ad145361cc86f81c97d32deccf93f14eb3920'
reductions=[]
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/reductions/'+label;d=checked(stem+'-results.json')
 assert d['coverage']['flushes']==10 and len(d['by_operation'])==8 and all(d['by_operation'].values())
 for key in ['all_masked','masked_vd0','unaligned_scalar','aliases','illegal']:assert d['coverage'][key]>0
 for suffix in ['.log','-compile.log']:include(stem+suffix)
 p=ROOT/(stem+'-assert.sv')
 if p.exists():artifacts.add(p)
 reductions.append(d)
assert len(reductions[0]['by_type'])==22 and reductions[0]['coverage']['reductions']==1411
assert reductions[0]['coverage']['zero_vl']>0
assert reductions[0]['coverage']['illegal']==210
for k in ['coverage','by_operation','by_type','performance','summary']:assert reductions[1][k]==reductions[2][k],k
mixed=[];host=[]
for label in ['rtl','mapped']:
 for folder,target in [('build/reduction-interleave',mixed),('build/host-boundary',host)]:
  target.append(checked(folder+'/'+label+'-results.json'))
  for suffix in ['.log','-compile.log']:include(folder+'/'+label+suffix)
assert mixed[0]['vector_instructions']==mixed[1]['vector_instructions']==7
assert host[0]['summary']==host[1]['summary']
assert 'replies=112 cancels=16 poisons=6' in host[0]['summary']
fp=result('build/test/fp-vector-m9-convert-results.json','build/rtl/RamVectorFp.sv','build/test/fp-vector-m9-convert-tb.sv')
assert fp['commands']==2157 and fp['write_stage_assertions_enabled']
assert fp['test_summary']==base['fp_tests'][3]['test_summary']
include('build/test/fp-vector-m9-convert.log')
stream=result('build/test/streaming-rtl.json','build/rtl/RamVectorFp.sv','build/test/streaming-rtl-tb.sv');assert stream['commands']==251
integer=read('build/test/m7-div-fp-results.json');assert integer['commands']==1673
assert integer['input_sha256']['RamVectorFp']['rtl']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert integer['input_sha256']['RamVectorFp']['testbench']==sha(ROOT/'build/test/m7-div-fp-tb.sv')
assert integer['models']['RamVectorFp'].startswith('PASS ram-vector commands=1673')
for n in ['m7-div-fp-results.json','m7-div-fp-tb.sv','RamVectorFp.log']:include('build/test/'+n)
legacy=read('build/test/ram-vector-results.json');assert legacy['commands']==789
for top in ['RamVector','RamVector16','RamVectorFlops']:
 assert legacy['input_sha256'][top]['rtl']==sha(ROOT/f'build/rtl/{top}.sv')
 assert legacy['input_sha256'][top]['testbench']==sha(ROOT/'build/test/ram_vector_tb.sv')
 assert legacy['models'][top].startswith('PASS ram-vector commands=789');include('build/test/'+top+'.log')
include('build/test/ram-vector-results.json');include('build/test/ram_vector_tb.sv')
memory=[];soc=[]
for folder,top,tests in [('build/test','LishiVpuMemory',memory),('build/monitor/integration-spinor','SpinorVpu',soc)]:
 for label,count in [('rtl',254),('smoke',94),('mapped',94)]:
  stem=folder+'/vector-memory-'+label
  rtl=f'build/synth/{top}/mapped.v' if label=='mapped' else f'build/rtl/{top}.sv'
  d=result(stem+'-results.json',rtl,stem+'-tb.sv');assert d['memory_cases']==count
  assert d['stop_cases']==(77 if label=='rtl' else 9)
  if label!='mapped':assert d['assertions_enabled']
  for suffix in ['.log','.compile.log']:include(stem+suffix)
  if label!='mapped':
   for module in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+module+'-assert.sv')
  if top=='SpinorVpu':
   log=(ROOT/(stem+'.log')).read_text();assert 'PASS monitored-mmio' in log
   assert "32'h02882c57" in (ROOT/(stem+'-tb.sv')).read_text()
  tests.append(d)
 assert tests[0]['metrics']==base['memory_tests'][0]['metrics']
 assert tests[1]['metrics']==tests[2]['metrics']
monitors=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped','VpuMonitor-base-rtl']:
 stem='build/monitor/test/'+label;d=checked(stem+'-results.json');assert d['cycles']==2600
 for suffix in ['.log','-compile.log']:include(stem+suffix)
 monitors.append(d)
assert monitors[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert monitors[0][k]==monitors[2][k]
software=checked('build/monitor/software/results.json');include('build/monitor/software/decoded.json')
perf=read('build/performance-m18/results.json')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m18/performance-tb.sv')
assert perf['results']['M17']['rtl_sha256']==sha(ROOT/'archive/m17/rtl/RamVectorFp.sv')
assert perf['results']['M18']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M18']['cases'])==220 and perf['results']['M17']['cases']==perf['results']['M18']['cases']
for p in (ROOT/'build/performance-m18').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
summaries={};paths={}
for top in ['RamVectorFp','LishiVpuMemory','SpinorVpu','VpuHostBoundary','VpuMonitor']:
 summaries[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m17-baseline','m18','spinor-m18']:
 d=read('build/timing-budget/'+label+'/budget.json')
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None
 budgets[label]=d
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m18','spinor-m18']:
 for before,after in zip(budgets['m17-baseline']['scenarios'],budgets[label]['scenarios'],strict=True):
  assert before['assumed_link_ps']==after['assumed_link_ps'] and after['worst']['budget_ns']<=before['worst']['budget_ns']
cells=summaries['LishiVpuMemory']['mapped_cells'];public=summaries['SpinorVpu']['mapped_cells']
for c in [cells,public]:assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
assert lut(cells)==14790 and ff(cells)==10209
unchanged={}
for top in ['IntegerLaneSplit','FloatingPointLane','IntegerMultiply','IntegerDivide','FloatingPointConvert','VectorMemoryEngine','TileLinkReservation','VersionedRegisterFileRam']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;unchanged[top]=sha(ROOT/rel)
references=(ROOT/'docs/references/reductions-v1.0.txt').read_text()
names=['vredsum','vredand','vredor','vredxor','vredminu','vredmin','vredmaxu','vredmax']
for code,name in enumerate(names):assert re.search(r'^'+name+r'\.vs\s+31\.\.26=0x0'+str(code)+r' vm vs2 vs1 14\.\.12=0x2 vd 6\.\.0=0x57$',references,re.M),name
include('docs/references/reductions-v1.0.txt')
for p in (ROOT/'build/rtl').rglob('*'):
 if p.is_file() and p.suffix=='.sv':artifacts.add(p)
for p in (ROOT/'build/monitor/rtl').rglob('*'):
 if p.is_file():artifacts.add(p)
rows=[]
for b in budgets['spinor-m18']['scenarios']:
 rows.append(f"| {b['assumed_link_ps']} | {b['worst']['budget_ns']:.3f} |")
evaluation=f'''# M18：砺矢 · Spinor VPU

Valence SoC / Orbital CPU / Spinor VPU。公开可综合顶层SpinorVpu，内部保留Lishi/RamVector兼容名称。新增8条单宽整数归约和独立VpuHostBoundary；不包含实验OoO窗口，没有实际Orbital或Linux计算驱动集成，仍非完整RVV/RVA23。

## 功能证据

归约完整RTL：{reductions[0]['commands']}条命令，其中1411次合法归约、210次非法指令，22种合法SEW/LMUL组合、8种运算、10次flush。任意scalar种子/目的、重叠v0/源组、掩码、vl0、vstart、尾部与签名极值均覆盖，每次读取全部32个寄存器和版本图。映射smoke为{reductions[2]['commands']}条命令，结果、覆盖与周期均同RTL；另测无FP与16位分段版本。

7条混合向量程序在RTL/映射上均通过：归约→普通streaming加法→归约→MUL→归约→FP→归约；使用非零fflags/frm/vxrm/vxsat检查保留，并读取所有寄存器。是有限差分验证，不是全状态形式化或合规测试。

原有1673条整数/乘除、2157条FP向量、789条旧版向量和251条streaming回归通过，220组旧性能用例逐项周期不变。默认RAM访存254组RTL/94组映射；公开SpinorVpu在持续monitor读取时另外通过254组RTL/94组映射，并实际执行vset+vredsum、验证尾部与算术取消。所有访存逐用例性能指标与M17相同，总周期差值来自新增末尾指令和监控检查。

Host boundary的RTL/映射各128次事务（112次返回、16次取消）及6类粘滞协议错误检查通过，含80位token高位、防止坏完成触发提交、load/store错因、stop保留所有权和反压。使用合成CPU/VPU对端，尚非真实Orbital测试。

Monitor生产RTL/映射、8位回绕和非零基址各2600周期通过，ABI1.0保留，ID=0x1801/caps=0x7f；UIO工具通过编译/文件夹具，未在真实Linux设备上运行。历史monitor-v1/OOO报告不代表本轮新功能的集成状态。

## 资源与周期

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M17 LishiVpuMemory | 14530 | 10143 | 9 | 32 | 6 |
| M18 LishiVpuMemory | {lut(cells)} | {ff(cells)} | 9 | 32 | 6 |
| M18 SpinorVpu（含monitor） | {lut(public)} | {ff(public)} | 9 | 32 | 6 |

归约复用现有流水线，新增一个64位标量累加寄存器，计算顶层总计增加66 FF和260 LUT；没有新增DSP/向量RAM副本或整组FF快照。RAM资源为分布式映射，不是BRAM数量。独立Host boundary另为{lut(summaries['VpuHostBoundary']['mapped_cells'])} LUT/{ff(summaries['VpuHostBoundary']['mapped_cells'])} FF，尚未算入Spinor顶层；不能由独立单元预算相加推算完整SoC时序。

无completion反压的vredsum m8，SEW8/16/32/64对应VL128/64/32/16，延迟1421/717/365/189周期。串行反馈约11周期/活动元素；不是并行归约树，不是测得的应用带宽或Fmax。

## 云端条件预算

公开SpinorVpu和默认计算顶层均保持M17条件预算：

| 每段假设连线ps | SpinorVpu ns |
|---:|---:|
'''+ '\n'.join(rows)+'''

Yosys未布局网表、RapidWright家族单元参考和显式连线/建立假设；346个DSP相关端点排除，没有-2校准、时钟树/布线/hold/RAM写/I/O signoff。不是STA、WNS或300/500MHz通过。实际器件时序基线仍只有历史M5，本轮无Vivado执行。

## 接入与剩余工作

CPU连接、不可撤销授权、访存前缀/停止、非法与访问错误见docs/cpu-spinor-contract.md；完整缺失范围见docs/isa-coverage.md。PS ARM与PL RISC-V共享monitor ABI，两个Linux需要单一快照写所有者。原生RISC-V Linux仍缺完整ISA、VS/FS/上下文、保护/翻译、一致性和精确异常接入；ARM还缺计算作业队列或代理。

复现：python3 scripts/verify_m18.py；打包：python3 scripts/package.py --milestone m18。每份源码、RTL、网表、测试台和报告的SHA见receipt.json。没有Valence/Orbital源码改动，没有安装或调用Verilator。
'''
(OUT/'evaluation.md').write_text(evaluation)
for p in OUT.rglob('*'):
 if p.is_file() and p.name!='receipt.json':artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',name_zh='砺矢',soc='Valence',cpu='Orbital',public_top='SpinorVpu',milestone='M18',status='CLOUD_INTEGER_REDUCTIONS_HOST_BOUNDARY_AND_SPINOR_TOP_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 reductions=reductions,mixed_program=mixed,host_boundary=host,integer_vector=integer,legacy_vector=legacy,fp_vector=fp,streaming=stream,memory=memory,spinor_integration=soc,monitor=monitors,software=software,performance=perf,
 resources=summaries,paths=paths,conditional_budgets=budgets,unchanged_M17_RTL=unchanged,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 base_M17_zip_sha256='6dfa23549faa6739f403bf64225ad145361cc86f81c97d32deccf93f14eb3920',
 scope='PARTIAL_RVV; ONE_INSTRUCTION; NO_EXPERIMENTAL_OOO_IN_DATAPATH; PHYSICAL_NORMAL_RAM_ONLY; MEMORY_STOP_DEFERRED')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(public),'FF',ff(public))
