#!/usr/bin/env python3
"""Bind prefix-mask ISA, byte execution, regression and timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m22';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m21/reports/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m21/reports/'+name)
for old,new in [('build/rtl/RamVectorFp.sv','archive/m21/rtl/RamVectorFp.sv'),('build/rtl/SpinorVpu.sv','archive/m21/rtl/SpinorVpu.sv')]:
 assert sha(ROOT/new)==base['artifact_sha256'][old];include(new)
assert sha(ROOT/'archive/m21/source/RamVector.scala')==base['source_sha256']['src/main/scala/vpu/RamVector.scala'];include('archive/m21/source/RamVector.scala')
restored=checked('build/baseline-m21/results.json')
assert restored['restored_sha256']==sha(ROOT/restored['output'])==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json'];include(restored['output'])
prefix={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/mask-prefix/'+label;d=checked(stem+'-results.json');prefix[label]=d;assert all(d['coverage'].values())
 for suffix in ['.log','-compile.log','-assert.sv']:
  if (ROOT/(stem+suffix)).exists():include(stem+suffix)
full=prefix['RamVectorFp-full-rtl'];assert full['commands']==2890 and len(full['types'])==22
assert full['coverage']['flush']==75 and full['coverage']['illegal']==431
assert sum(full['coverage'][k] for k in ['before','only','including'])==1505
for k in ['commands','coverage','types','performance','summary']:assert prefix['RamVectorFp-smoke-rtl'][k]==prefix['RamVectorFp-smoke-mapped'][k],k
long=[x for x in full['performance'] if x['vl']==128];assert len(long)>=9 and all(x['cycles']==105 for x in long)
assert {x['first'] for x in long}=={-1,0,127}
prefix_proof=checked('build/mask-prefix-proof/results.json')
for name in ['generate.log','proof.log']:include('build/mask-prefix-proof/'+name)
mask={}
for folder in ['mask-scalar','mask-scan']:
 stem='build/'+folder+'/RamVectorFp-full-rtl';d=checked(stem+'-results.json');mask[folder]=d
 for k in ['commands','coverage','types','performance','summary']:assert d[k]==base['mask'][folder]['RamVectorFp-full-rtl'][k],(folder,k)
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
 for instruction in ['5230a3d7','5031a3d7','52312057','5000a3d7','5230a1d7','50312057','00880457']:
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
perf=read('build/performance-m22/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m22/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M21']['rtl_sha256']==sha(ROOT/'archive/m21/rtl/RamVectorFp.sv')
assert perf['results']['M22']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M22']['cases'])==220 and perf['results']['M22']['cases']==perf['results']['M21']['cases']
for p in (ROOT/'build/performance-m22').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
budgets={}
for label in ['m21-baseline','m22-spinor','m22-compute']:
 d=read('build/timing-budget/'+label+'/budget.json');budgets[label]=d
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None and not d['speed_grade_calibrated']
 for n in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+n)
for label in ['m22-spinor','m22-compute']:
 assert budgets[label]['weights_ps']==budgets['m21-baseline']['weights_ps']
 assert budgets[label]['provenance']==budgets['m21-baseline']['provenance']
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
table=[]
for top in ['SpinorVpu','LishiVpuMemory']:
 for old in [True,False]:
  c=(base['resources'] if old else resources)[top]['mapped_cells'];assert (c['DSP48E2'],c['RAM64M8'],c['RAM32M16'])==(9,32,6)
  table.append(f"| {'M21' if old else 'M22'} {top} | {lut(c)} | {ff(c)} | {c['DSP48E2']} | {c['RAM64M8']} | {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m21-baseline']['scenarios'],budgets['m22-spinor']['scenarios'],budgets['m22-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=budgets['m22-spinor']['scenarios'][1]['worst'];compute=budgets['m22-compute']['scenarios'][1]['worst']
evaluation=(
    '''# M22：前缀掩码指令

新增vmsbf.m、vmsif.m、vmsof.m，分别生成首个有效置位之前、包含首位、仅首位的掩码。仍为VLEN128/ELEN64、单条指令在途的部分RVV，未接入实际Orbital或Linux计算驱动。

## 语义与实现

支持v0.t、全部22种合法SEW/LMUL，源和目的各为单个mask寄存器，忽略组对齐。非零vstart、vd=vs2，以及masked时vd=v0非法；限制在vl=0时同样检查。合法完成清vstart，非法或撤销不改变架构状态。尾部和inactive位采用保留原值的合法策略。

复用M21字节通路：dispatch、源读/取、字节前缀、候选目的读/写，每次8个mask元素、6周期。先按VL和v0过滤源，再做小规模前缀OR，以1个seen位跨字节携带“此前存在有效置位”。结果和有效字节仍复用原寄存器，不新增整组快照或RF副本。完成握手才提交版本；flush取消候选写。VL=128三条指令均为105周期，包含命令/完成握手；命中位置不改变周期，因为后续有效目的位仍需写零。

## 验证

独立Python模型先求整条向量的首个有效置位索引，再按索引写结果，不复用字节前缀算法。完整RTL2890条命令：1505次合法前缀、431次非法、75次撤销，核对全部32个向量寄存器、版本表、CSR、完成背压与提交。覆盖22种类型、128个one-hot位置、跨字节、VL外置位、v0源/目的、无置位、全masked、零VL以及所有重叠限制。保留原FP/定点CSR并验证不泄漏。

277条命令的FP版smoke在RTL与映射网表中覆盖、功能、周期一致；无FP/16位切分版另通过smoke。字节helper的2048种source/seen/selector组合通过SAT，与独立的最低置位隔离及减法公式等价。该证明只覆盖组合helper；实际FSM、RAM、flush和提交由仿真验证。

原mask/scalar10198条、扫描2894条、归约3418条、整数乘除1673条、FP向量2157条、旧向量789条、streaming251条重新通过RTL。原220组整数/FP性能和旧mask/扫描基准的结果与周期均和M21相同。FP向量仍为225358周期。混合INT/FP/归约程序通过RTL与映射。

默认访存封装254组RTL通过；公开SpinorVpu在持续monitor读取时通过254组RTL及94组RTL/映射子集。逐访存用例请求与周期和M21相同；测试台末尾增加真实前缀命令、取消、非法重叠、v0生成/消费及返回masked vadd，所以总测试周期增加。monitor ABI1.0，ID=0x2201/caps=0x7ff，bit10表示这三条前缀指令；生产RTL/映射与8位计数回绕检查通过。

SHA确认9个数值/访存/RF/CPU边界单元RTL与M21完全一致，按输入SHA复用既有数值单测、映射单测及局部舍入/重编码/进位证明。本轮未重跑这些未修改单元；局部证明不覆盖整条VPU。实际Orbital接入仍未验证。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
'''
    + '\n'.join(table)
    + '''

Yosys xcup未布局映射。RAM原语是分布式LUTRAM，不是BRAM块数；这些RAM也消耗器件LUT。

## 云端条件时序

| 每段假设连线ps | M21公开顶层ns | M22公开顶层ns | M22计算/访存封装ns |
|---:|---:|---:|---:|
'''
    + '\n'.join(timing)
    + f'''

100ps档公开顶层{mid['budget_ns']:.3f}ns，相对300MHz的3.333ns算术余量{1000/300-mid['budget_ns']:+.3f}ns；计算/访存封装{compute['budget_ns']:.3f}ns，余量{1000/300-compute['budget_ns']:+.3f}ns。公开顶层覆盖路径为{mid['start']}到{mid['end']}。两种封装各自综合，不能混用预算。

使用相同的Yosys网表分析、RapidWright家族参考弧、50/100/200ps连线与100ps建立假设。M21图从gzip冻结包恢复后核对原始SHA，两版权重/来源一致。没有放置布线、-2速度校准、DSP相关路径、时钟树/hold、RAM写或I/O时序，没有器件SDF/STA、WNS或Fmax。本轮未执行Vivado，300/500MHz是否通过仍为null；M5的真实OOC结果不能继承。

## 复现与剩余范围

make bootstrap；python3 scripts/verify_m22.py；python3 scripts/package.py --milestone m22。receipt.json绑定源码、冻结基线、RTL、网表、测试台和证据。完整复现入口会重新生成复用单元的证据。见docs/m22-prefix-mask.md与docs/isa-coverage.md。viota/vid、排列、宽窄/定点、FP归约、完整LSU、系统保护/上下文和真实SoC接入仍未完成，不声明完整V/RVA23。本轮未运行Verilator或修改Valence源码。
'''
)
(OUT/'evaluation.md').write_text(evaluation);include('reports/m22/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M22',status='PREFIX_MASK_INSTRUCTIONS_EVALUATED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 mask_prefix=prefix,mask_prefix_proof=prefix_proof,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,memory=memory,spinor_integration=soc,monitor=monitors,
 unchanged_M21_RTL=unchanged,reused_M21_proofs=reused_proofs,reused_M21_units=reused_units,performance=perf,resources=resources,paths=paths,conditional_budgets=budgets,restored_baseline=restored,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; BYTE_PREFIX_MASK_ENGINE; PHYSICAL_NORMAL_RAM_ONLY; CONDITIONAL_TIMING_NOT_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
