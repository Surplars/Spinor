#!/usr/bin/env python3
"""Bind timing cuts, reserved-encoding fixes and current regression evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m30';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m29/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m29/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane']:
 f=f'archive/m29/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m29/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m29/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m30-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m29-baseline','m30-spinor','m30-compute']:
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
fp_widening_reductions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/fp-widening-reductions/'+label;d=checked(stem+'-results.json');logs(stem);fp_widening_reductions[label]=d
 assert d['reference_anchors']==52 and d['coverage']['flushes']>0
fpwide=fp_widening_reductions['RamVectorFp-full-rtl']
assert len(fpwide['by_type'])==5 and all(fpwide['coverage'].values()) and fpwide['commands']==1664
assert fpwide['coverage']['reductions']==442 and fpwide['coverage']['illegal']==194
for key in ['commands','coverage','by_operation','by_type','performance','summary']:
 assert fp_widening_reductions['RamVectorFp-smoke-rtl'][key]==fp_widening_reductions['RamVectorFp-smoke-mapped'][key],key
for label in ['RamVector-smoke-rtl','RamVector16-smoke-rtl']:assert fp_widening_reductions[label]['coverage']['reductions']==0
fp_widen_lane={}
for label in ['rtl','smoke','mapped']:
 stem='build/fp-widen-lane/'+label;d=checked(stem+'-results.json');logs(stem);fp_widen_lane[label]=d
 assert d['extra_reference_anchors']==7 and d['base_reference_anchors']==52
assert fp_widen_lane['rtl']['vectors']==1292
for key in ['vectors','flush_reset_cases','latency','summary']:assert fp_widen_lane['smoke'][key]==fp_widen_lane['mapped'][key],key
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==39
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
for top in ['IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary','FloatingPointConvert','VectorMemoryEngine']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m30/results.json');include('build/performance-m30/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m30/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M29']['rtl_sha256']==sha(ROOT/'archive/m29/rtl/RamVectorFp.sv')
assert perf['results']['M30']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M30']['cases'])==220
for old,new in zip(perf['results']['M29']['cases'],perf['results']['M30']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m30').iterdir():
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
  table.append(f"| {'M29' if old else 'M30'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m29-baseline']['scenarios'],budgets['m30-spinor']['scenarios'],budgets['m30-compute']['scenarios'],strict=True):
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
evaluation=f"""# M30：精确FP32→FP64宽化求和归约

新增vfwredosum.vs、vfwredusum.vs，源FP32、seed/累加器/结果FP64；支持e32/m1、m2、m4、m8、mf2五种类型与5种合法frm。unordered选择规范允许的确定顺序折叠。FP16与FP64→128尚未支持；当前仍为VLEN128/ELEN64、单指令容量的部分RVV，未接真实Orbital或Linux，不能发布完整V/RVA23或misa.V声明。

## RAM与数值流水

复用M29源SEW/标量2×SEW的RAM通路和64位累加器。新增内部widenAdd操作：A来自FP32精确raw recode，B为FP64，结果直接按FP64舍入。原共享FP lane已计算三路FP32规格化与FP64 recode，只改变A的格式选择和add/convert/misc路由，复用现有FMA/round流水。不增加状态、寄存器、RAM端口、整组快照或DSP；普通运算时延不变。没有对普通FP宽化转换指令作支持声明。

FP32有限值精确提升，NaN保留signaling属性至实际求和，由浮点加法产生NV；不先把seed截成FP32，也不以FP32舍入中间结果。seed与目的各EMUL1，m8源合法；目的可与任一源或mask重叠，但seed/data是不同EEW的两个源，不能共享物理寄存器。VL0不写目的；VL>0无有效元素时原样复制FP64 seed，包括sNaN负载、qNaN负载、-0，不产生新的flags。目的低64位写回，其余tail保留，fflags与版本在完成握手才提交，flush抛弃私有状态。保留frm、源SEW不支持、非零vstart、源组对齐和masked源v0检查在VL0也执行。Monitor ABI1.0，ID0x3001/caps0x3ffff，bit17表示宽化FP归约。

## 时序优化

AVL/gather边界判断将低8位比较改为四个2位less/equal及平衡布尔组合，保持高56位非零时直接判false，消除该比较的carry链，不增加流水或周期。独立SAT miter对所有64位输入和8位limit与原数学小于关系证明等价；同一证明继续检查组几何与增量。FP recode的局部全输入证明按当前源码重新通过。这些是局部组合证明，不是整机/ISA形式合规证明。

## 验证

新增SoftFloat参考路径使用f32_to_f64后f64_add，保留转换与加法flags并规范NaN；7组新已知答案先锚定该路径，原52组参考锚点保留。混合精度lane {fp_widen_lane['rtl']['vectors']}组、{fp_widen_lane['rtl']['flush_reset_cases']}次flush/reset完整RTL通过；98组RTL/映射通过，检查高32位垃圾忽略、FP64 seed所有位、子正规、NaN/无穷/±0/舍入边界、五种frm、非法FP32输出模式和frm5/6/7、背压/tag和恢复。

完整向量 {fpwide['commands']}条命令，合法{fpwide['coverage']['reductions']}、非法{fpwide['coverage']['illegal']}、取消{fpwide['coverage']['flushes']}，覆盖5种类型、精确提升/避免FP32中间舍入、顺序敏感消去、seed高位、无有效元素的原位NaN复制、mixed-EEW源别名、目的重叠、v24..v31边界、tail、VL0、frm/vstart/对齐/v0保留检查、提交前版本与fflags保持；逐条读取32个寄存器。266条smoke当前RTL/映射结果、flags及周期一致；无FP/16位切分版负向测试保持非法。39条混合向量序列当前RTL/映射通过，涵盖新宽化FP→普通FP/INT及compress，检查模式/宽度不泄漏。

原6811组FP lane、5021组转换本轮重新通过RTL，385组FP lane重新通过映射。旧单宽FP归约5771及588映射、宽化INT归约1025及163映射、compress1229及189映射、gather3675及404映射、558个保留源别名反例当前映射，以及slide5576/index1674/prefix2888/mask-scalar10198/scan2894/单宽INT归约3418/INT乘除1673/旧INT789/FP向量2157/stream251完整RTL回归通过。原220组性能结果和周期保持M29。除FloatingPointLane外的8个数值/RF/LSU/host单元RTL按SHA保持M29，未变的局部证明和整数除法单元证据保留绑定。

公开SpinorVpu并发monitor流量下279组RTL与119组RTL/映射访存通过，末尾执行两类FP32→64归约、取消恢复、seed别名非法、tail保留和返回整数运算；独立LSU279/119组RTL及119组映射通过。Monitor2600周期RTL/映射、tiny回绕和软件文件fixture通过，尚非真实Linux内核/上板结果。归约仍为串行反馈，性能行包含准备开销，不是多指令并行。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射，RAM另占器件LUT，不是BRAM块数；全局映射差异不等于新增指令的独立成本。

## 固定云端门槛

| 每段连线假设ps | M29公开ns | M30公开ns | M30计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段下公开{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns，余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，均≤3.333ns。门槛仍锚定冻结M25家族权重与参考，M29冻结图按SHA恢复用于比较，假设未改动。

仅为条件参考。没有布局布线或ZU15EG-2校准，DSP相关端点排除，无hold/时钟树、RAM写、IO或SDF检查；物理300/500MHz仍为null，不继承M5。200ps档不满足300MHz周期，当前正余量很小。

## 复现

make bootstrap；python3 scripts/verify_m30.py；python3 scripts/package.py --milestone m30。receipt绑定当前源码、RTL/网表、SoftFloat参考与测试台、证明和冻结基线。未修改Valence或使用Verilator。后续继续宽窄整数、FP转换与更多访存模式，再推进Orbital程序闭环。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m30/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M30',status='FP_WIDENING_REDUCTIONS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M29_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; FP_WIDENING_REDUCTIONS; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
