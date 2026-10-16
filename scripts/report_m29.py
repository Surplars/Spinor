#!/usr/bin/env python3
"""Bind timing cuts, reserved-encoding fixes and current regression evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m29';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m28/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m28/reports/'+name)
for name in ['RamVectorFp','SpinorVpu']:
 f=f'archive/m28/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m28/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m28/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m29-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m28-baseline','m29-spinor','m29-compute']:
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==35
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
perf=read('build/performance-m29/results.json');include('build/performance-m29/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m29/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M28']['rtl_sha256']==sha(ROOT/'archive/m28/rtl/RamVectorFp.sv')
assert perf['results']['M29']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M29']['cases'])==220
for old,new in zip(perf['results']['M28']['cases'],perf['results']['M29']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m29').iterdir():
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
  table.append(f"| {'M28' if old else 'M29'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m28-baseline']['scenarios'],budgets['m29-spinor']['scenarios'],budgets['m29-compute']['scenarios'],strict=True):
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
evaluation=f"""# M29：RAM式宽化整数归约

新增vwredsumu.vs、vwredsum.vs，支持8→16、16→32、32→64，18种合法源SEW/LMUL。源m8合法；64→128超出ELEN64，VL0也报非法。仍为VLEN128/ELEN64、单指令容量的部分RVV，不能发布完整V/misa.V/RVA23声明，尚未接实际Orbital/Linux。

## 实现与边界

源RAM地址与元素提取保持SEW/LMUL，seed、算术请求和单元素写回使用2×SEW。unsigned将窄元素零扩展，signed按窄元素符号位扩展，复用现有IntegerLane和64位reductionAccumulator，按2×SEW取模回绕。复用原seed读取、dispatch反馈、候选RAM、tail保留及完成版本提交，无新增状态、寄存器、RAM端口、整组快照或DSP。源/目标宽度选择用现有稳定owner指令和sew布尔计算，普通整数/FP路径保持原宽度。

加宽的seed和目的各为EMUL1单寄存器，不按数据LMUL对齐，目的允许与源或mask重叠。但seed与数据是不同EEW的两个源，同一物理寄存器不能同时提供二者；检查覆盖源组内每个位置，分数LMUL也按物理寄存器约束。masked data/seed v0、数据组不对齐、非零vstart、源SEW64和错误编码在VL0也拒绝，非法保持架构状态。VL0不写目的；VL>0但无有效元素时按2×SEW复制seed。目的其余tail保留，完成背压与flush不提前发布版本或修改CSR。Monitor ABI1.0，ID0x2901/caps0x1ffff，bit16表示宽化整数归约。

## 验证

独立Python参考从不可变整组数据按源SEW取有效元素，以任意精度整数进行signed/unsigned数学求和，加完整2×SEW seed后仅在最终取模；不复制RTL的宽度选择、状态机或RAM算法。完整RTL {wide['commands']}条命令，其中合法{wide['coverage']['reductions']}、非法{wide['coverage']['illegal']}、撤销{wide['coverage']['flushes']}；覆盖18种类型、跨寄存器、m8末端v24..v31、seed高位、正/负扩展、溢出、全mask关闭、VL0、所有源组位置的混合EEW seed别名、masked源v0、目的重叠及tail、未对齐标量、保留vstart/编码、完成背压和CSR保持。逐条回读全部32个寄存器并检查版本，提交前和背压期间版本保持不变。

{widening_reductions['RamVectorFp-smoke-rtl']['commands']}条smoke在当前RTL和映射网表结果/周期一致；无FP、16位切分版smoke也通过。35条混合向量序列在INT/FP/同宽归约/宽化归约/compress/gather之间交替，当前RTL和映射均通过，检查算术宽度与signed控制不泄漏。公开SpinorVpu并发monitor流量下，279组RTL及119组RTL/映射访存回归通过，末尾执行两类32→64归约、取消、源别名非法、tail保留和返回普通整数执行。独立物理LSU279/119组RTL及119组映射通过；monitor2600周期RTL/映射、tiny回绕和用户态fixture通过。

旧FP归约5771条完整RTL及588条RTL/映射重新通过，包含FP32/64和flags。旧compress1229、gather3675、slide5576、index1674、prefix2888、mask/scalar10198、scan2894、单宽整数归约3418、INT乘除1673、旧整数789、FP向量2157、streaming251重新通过RTL；compress/gather smoke及558个保留源别名反例在当前映射通过。原220组性能结果和周期保持M28。FP、转换、整数数值单元、RF、物理LSU等9个单元RTL与M28的SHA一致，复用已绑定的6811组FP、5021组转换及局部数值证明；这不冒充本轮完整顶层测试。

新宽化归约仍为串行反馈，性能行见receipt，包含准备与命令开销，不是多指令并行。e8/m8、VL128、无完成背压时128/64个有效元素分别1421/781拍。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；RAM另占器件LUT，不是BRAM数量。全局映射变化不等于新增指令本身的增量成本。

## 固定云端门槛

| 每段连线假设ps | M28公开ns | M29公开ns | M29计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

原100ps/段及家族权重下公开{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns，余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，均≤300MHz周期3.333ns。公开顶层条件余量很小。门槛仍锚定冻结M25权重/参考，M28冻结图按SHA恢复用于比较，未改变假设。

未布局布线、未按ZU15EG-2校准；DSP相关端点排除，无时钟树/hold、RAM写、IO或SDF验证。物理300/500MHz通过字段仍为null，不继承旧M5结果。200ps档不满足300MHz周期。

## 复现

make bootstrap；python3 scripts/verify_m29.py；python3 scripts/package.py --milestone m29。receipt绑定源码、当前RTL/网表、独立参考/测试台、局部证明和冻结基线。未修改Valence或使用Verilator。后续继续宽窄整数、宽化FP归约与更多访存模式，再推进实际Orbital程序闭环。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m29/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M29',status='WIDENING_INTEGER_REDUCTIONS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M28_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; WIDENING_INTEGER_REDUCTIONS; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
