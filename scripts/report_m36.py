#!/usr/bin/env python3
"""Bind M36 integer expansion, regression and fixed timing evidence."""
import hashlib,json,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m36';OUT.mkdir(parents=True,exist_ok=True)
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
def same_performance(current,old,delta):
 assert len(current)==len(old)
 for x,y in zip(current,old,strict=True):
  assert x.keys()==y.keys()
  for k in x:assert x[k]==y[k]+delta if k=='cycles' else x[k]==y[k],(k,x,y)

def compare_memory(current,old):
 for key in ['case_specs','metrics']:
  assert current[key][:len(old[key])]==old[key],key
 assert current['benchmark_cases']==old['benchmark_cases']
 assert all(current['context_reads'][k]==v for k,v in old['context_reads'].items())
 assert current['stop_cases']==old['stop_cases']
 return []

base=read('archive/m35/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m35/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane']:
 f=f'archive/m35/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m35/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m35/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m36-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m35-baseline','m36-spinor','m36-compute']:
 budgets[label]=read('build/timing-budget/'+label+'/budget.json')
 for suffix in ['json','md']:include(f'build/timing-budget/{label}/budget.{suffix}')
 for p,h in budgets[label]['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)

def family(folder,mapped=False,all_coverage=True):
 labels=['RamVectorFp-full-rtl','RamVectorFp-smoke-rtl','RamVector-smoke-rtl','RamVector16-smoke-rtl']
 if mapped:labels+=['RamVectorFp-smoke-mapped']
 data={}
 for label in labels:
  stem=f'build/{folder}/{label}';d=checked(stem+'-results.json');logs(stem);data[label]=d
  if all_coverage:assert all(d['coverage'].values()),(folder,label)
 if mapped:
  for key in ['commands','coverage','types','performance','summary']:
   assert data['RamVectorFp-smoke-rtl'][key]==data['RamVectorFp-smoke-mapped'][key],(folder,key)
 return data
families={folder:family(folder) for folder in ['compress','gather','slide','index-generate','mask-prefix']}
assert all(len(d['RamVectorFp-full-rtl']['types'])==22 for d in families.values())
assert families['slide']['RamVectorFp-full-rtl']['coverage']['masked_source_v0']==134
prefix=families['mask-prefix']['RamVectorFp-full-rtl'];assert prefix['commands']==2888
assert all(x['cycles']==106 for x in prefix['performance'] if x['vl']==128)
aliases={}
for label in ['RamVectorFp-rtl','RamVector-rtl','RamVector16-rtl']:
 stem='build/mask-source-alias/'+label;aliases[label]=checked(stem+'-results.json');logs(stem)
 assert aliases[label]['coverage']['legal_zero_fields']>0
fp_widening_reductions=family('fp-widening-reductions',all_coverage=False)
fp_reductions=family('fp-reductions',all_coverage=False)
for data in [fp_widening_reductions,fp_reductions]:
 for d in data.values():assert d['reference_anchors']==52 and d['coverage']['flushes']>0
 for label in ['RamVector-smoke-rtl','RamVector16-smoke-rtl']:assert data[label]['coverage']['reductions']==0
fpwide=fp_widening_reductions['RamVectorFp-full-rtl']
assert len(fpwide['by_type'])==5 and all(fpwide['coverage'].values()) and fpwide['commands']==1664
assert fpwide['coverage']['reductions']==442 and fpwide['coverage']['illegal']==194
full=fp_reductions['RamVectorFp-full-rtl']
assert full['commands']==5771 and len(full['by_type'])==9 and all(full['by_operation'].values()) and all(full['coverage'].values())
for row in full['performance']:
 if row['sew']==32 and row['vlmul']==3 and row['frm']==0:assert row['cycles']==(1230 if row['op'] in [1,3] else 302)
widening_reductions=family('widening-reductions')
wide=widening_reductions['RamVectorFp-full-rtl'];assert len(wide['by_type'])==18 and wide['commands']==1025
assert wide['coverage']['reductions']==260 and wide['coverage']['illegal']==325 and wide['coverage']['flushes']==60
fp_widen_lane={}
for label in ['rtl','smoke','mapped']:
 stem='build/fp-widen-lane/'+label;d=checked(stem+'-results.json');logs(stem);fp_widen_lane[label]=d
 assert d['extra_reference_anchors']==7 and d['base_reference_anchors']==52
assert fp_widen_lane['rtl']['vectors']==1292
for key in ['vectors','flush_reset_cases','latency','summary']:assert fp_widen_lane['smoke'][key]==fp_widen_lane['mapped'][key],key
extensions=family('integer-extensions');narrowing=family('narrowing-shifts');widening=family('widening-arithmetic')
assert extensions['RamVectorFp-full-rtl']['commands']==4212 and len(extensions['RamVectorFp-full-rtl']['types'])==15
full_narrow=narrowing['RamVectorFp-full-rtl'];assert full_narrow['commands']==4945 and len(full_narrow['types'])==15
assert full_narrow['coverage']['illegal']==1753 and full_narrow['coverage']['flush']==198
widen_full=widening['RamVectorFp-full-rtl'];assert widen_full['commands']==11926 and len(widen_full['types'])==15
assert widen_full['coverage']['illegal']==4825 and widen_full['coverage']['flush']==608
mac=family('integer-mac')
mac_netlist={}
for label in ['rtl','mapped']:
 stem='build/integer-mac-netlist/'+label;mac_netlist[label]=checked(stem+'-results.json');logs(stem)
 assert mac_netlist[label]['mac_instructions']==40 and mac_netlist[label]['flushes']==8
for key in ['commands','mac_instructions','flushes','coverage','summary']:assert mac_netlist['rtl'][key]==mac_netlist['mapped'][key]
mac_full=mac['RamVectorFp-full-rtl']
assert len(mac_full['types'])==22 and mac_full['commands']==6778
assert mac_full['coverage']['illegal']==1370 and mac_full['coverage']['flush']==512
assert {r['code'] for r in mac_full['performance']}=={0x29,0x2b,0x2d,0x2f}
assert {r['form'] for r in mac_full['performance']}=={2,6}
multiply=family('widening-multiply')
multiply_full=multiply['RamVectorFp-full-rtl']
assert multiply_full['commands']==4467 and len(multiply_full['types'])==15
assert multiply_full['coverage']['illegal']==1857 and multiply_full['coverage']['flush']==246
assert {r['code'] for r in multiply_full['performance']}=={0x38,0x3a,0x3b}
assert {r['form'] for r in multiply_full['performance']}=={2,6}
for folder,data in families.items():
 for label,d in data.items():
  old=base['families'][folder][label]
  for key in ['commands','coverage','types']:assert d[key]==old[key],(folder,label,key)
  same_performance(d['performance'],old['performance'],0)
for name,data in [('integer_mac',mac),('widening_multiply',multiply),('integer_extensions',extensions),('narrowing_shifts',narrowing),('widening_arithmetic',widening),('fp_widening_reductions',fp_widening_reductions),('fp_reductions',fp_reductions),('widening_reductions',widening_reductions)]:
 for label,d in data.items():
  old=base[name][label]
  for key in ['commands','coverage']:assert d[key]==old[key],(name,label,key)
  same_performance(d['performance'],old['performance'],0)
mask={}
for folder in ['mask-scalar','mask-scan']:
 stem=f'build/{folder}/RamVectorFp-full-rtl';d=checked(stem+'-results.json');logs(stem);mask[folder]=d
 for k in ['commands','coverage','types']:assert d[k]==base['mask'][folder][k],(folder,k)
 same_performance(d['performance'],base['mask'][folder]['performance'],0)
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==89
memory=[]
for label,count in [('rtl',303),('smoke',143),('mapped',143)]:
 stem='build/test/vector-memory-'+label;rtl='build/synth/LishiVpuMemory/mapped.v' if label=='mapped' else 'build/rtl/LishiVpuMemory.sv'
 d=sim(stem,rtl);assert d['memory_cases']==count;memory.append(d)
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert memory[1]['metrics']==memory[2]['metrics']
memory_phase_changes=[compare_memory(current,old) for current,old in zip(memory,base['memory'],strict=True)]
soc=[]
for label,count in [('rtl',303),('smoke',143),('mapped',143)]:
 stem='build/monitor/integration-spinor/vector-memory-'+label
 d=sim(stem,'build/synth/SpinorVpu/mapped.v' if label=='mapped' else 'build/rtl/SpinorVpu.sv');soc.append(d)
 assert d['memory_cases']==count and d['stop_cases']==(77 if label=='rtl' else 9)
 assert 'PASS monitored-mmio' in (ROOT/(stem+'.log')).read_text()
 if label!='mapped':
  assert d['assertions_enabled']
  for mod in ['VectorMemoryEngine','RamVectorFpMemory']:include(stem+'-'+mod+'-assert.sv')
assert soc[1]['metrics']==soc[2]['metrics']
public_phase_changes=[compare_memory(current,old) for current,old in zip(soc,base['spinor_integration'],strict=True)]
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
for top in ['IntegerLaneSplit','IntegerMultiply','IntegerDivide','TileLinkReservation','VersionedRegisterFileRam','VpuHostBoundary']:
 rel=f'build/rtl/{top}.sv';assert sha(ROOT/rel)==base['artifact_sha256'][rel],top;include(rel);unchanged[top]=sha(ROOT/rel)
perf=read('build/performance-m36/results.json');include('build/performance-m36/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m36/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M35']['rtl_sha256']==sha(ROOT/'archive/m35/rtl/RamVectorFp.sv')
assert perf['results']['M36']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M36']['cases'])==220
for old,new in zip(perf['results']['M35']['cases'],perf['results']['M36']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m36').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
resources={};paths={}
for top in ['RamVectorFp','SpinorVpu','LishiVpuMemory','FloatingPointLane','VpuMonitor','IntegerDivide']:
 resources[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 graph=read('build/synth/'+top+'/mapped.json')['modules'][top]
 assert dict(Counter(c['type'] for c in graph['cells'].values()))==resources[top]['mapped_cells'],top
 assert set(resources[top]['input_sha256'])=={f'build/rtl/{top}.sv','scripts/synth.py'},top
 assert set(resources[top]['netlist_sha256'])=={f'build/synth/{top}/mapped.json',f'build/synth/{top}/mapped.v'},top
 assert set(paths[top]['input_sha256'])=={f'build/synth/{top}/mapped.json','scripts/path_depth.py'},top
 for key in ['input_sha256','netlist_sha256']:
  for f,h in resources[top].get(key,{}).items():assert sha(ROOT/f)==h,(top,f);include(f)
 for f,h in paths[top]['input_sha256'].items():assert sha(ROOT/f)==h,(top,f);include(f)
 for n in ['summary.json','paths.json','mapped.v','mapped.json','synth.ys','synth.log']:include('build/synth/'+top+'/'+n)
def lut(c):return sum(v for k,v in c.items() if k.startswith('LUT'))
def ff(c):return sum(v for k,v in c.items() if k.startswith('FD'))
# New full and bounded mapped suites.
wmac=family('widening-mac')
new={}
for label in ['RamVectorFp-full-rtl','RamVectorFp-compact-rtl','RamVector-compact-rtl','RamVector16-compact-rtl','RamVectorFp-compact-mapped']:
 stem='build/m36-integer/'+label;new[label]=checked(stem+'-results.json');logs(stem)
 assert len(new[label]['encodings'])==17
assert len(new['RamVectorFp-full-rtl']['types'])==22
assert len(wmac['RamVectorFp-full-rtl']['types'])==15
for key in ['commands','coverage','types','encodings','performance','summary']:
 assert new['RamVectorFp-compact-rtl'][key]==new['RamVectorFp-compact-mapped'][key],key
for label in ['rtl','mapped']:
 rows=read('build/m36-regression/'+label+'.json');include('build/m36-regression/'+label+'.json')
 for records in rows.values():
  for row in records:assert row['exit_code']==0,row;include(row['log'])
wmfull=wmac['RamVectorFp-full-rtl'];newfull=new['RamVectorFp-full-rtl']
assert {r['code'] for r in wmfull['performance']}>={0x3c,0x3d,0x3e,0x3f}
assert wmfull['commands']==5961 and wmfull['coverage']['illegal']==2744 and wmfull['coverage']['flush']==287
assert newfull['commands']==3732 and newfull['coverage']['flush']==60
assert all(r['coverage']['flush']>0 for r in wmac.values())
resources_table=[]
for top in ['SpinorVpu','LishiVpuMemory','RamVectorFp']:
 old=base['resources'][top]['mapped_cells'];c=resources[top]['mapped_cells']
 assert all(c[k]==old[k] for k in ['DSP48E2','RAM64M8','RAM32M16'])
 resources_table.append(f"| {top} | {lut(c)} ({lut(c)-lut(old):+d}) | {ff(c)} ({ff(c)-ff(old):+d}) | {c['DSP48E2']} | {c['RAM64M8']} / {c['RAM32M16']} |")
timing=[]
for a,b,c in zip(budgets['m35-baseline']['scenarios'],budgets['m36-spinor']['scenarios'],budgets['m36-compute']['scenarios'],strict=True):
 assert a['assumed_link_ps']==b['assumed_link_ps']==c['assumed_link_ps']
 timing.append(f"| {b['assumed_link_ps']} | {a['worst']['budget_ns']:.3f} | {b['worst']['budget_ns']:.3f} | {c['worst']['budget_ns']:.3f} |")
mid=gate['results']['SpinorVpu'];compute=gate['results']['LishiVpuMemory']
# Capture complete-vector no-stall performance, excluding alias/restart cases.
wmac_performance=[]
for t in [0,8,16,2,10,18]:
 values={form:next(r for r in wmfull['performance'] if r['vtype']==t and r['code']==0x3c and r['form']==form and r['vm']==1) for form in [2,6]}
 row=dict(sew=8<<(t>>3),lmul='m'+str(1<<(t&7)),vl=values[2]['vl'],vector_cycles=values[2]['cycles'],scalar_cycles=values[6]['cycles'])
 wmac_performance.append(row)
performance_table=[f"| {r['sew']} | {r['lmul']} | {r['vl']} | {r['vector_cycles']} | {r['scalar_cycles']} |" for r in wmac_performance]
whole_rows=[r for r in newfull['performance'] if r['kind']=='whole' and r['vstart']==0 and r['sew']==8 and r['vl']==0]
performance_text="""# M36 性能参考

周期为RTL仿真，包含提交，不含配置、访存和软件。仍复用串行16×16乘法器和流水ALU，无每拍一元素保证。300MHz只是目标换算，实际器件频率未验证。

| 源SEW | LMUL | 元素数 | 宽化乘加vv周期 | vx周期 |
|---|---|---:|---:|---:|
"""+'\n'.join(performance_table)+"""

旧220组性能与冻结M35逐项一致；旧单宽乘加、宽化乘法、扩展/移位/归约/排列的回归性能记录也保持原周期。独立LSU与公共顶层访存请求数、RF读取次数及所有原有访存测试周期相同。

整组搬运每寄存器先读写目的候选副本，再读写源数据，共4拍/寄存器，加解码、wholeCheck和提交开销；这保留非零vstart之前的数据，不增加整组FF快照。完整机器周期见receipt的m36_integer.performance；该表同时含自搬运NOP、非法及重启记录，不应混作吞吐基准。
"""
(OUT/'performance.md').write_text(performance_text);include('reports/m36/performance.md')
local_base=read('archive/m31/local-report/receipt.json')
for name in ['receipt.json','evaluation.md']:include('archive/m31/local-report/'+name)
evaluation=(ROOT/'docs/m36-integer-completion.md').read_text().replace('(rvv-completion-plan.md)','(../../docs/rvv-completion-plan.md)').replace('(references/m36-integer-v1.0.txt)','(../../docs/references/m36-integer-v1.0.txt)').replace('(../reports/m36/evaluation.md)','(evaluation.md)')+f"""

## 验证结果

宽化乘加完整RTL {wmfull['commands']}条命令、15种合法SEW/LMUL，非法{wmfull['coverage']['illegal']}、取消{wmfull['coverage']['flush']}；主配置/无FP/16位切分smoke均通过。新增整数集完整RTL {newfull['commands']}条命令，覆盖22种普通整数类型、全部17种新增编码及{newfull['coverage']['flush']}次取消。精简新增集RTL/当前网表各{new['RamVectorFp-compact-rtl']['commands']}条命令，数值/架构状态/周期一致。

M35旧整数乘加6778条、宽化乘法4467条、宽化加减11926条、扩展4212条、窄化4945条及其余已实现向量族完整RTL回归通过。当前网表另通过旧乘加40条运算、89条混合序列、独立LSU143组、公共顶层143组及monitor；公共顶层完整RTL303组通过，并实际执行M36宽化乘加、整组搬运、反减和比较。当前网表未重跑全部ISA矩阵。

{len(unchanged)}个数值/存储/宿主边界单元生成RTL与M35逐字节相同，保留输入SHA绑定的未改单元/局部证明；FP32/64数值单元与转换因增量分块重新验证，增量/地址证明重新执行。220组原有性能与M35一致，原有访存用例周期和请求数相同；新增24组高地址分块进位故障用例。不是RVV合规声明。详见[性能参考](performance.md)。

## Yosys xcup资源（括号为相对M35变化）

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 / RAM32M16 |
|---|---:|---:|---:|---:|
{chr(10).join(resources_table)}

未布局资源估计，LUTRAM另占LUT，不等于Vivado BRAM数量。

## 固定云端条件预算

| 连线假设ps/段 | M35公共ns | M36公共ns | M36计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段：公共{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns；余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，门槛3.333ns。权重和固定M25基线未放宽。

这是未布局、未按-2速度档校准的条件参考，排除DSP污染端点，不含布线、hold、时钟树、RAM写时序和外部IO。M36未运行Vivado或SDF，实际300/500MHz未知；M31本地OOC结果仅作为历史基线。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m36/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M36',status='INTEGER_EXPANSION_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 widening_mac=wmac,widening_mac_performance=wmac_performance,m36_integer=new,integer_mac=mac,integer_mac_netlist=mac_netlist,
 widening_arithmetic=widening,widening_multiply=multiply,narrowing_shifts=narrowing,integer_extensions=extensions,local_M31_baseline=local_base,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M35_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 current_top_mapped_scope=['new-17-encoding-compact','integer-mac-compact-40','mixed-89','public-memory-and-new-integer','LSU','monitor'],scope='PARTIAL_RVV; ONE_INSTRUCTION; INTEGER_EXPANSION; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
