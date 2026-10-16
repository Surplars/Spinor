#!/usr/bin/env python3
"""Bind narrowing shifts, frozen local baseline and fixed cloud timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m32';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m31/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m31/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane']:
 f=f'archive/m31/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m31/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m31/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m32-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m31-baseline','m32-spinor','m32-compute']:
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==52
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
for top in ['FloatingPointLane','IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary','FloatingPointConvert','VectorMemoryEngine']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m32/results.json');include('build/performance-m32/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m32/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M31']['rtl_sha256']==sha(ROOT/'archive/m31/rtl/RamVectorFp.sv')
assert perf['results']['M32']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M32']['cases'])==220
for old,new in zip(perf['results']['M31']['cases'],perf['results']['M32']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m32').iterdir():
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
  table.append(f"| {'M31' if old else 'M32'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m31-baseline']['scenarios'],budgets['m32-spinor']['scenarios'],budgets['m32-compute']['scenarios'],strict=True):
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
extensions={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/integer-extensions/'+label;d=checked(stem+'-results.json');logs(stem);extensions[label]=d
 assert all(d['coverage'].values())
assert extensions['RamVectorFp-full-rtl']['commands']==4212 and len(extensions['RamVectorFp-full-rtl']['types'])==15
for key in ['commands','coverage','types','performance','summary']:
 assert extensions['RamVectorFp-smoke-rtl'][key]==extensions['RamVectorFp-smoke-mapped'][key],key
narrowing={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVectorFp-smoke-mapped','RamVector-smoke-rtl','RamVector16-smoke-rtl']:
 stem='build/narrowing-shifts/'+label;d=checked(stem+'-results.json');logs(stem);narrowing[label]=d
 assert all(d['coverage'].values())
full_narrow=narrowing['RamVectorFp-full-rtl']
assert full_narrow['commands']==4945 and len(full_narrow['types'])==15
assert full_narrow['coverage']['illegal']==1753 and full_narrow['coverage']['flush']==198
for key in ['commands','coverage','types','performance','summary']:
 assert narrowing['RamVectorFp-smoke-rtl'][key]==narrowing['RamVectorFp-smoke-mapped'][key],key
local_base=read('archive/m31/local-report/receipt.json')
assert local_base['passes_300MHz_current_OOC_constraints'] is True
assert local_base['routed']['WNS_ns']==0.392 and local_base['routed']['WHS_ns']==0.009
for name in ['receipt.json','evaluation.md']:include('archive/m31/local-report/'+name)
evaluation=f"""# M32：整数窄化移位

新增vnsrl.wv/wx/wi和vnsra.wv/wx/wi，共6种编码；覆盖16→8、32→16、64→32的15种合法SEW/LMUL组合。源vs2的EEW和EMUL为目的的两倍；vs1移位量向量仍按目的SEW/LMUL读取。shift取低log2(2×SEW)位，wi使用无符号5位立即数；wx配合x0可执行vncvt.x.x.w伪指令。SEW64→128超出ELEN64、目的LMUL=m8使源EMUL=16，均保留非法。仍为部分RVV、单指令容量，未接实际Orbital/Linux，不能发布完整V/RVA23或misa.V声明。

## RAM和微架构

复用M31源SEW寄存器、现有RAM端口、64位a/b暂存和原整数分级移位流水。dispatch按宽源寻址，captureA之后将vs1地址恢复为目的SEW；整数lane按宽源位宽移位，流水返回时按目的SEW的tag/字节mask截断写回。无新状态、DSP、整组寄存器快照或流水级，9个FP/整数/RF/LSU/host单元RTL保持M31。

源组按自身EMUL对齐；目的与宽源重叠时必须位于最低部分（vd=vs2）。窄源vs1与宽源vs2的不同EEW物理别名保留非法；目的与vs1的同宽重叠可用。支持mask、tail undisturbed、合法vstart及VL0检查。fflags/vxrm/vxsat保持不变，提交握手才切换目的版本，flush抛弃候选结果。Monitor ABI1.0，ID0x3201，caps0xfffff，bit19表示窄化整数移位。

新源对齐布尔表达式由全输入SAT与独立计数表对照；原组重叠/最高部分、增量、地址和配置比较证明继续通过。

## 验证

完整窄化RTL测试4945条命令，1566条合法窄化指令（含空操作）、1753次非法拒绝、198个取消场景，覆盖15种合法类型；逐条对照32个寄存器、版本与配置。覆盖宽源与窄移位向量跨寄存器、算术负数、高移位位、超宽scalar、uimm16..31、最低重叠、v24..v31边界、mask/tail、VL0、vstart、源别名及取消恢复。489条smoke当前RTL/映射的数值、版本和周期一致；无FP与16位切分版各487条smoke通过。52条混合指令RTL/映射通过，包含窄化→扩展→FP FMA（同funct6不同funct3）→compress，检查模式切换。

原整数扩展4212/884、FP宽化归约1664/266、单宽FP归约5771/588、宽化INT归约1025/163、compress1229/189、gather3675/404的完整RTL与smoke映射继续通过。旧源别名、slide/index/prefix/mask/INT归约、乘除、FP向量、streaming完整RTL回归通过，220组旧性能周期保持M31。未改动数值单元与局部证明复用按原输入SHA绑定的已通过证据；冷启动verify会重跑它们。

公开SpinorVpu并发monitor下279组完整RTL及119组RTL/映射访存通过，末尾执行窄化wx/wi/wv、masked保留、flush与非法混合EEW源别名。独立LSU279/119 RTL及119映射通过；monitor2600周期RTL/映射、tiny与软件fixture通过。不是实际Linux或上板验证。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；RAM另占LUT，非BRAM块数。新指令复用原分级shift，FF/DSP/RAM计数保持M31。M31本地Vivado使用14173总LUT、11605FF、7DSP、2RAMB36，工具映射拓扑不同，不能把该物理资源计数直接当成M32结果。

## 固定云端门槛与本地基线

| 每段连线假设ps | M31公开ns | M32公开ns | M32计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段下公开{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns，余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，均≤3.333ns。仍使用冻结M25权重/锚点，按SHA恢复M31图对比，未改变权重或连线假设。

M31本地报告作为冻结基线保留：Vivado2025.1、ZU15EG-2、3.333ns，setup+0.392ns、hold+0.009ns、布线错误0、两组XSim通过。HD.CLK_SRC及613个输入/608个输出的接口延迟未设，仍非完整SoC时序签核。M32改变了RTL，不能继承M31的本地通过结论。

M32只经过云端条件预算，无布局布线/速度档校准，DSP相关端点排除，没有hold、时钟树、RAM写、接口或SDF检查；当前物理300/500MHz均未知。200ps/段档不满足300MHz，公开顶层100ps档余量也较小。

## 复现和交付

make bootstrap；python3 scripts/verify_m32.py；python3 scripts/package.py --milestone m32。完整包包含当前源码/RTL、测试与网表、冻结M25/M31图及M31本地报告。此轮无新的Windows执行包，不要求立即重跑本地；先在云端推进功能并保留M31实测比较基线。旧M31 Windows包用于验证M31，不能代表M32。未修改Valence或调用Verilator。下一步继续宽化算术/定点与FP宽窄转换、访存模式和Orbital接入。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m32/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M32',status='NARROWING_SHIFTS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 narrowing_shifts=narrowing,integer_extensions=extensions,local_M31_baseline=local_base,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M31_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; NARROWING_SHIFTS; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
