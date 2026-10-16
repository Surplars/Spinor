#!/usr/bin/env python3
"""Bind timing cuts, reserved-encoding fixes and current regression evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m26';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m25/reports/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m25/reports/'+name)
for name in ['RamVectorFp','SpinorVpu']:
 f=f'archive/m25/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala']:
 f='archive/m25/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m25/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
gate=checked('build/timing-budget/m26-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m25-baseline','m26-spinor','m26-compute']:
 budgets[label]=read('build/timing-budget/'+label+'/budget.json')
 for suffix in ['json','md']:include(f'build/timing-budget/{label}/budget.{suffix}')
 for p,h in budgets[label]['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)

families={}
for folder in ['gather','slide','index-generate','mask-prefix']:
 data={}
 labels=['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']
 if folder=='gather':labels+=['RamVectorFp-smoke-mapped']
 for label in labels:
  stem=f'build/{folder}/{label}';d=checked(stem+'-results.json');logs(stem);data[label]=d
  assert all(d['coverage'].values()),(folder,label)
 assert len(data['RamVectorFp-full-rtl']['types'])==22
 families[folder]=data
for k in ['commands','coverage','types','performance','summary']:
 assert families['gather']['RamVectorFp-smoke-rtl'][k]==families['gather']['RamVectorFp-smoke-mapped'][k]
assert families['slide']['RamVectorFp-full-rtl']['coverage']['masked_source_v0']==134
prefix=families['mask-prefix']['RamVectorFp-full-rtl'];assert prefix['commands']==2888
assert all(x['cycles']==105 for x in prefix['performance'] if x['vl']==128)
aliases={}
for label in ['RamVectorFp-rtl','RamVector-rtl','RamVector16-rtl','RamVectorFp-mapped']:
 stem='build/mask-source-alias/'+label;aliases[label]=checked(stem+'-results.json');logs(stem)
 assert aliases[label]['coverage']['legal_zero_fields']>0
for k in ['commands','reserved_cases','coverage','summary']:assert aliases['RamVectorFp-rtl'][k]==aliases['RamVectorFp-mapped'][k]
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==19
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
old_lat=base['reused_M24_units']['fp-lane']['observed_latency_cycles']
for key,lat in units['fp-lane']['observed_latency_cycles'].items():
 op=int(re.search(r'_op(\d+)',key)[1]);delta=2 if op<=8 and 'illegal' not in key else 0
 assert lat==[x+delta for x in old_lat[key]],(key,lat,old_lat[key])
unchanged={}
for top in ['IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m26/results.json');include('build/performance-m26/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m26/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M25']['rtl_sha256']==sha(ROOT/'archive/m25/rtl/RamVectorFp.sv')
assert perf['results']['M26']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M26']['cases'])==220
for old,new in zip(perf['results']['M25']['cases'],perf['results']['M26']['cases'],strict=True):
 delta=2*new['active_elements']*new['instructions'] if new['operation']=='vfadd' else 0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m26').iterdir():
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
  table.append(f"| {'M25' if old else 'M26'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m25-baseline']['scenarios'],budgets['m26-spinor']['scenarios'],budgets['m26-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=gate['results']['SpinorVpu'];compute=gate['results']['LishiVpuMemory']
evaluation=f"""# M26：舍入/IEEE封装分级与保留编码检查

继续完善Spinor本体；没有新增指令种类，仍为部分RVV、VLEN128/ELEN64、单条指令容量。公开顶层SpinorVpu，目标ZU15EG-2。未接实际Orbital或Linux，不声明完整V/RVA23。

## 实现

StagedRound在指数修正、overflow/underflow判断和特殊值封装之间增加一级。FloatingPointLane的FP32/64转IEEE先寄存指数、非规格化移位距离及有效数，再执行移位、NaN规范化和回应封装。FMA族及DIV/SQRT相对M25每有效元素增加2拍，整数转FP增加1拍；FP比较/分类/符号、FP转整数与整数执行周期不变。完成背压保持tag/flags/data；flush清除owner，不发布旧响应。

索引递增与mask字节推进改用已有ParallelIncrement，保留8位推进到128的语义，没有增加元素周期。增量器证明扩展5位宽；没有新增RF读端口、快照或整组FF数组。RF仍是双版本64×128、同步读取和字节写使能的LUTRAM。

统一普通INT/FP/乘除/归约/滑移的执行mask与v0数据源双EEW别名检查，归约seed也算SEW源。LSU拒绝masked store v0；masked load v0同样非法。非法检查在VL0、全mask关闭和vstart越过VL之前执行，保持寄存器、版本、CSR及vstart，不产生访存请求。EEW1掩码源可与执行mask同用v0，单目selector0和标量寄存器号0不当作v0数据读；unmasked v0仍合法。独立用例表与Python算术/滑移/归约golden同步修正，没有用旧正向测试替代合法性依据。

Monitor ABI1.0，ID0x2601/caps0x3fff；接口、RAM容量与ISA能力位不变。TileLink仍预留，物理normal-RAM访存尚无VM/PMP/缓存一致性。

## 验证

专项保留编码RTL {aliases['RamVectorFp-rtl']['reserved_cases']}个反例加{aliases['RamVectorFp-rtl']['coverage']['legal_zero_fields']}类合法零字段，当前映射网表同结果/周期；无FP及16位切分版也通过。滑移5576条中894条非法（新增134个masked源v0反例）；归约3418条中386条非法（176个seed v0反例），不再把这些保留编码计作合法运算。

四格式舍入相对固定HardFloat有界10步全raw位证明；新增IEEE解码相对固定HardFloat有界4步、任意recoded位及capture/hold证明；均为局部证明，不是完整FP流水或全ISA证明。并行增量/地址/配置、recode、divider和mask-prefix证明的源码SHA逐一核对。FP lane {units['fp-lane']['vectors']}组SoftFloat位/flags比较、{units['fp-lane']['flush_reset_cases']}次撤销/复位；smoke与映射增加舍入末段逐拍取消。转换5021组、492次撤销/复位重新通过。

完整gather3675、索引1674、前缀mask2888、mask/scalar10198、scan2894、INT乘除1673、旧向量789、FP向量2157、streaming251重新通过RTL。19条INT/FP/归约/排列交替序列与gather smoke在当前RTL/映射通过；monitor RTL/映射2600周期及tiny计数回绕通过。220组性能逐组核对数值，整数周期保持M25，vfadd增加恰好每有效元素2拍，未把增加流水级称作吞吐提升。

LSU完整279组（78种EEW/EMUL、77次边界停止）及119组smoke RTL/映射通过；新增24组四种EEW的masked v0 load/store非法边界和1组unmasked v0 store正例。公开SpinorVpu在monitor并发访问下279组RTL及119组RTL/映射通过；逐请求数据与周期按参考检查。旧M25完整映射证据不冒充当前网表。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射；RAM还会消耗器件LUT，表中数量不是BRAM。

## 云端验收

| 每段连线假设ps | M25公开ns | M26公开ns | M26计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段假设下，公开顶层{mid['budget_ns']:.3f}ns、算术余量{mid['budget_residual_ns']:.3f}ns，计算/访存{compute['budget_ns']:.3f}ns、余量{compute['budget_residual_ns']:.3f}ns，均在300MHz的3.333ns条件预算内。check_timing_gate.py对两个顶层强制检查，权重和RapidWright家族来源与冻结M25完全一致，不改连线假设换取通过。

这仅是条件参考门槛通过。没有布局布线、-2器件校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，没有器件STA/SDF或WNS；物理300/500MHz通过仍为null。200ps档结果见表，不能据100ps档声称实际300MHz已过，旧M5物理结果不能继承。

## 复现与后续

make bootstrap；python3 scripts/verify_m26.py；python3 scripts/package.py --milestone m26。receipt绑定源码、当前RTL/网表、测试台、局部证明、冻结基线、固定时序门槛与报告。后续继续compress、宽窄整数、FP归约及更多访存模式。未修改Valence，未调用Verilator。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m26/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M26',status='FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M25_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; PIPELINED_FP_ROUND_AND_IEEE_PACK; RESERVED_ENCODING_FIX; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
