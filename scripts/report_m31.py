#!/usr/bin/env python3
"""Bind integer extensions, current Windows handoff and fixed cloud timing evidence."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m31';OUT.mkdir(parents=True,exist_ok=True)
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
base=read('archive/m30/reports/receipt.json')
assert sha(ROOT/'tools.lock.json')==base['source_sha256']['tools.lock.json']
for name in ['receipt.json','evaluation.md']:include('archive/m30/reports/'+name)
for name in ['RamVectorFp','SpinorVpu','FloatingPointLane']:
 f=f'archive/m30/rtl/{name}.sv';assert sha(ROOT/f)==base['artifact_sha256'][f'build/rtl/{name}.sv'];include(f)
for name in ['RamVector.scala','StagedRound.scala','FloatingPointLane.scala','VectorMemoryEngine.scala','VectorConfig.scala','GenerateIncrementProof.scala']:
 f='archive/m30/source/'+name;assert sha(ROOT/f)==base['source_sha256']['src/main/scala/vpu/'+name];include(f)
restored=checked('build/baseline-m30/results.json');include(restored['output'])
assert sha(ROOT/restored['output'])==restored['restored_sha256']==base['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor=checked('build/baseline-m25/results.json');include(anchor['output'])
anchor_frozen=read('archive/m25/reports/receipt.json')
assert sha(ROOT/anchor['output'])==anchor['restored_sha256']==anchor_frozen['artifact_sha256']['build/synth/SpinorVpu/mapped.json']
anchor_budget=read('build/timing-budget/m25-baseline/budget.json')
for p,h in anchor_budget['input_sha256'].items():assert sha(ROOT/p)==h,p;include(p)
include('build/timing-budget/m25-baseline/budget.md')
gate=checked('build/timing-budget/m31-gate/results.json')
budget_model=checked('build/test/cloud-budget-results.json')
assert gate['scope']=='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA' and gate['assumed_link_ps']==100
assert set(gate['results'])=={'SpinorVpu','LishiVpuMemory'}
budgets={}
for label in ['m30-baseline','m31-spinor','m31-compute']:
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
 stem='build/reduction-interleave/'+label;d=checked(stem+'-results.json');logs(stem);mixed.append(d);assert d['vector_instructions']==46
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
perf=read('build/performance-m31/results.json');include('build/performance-m31/results.json')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m31/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert perf['results']['M30']['rtl_sha256']==sha(ROOT/'archive/m30/rtl/RamVectorFp.sv')
assert perf['results']['M31']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert len(perf['results']['M31']['cases'])==220
for old,new in zip(perf['results']['M30']['cases'],perf['results']['M31']['cases'],strict=True):
 delta=0
 assert new['cycles']==old['cycles']+delta,(new['id'],delta)
for p in (ROOT/'build/performance-m31').iterdir():
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
  table.append(f"| {'M30' if old else 'M31'} {top} | {lut(c)} | {ff(c)} | 9 | 32 | 6 |")
timing=[]
for a,b,c in zip(budgets['m30-baseline']['scenarios'],budgets['m31-spinor']['scenarios'],budgets['m31-compute']['scenarios'],strict=True):
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
windows=checked('build/windows-m31-validation/results.json')
assert windows['scope']=='EXACT_PACKAGED_TB_ICARUS_REPLAY_AND_MOCK_ORCHESTRATION; NO_WINDOWS_XSIM_VIVADO_PNR_SDF_EXECUTION'
assert windows['bundle_sha256']==sha(ROOT/'spinor-windows-m31.zip');include('spinor-windows-m31.zip')
assert len(windows['tcl_mock_cases'])==9 and len(windows['powershell_mock_cases'])==2 and windows['tampered_input_rejected']
for top,name in [('RamVectorFp','extensions'),('SpinorVpu','integration')]:
 assert windows['replays'][name]['RTL_sha256']==sha(ROOT/f'build/rtl/{top}.sv')
evaluation=f"""# M31：整数扩展与当前Windows验证包

新增vzext.vf2/vf4/vf8、vsext.vf2/vf4/vf8，源EEW=SEW/2、/4、/8，目的仍为SEW/LMUL。支持e16/e32/e64的15种合法类型组合；源至少8位、EMUL至少1/8。仍为VLEN128/ELEN64、单指令容量的部分RVV，未接实际Orbital/Linux，不可声明完整V/RVA23或misa.V。

## RAM与流水线

源EEW与目的SEW独立寻址；复用现有RAM、64位暂存、整数move与基本整数元素重叠流水。验证前寄存源几何小表，数据阶段使用2位源SEW，扩展无新增状态或DSP/整组FF快照。源组按自身EMUL对齐；有重叠时要求源EMUL≥1且占据目的组最高部分，fractional源与目的共享物理寄存器则保留非法。用异或与alignment判断最高部分，SAT覆盖所有对齐基址/组大小，与完整端地址判定等价。

支持mask、tail undisturbed、合法vstart恢复、VL0/no-op start及flush。源/目的与执行mask不同EEW的别名、坏selector/位宽/对齐/重叠在VL0也验证。完成握手才切换目的版本，flush丢弃候选结果；不改变fflags/vxsat。Monitor ABI1.0，ID0x3101/caps0x7ffff，新增bit18整数扩展。

## 验证

整数扩展4212条完整RTL命令，1975条非法、198个取消场景，逐条比较32个寄存器、配置与版本；884条smoke当前RTL/映射结果和周期一致。无FP及16位切分版各882条smoke通过。46条混合向量程序交替扩展、INT/FP、归约、gather/compress，通过RTL/映射。新重叠判定的SAT与原增量/地址/配置证明通过。

旧FP宽化归约1664/266、单宽FP归约5771/588、宽化INT归约1025/163、compress1229/189、gather3675/404的完整RTL与smoke映射继续通过。源别名、slide/index/prefix/mask/INT归约、乘除与FP向量、streaming完整RTL回归通过；220组旧性能周期保持M30。9个FP/整数/RF/LSU/host单元RTL按SHA保持M30；独立数值单元与未改动证明复用绑定原输入的已通过证据，冷启动verify命令会重跑这些证据。

公开SpinorVpu并发monitor下279组完整RTL及119组RTL/映射访存通过，末尾执行新扩展、flush/非法重叠和返回普通运算。独立LSU279/119 RTL及119映射通过，monitor2600周期RTL/映射、tiny与软件fixture通过。当前不是Linux驱动上板结果。

## Windows本地验证

spinor-windows-m31.zip内含当前SpinorVpu和RamVectorFp、生成的两个自检TB、PowerShell/Tcl和散列。默认All先XSim功能自检，再按3.333333ns对SpinorVpu全新综合、布局、phys_opt与布线，导出setup/hold、资源、DCP/EDIF和对应DSP延迟。失败也自动流式打包嵌套日志/波形和已生成报告；无旧DCP恢复入口。

两个打包后的原样TB已在云端Icarus重放。Tcl以mock验证9种正常/仿真失败/缺失PASS/缺失时钟/空DSP数据路径；Linux PowerShell7.5.4实际解析并以假launcher执行成功、非零退出和篡改输入检测，包含路径空格、参数、散列和嵌套ZIP检查。这些只验证编排，未执行Windows5.1、XSim、Vivado、P&R或真正DSP导出。功能TB是约10ns抽象tick加稳定等待；实现频率参数不会把RTL仿真变成时序证明。本包没有post-route SDF仿真或可上板bit。具体本地命令见docs/m31-integer-extensions.md。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Yosys xcup未布局映射，RAM另占器件LUT，不是BRAM块数。

## 固定云端门槛

| 每段连线假设ps | M30公开ns | M31公开ns | M31计算/访存ns |
|---:|---:|---:|---:|
{chr(10).join(timing)}

固定100ps/段下公开{mid['budget_ns']:.3f}ns、计算/访存{compute['budget_ns']:.3f}ns，余量{mid['budget_residual_ns']:.3f}/{compute['budget_residual_ns']:.3f}ns，均≤3.333ns。仍使用冻结M25家族权重与锚点，按SHA恢复M30图比较，未放宽假设。只有条件参考：无布局布线或ZU15EG-2校准，DSP相关端点排除，无hold/时钟树/RAM写/IO/SDF验证；物理300/500MHz仍为null，不继承M5。本地需检查完整约束覆盖、setup/hold与route状态。

## 复现

make bootstrap；python3 scripts/verify_m31.py；python3 scripts/package.py --milestone m31。Windows编排检查额外下载散列固定的Linux PowerShell用于测试脚本，不作为HDL工具。receipt绑定源码、RTL/网表、测试台、证明、两份交付与冻结基线；未修改Valence或使用Verilator。后续继续宽窄整数算术、FP转换、更多访存及Orbital程序闭环。
"""
(OUT/'evaluation.md').write_text(evaluation);include('reports/m31/evaluation.md')
for folder in ['build/rtl','build/monitor/rtl']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','software','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Spinor VPU',milestone='M31',status='INTEGER_EXTENSIONS_AND_WINDOWS_HANDOFF_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 integer_extensions=extensions,windows_handoff=windows,fp_widening_reductions=fp_widening_reductions,fp_widen_lane=fp_widen_lane,widening_reductions=widening_reductions,fp_reductions=fp_reductions,families=families,mask_source_alias=aliases,mask=mask,reductions=red,integer=integer,fp_vector=fp,streaming=stream,mixed_program=mixed,
 memory=memory,spinor_integration=soc,monitor=monitors,monitor_client=client,proofs=proofs,numerical_units=units,unchanged_M30_RTL=unchanged,
 performance=perf,resources=resources,paths=paths,budget_model=budget_model,conditional_budgets=budgets,conditional_reference_gate=gate,restored_baseline=restored,fixed_M25_anchor=anchor,
 actual_Orbital_integrated=False,actual_Linux_UIO_tested=False,Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,
 scope='PARTIAL_RVV; ONE_INSTRUCTION; INTEGER_EXTENSIONS; WINDOWS_HANDOFF; CONDITIONAL_GATE_NOT_DEVICE_STA')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status']);print('Spinor LUT',lut(resources['SpinorVpu']['mapped_cells']),'FF',ff(resources['SpinorVpu']['mapped_cells']))
