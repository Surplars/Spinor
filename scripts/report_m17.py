#!/usr/bin/env python3
"""Bind M17 zero-extra-cycle arithmetic/FP changes to fresh cloud evidence."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m17';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
artifacts=set()
def include(p):
 p=ROOT/p;assert p.is_file(),p;artifacts.add(p)
def bound_result(name,rtl,tb):
 d=read('build/test/'+name)
 assert d['status']=='PASS',name
 assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl),name
 assert d['testbench_sha256']==sha(ROOT/tb),name
 include('build/test/'+name);include(rtl);include(tb)
 return d
old=read('archive/m16/reports/receipt.json')
fp=[]
for stem,rtl in [('fp-lane','build/rtl/FloatingPointLane.sv'),('fp-lane-smoke','build/rtl/FloatingPointLane.sv'),('fp-lane-mapped','build/synth/FloatingPointLane/mapped.v'),('fp-vector-m9-convert','build/rtl/RamVectorFp.sv')]:
 fp.append(bound_result(stem+'-results.json',rtl,'build/test/'+stem+'-tb.sv'))
 include('build/test/'+stem+'.log')
assert fp[0]['vectors']==6811 and fp[1]['vectors']==fp[2]['vectors']==385
assert fp[3]['commands']==2157 and fp[3]['write_stage_assertions_enabled']
assert fp[0]['observed_latency_cycles']==old['fp_tests'][0]['observed_latency_cycles']
assert fp[1]['observed_latency_cycles']==fp[2]['observed_latency_cycles']
memory=[]
for label,cases,stops,combinations in [('rtl',254,77,78),('smoke',94,9,6),('mapped',94,9,6)]:
 stem='vector-memory-'+label
 rtl='build/synth/LishiVpuMemory/mapped.v' if label=='mapped' else 'build/rtl/LishiVpuMemory.sv'
 d=bound_result(stem+'-results.json',rtl,'build/test/'+stem+'-tb.sv')
 assert (d['memory_cases'],d['stop_cases'],d['eew_emul_combinations'])==(cases,stops,combinations)
 include('build/test/'+stem+'.log');memory.append(d)
assert memory[1]['metrics']==memory[2]['metrics']
assert memory[0]['metrics']==old['memory_tests'][0]['metrics']
streaming=[]
for label in ['rtl','mapped']:
 rtl='build/synth/RamVectorFp/mapped.v' if label=='mapped' else 'build/rtl/RamVectorFp.sv'
 streaming.append(bound_result('streaming-'+label+'.json',rtl,'build/test/streaming-'+label+'-tb.sv'))
assert streaming[0]['commands']==251 and streaming[1]['commands']==73
integer=read('build/test/m7-div-fp-results.json');assert integer['commands']==1673
for label,path in [('RamVectorFp','build/rtl/RamVectorFp.sv'),('RamVectorFp-mapped','build/synth/RamVectorFp/mapped.v')]:
 assert integer['models'][label].startswith('PASS ram-vector commands=1673')
 assert integer['input_sha256'][label]['rtl']==sha(ROOT/path)
 assert integer['input_sha256'][label]['testbench']==sha(ROOT/'build/test/m7-div-fp-tb.sv')
 include('build/test/'+label+'.log')
include('build/test/m7-div-fp-results.json');include('build/test/m7-div-fp-tb.sv')
lane=read('build/test/lane-results.json')
for d in lane.values():assert d['corrupt_result_rejected'] and d['accepted']==d['retired']+d['flushed']
include('build/test/lane-results.json');include('build/test/lane.stim')
proofs={}
for label in ['classify-proof','divider-proof']:
 d=read('build/'+label+'/results.json');assert d['status']=='PASS'
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h;include(p)
 for p in (ROOT/'build'/label).iterdir():
  if p.is_file():artifacts.add(p)
 proofs[label]=d
perf=read('build/performance-m17-final/results.json')
assert perf['results']['M16']['rtl_sha256']==sha(ROOT/'archive/m16/rtl/RamVectorFp.sv')
assert perf['results']['M17']['rtl_sha256']==sha(ROOT/'build/rtl/RamVectorFp.sv')
assert perf['testbench_sha256']==sha(ROOT/'build/performance-m17-final/performance-tb.sv')
assert perf['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
a=perf['results']['M16']['cases'];b=perf['results']['M17']['cases']
assert len(a)==len(b)==220 and a==b
include('archive/m16/rtl/RamVectorFp.sv')
for p in (ROOT/'build/performance-m17-final').iterdir():
 if p.suffix in ['.json','.sv','.log']:artifacts.add(p)
budgets={}
for label in ['m16-baseline','m17']:
 d=read('build/timing-budget/'+label+'/budget.json')
 for p,h in d['input_sha256'].items():assert sha(ROOT/p)==h;include(p)
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None
 budgets[label]=d
 for name in ['budget.json','budget.md']:include('build/timing-budget/'+label+'/'+name)
for before,after in zip(budgets['m16-baseline']['scenarios'],budgets['m17']['scenarios'],strict=True):
 assert before['assumed_link_ps']==after['assumed_link_ps']
 assert after['worst']['budget_ns']<before['worst']['budget_ns']
summaries={};paths={}
for top in ['LishiVpuMemory','FloatingPointLane','RamVectorFp']:
 summaries[top]=read('build/synth/'+top+'/summary.json');paths[top]=read('build/synth/'+top+'/paths.json')
 for name in ['summary.json','paths.json','mapped.json','mapped.v','synth.ys','synth.log']:include('build/synth/'+top+'/'+name)
cells=summaries['LishiVpuMemory']['mapped_cells']
assert cells['DSP48E2']==9 and cells['RAM64M8']==32 and cells['RAM32M16']==6
lut=sum(v for k,v in cells.items() if k.startswith('LUT'));assert lut<14686
assert sum(v for k,v in cells.items() if k.startswith('FD'))==10143
unchanged={}
for top in ['IntegerMultiply','IntegerDivide','FloatingPointConvert','VectorMemoryEngine','TileLinkReservation']:
 p='build/rtl/'+top+'.sv';assert sha(ROOT/p)==old['artifact_sha256'][p];unchanged[top]=sha(ROOT/p)
include('archive/m16/reports/receipt.json')
for p in (ROOT/'build/rtl').iterdir():
 if p.suffix=='.sv':artifacts.add(p)
rows=[]
for before,after in zip(budgets['m16-baseline']['scenarios'],budgets['m17']['scenarios']):
 rows.append(f"| {after['assumed_link_ps']} | {before['worst']['budget_ns']:.3f} | {after['worst']['budget_ns']:.3f} |")
text='''# M17 云端优化评估

保留默认32位整数分段，无新增流水级；局部加法使用16位边界进位选择。浮点min/max复用已注册的特殊值判定，fclass直接判断IEEE编码，去除重复规格化。FP32/64分类已与HardFloat作全位模式SAT等价证明。没有新增指令，尚非完整RVV。

## 条件预算

| 假设每段连线ps | M16 ns | M17 ns |
|---:|---:|---:|
'''+ '\n'.join(rows)+f'''

全图 LUT 14686 → {lut}；FF 10143不变，DSP9不变，RAM64M8×32、RAM32M16×6不变，CARRY4 440 → {cells['CARRY4']}。RAM属于分布式RAM映射，不是新增BRAM。

这是Yosys映射网表和RapidWright家族表的未布局条件预算，不是器件STA、WNS或Fmax。排除346个DSP相关端点；未校准-2，没有布线、时钟树、hold、RAM写或I/O时序。不能由这些数字宣称300MHz或500MHz通过。当前最坏预算链转移到FP64舍入掩码到roundedSig。

## 功能和周期

6811组浮点数值/标志、2157条向量浮点指令、1673条整数/乘除向量指令、251条流式指令、254组访存检查通过。网表复测385组FP、1673条整数向量、73条流式指令、94组访存。整数通道随机反压/flush/结果破坏负对照通过。220组结果校验性能用例的逐用例周期与M16完全相同；访存性能指标和FP指令延迟也不变。完整散列与覆盖见receipt.json。

16位候选虽通过功能检查，但整数收尾每指令多1周期，三档预算3.300/4.050/5.550ns，未采用为默认。探索测量保存在rejected16；该目录属于先前候选测量，不对应当前重新生成的16位RTL。当前交付结论仅针对默认32位顶层。

物理时序基线仍只有历史M5；当前无需重复本地Vivado。后续先检查FP64舍入的控制扇出和组合深度，再决定本地实现验证。LSU/TL接口和延迟停止合同不变；仍缺CPU集成、VM/PMP/一致性和完整RVV。
'''
(OUT/'evaluation.md').write_text(text)
for p in OUT.rglob('*'):
 if p.is_file() and p.name!='receipt.json':artifacts.add(p)
source=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','mill','Makefile','tools.lock.json','README.md']]
source += [p for folder in ['src','scripts','tests','docs','third_party'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
receipt=dict(project='Lishi VPU',name_zh='砺矢',milestone='M17',status='CLOUD_ZERO_EXTRA_CYCLE_ARITHMETIC_AND_FP_SCREEN_PASS',
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(artifacts)},
 fp_tests=fp,memory_tests=memory,streaming_tests=streaming,integer_vector=integer,lane_tests=lane,proofs=proofs,performance=perf,
 resources=summaries,paths=paths,conditional_timing_budgets=budgets,unchanged_M16_RTL=unchanged,
 Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,physical_baseline='M5 only',
 scope='DEFAULT_32_BIT_TOPS_ONLY; NOT_FULL_RVV; NO_VALENCE_INTEGRATION; PHYSICAL_NORMAL_RAM_ONLY; MEMORY_FLUSH_DEFERRED')
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(receipt['status'], 'LUT',lut,'FF',10143)
