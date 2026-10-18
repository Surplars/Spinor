#!/usr/bin/env python3
"""Validate current M50 evidence; historical receipts supply path manifests only."""
import hashlib
import json
import csv
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m50';OUT.mkdir(parents=True,exist_ok=True)
artifacts=set();external={};hashes={}
def sha(rel):
    rel=str(rel)
    if rel not in hashes:hashes[rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
    return hashes[rel]
def read(rel):return json.loads((ROOT/rel).read_text())
def include(rel):
    rel=str(rel);assert (ROOT/rel).is_file(),rel
    if Path(rel).parts[0]=='tools':external[rel]=sha(rel)
    else:artifacts.add(rel)
def bind(rel,h):assert sha(rel)==h,rel;include(rel)
def checked(rel):
    d=read(rel);assert d.get('status','PASS')=='PASS',rel;include(rel)
    for key in ['sha256','input_sha256','source_sha256','artifact_sha256','netlist_sha256']:
        for f,h in d.get(key,{}).items():
            if isinstance(h,str):bind(f,h)
            else:
                assert rel in ['build/test/m7-div-fp-results.json','build/test/ram-vector-results.json'],(rel,key)
                bind(f'build/rtl/{f}.sv',h['rtl'])
                bind('build/test/'+('m7-div-fp-tb.sv' if 'm7-' in rel else 'ram_vector_tb.sv'),h['testbench'])
    stem=rel.removesuffix('-results.json').removesuffix('.json')
    for suffix in ['.log','-compile.log','.compile.log','-tb.sv','-assert.sv']:
        if (ROOT/(stem+suffix)).is_file():include(stem+suffix)
    if Path(rel).name=='results.json':
        for name in ['compile.log','run.log','generate.log','proof.log']:
            p=Path(rel).parent/name
            if (ROOT/p).is_file():include(p)
    return d

# Core RTL changed. Require complete current matrices with no arithmetic reuse.
counts={}
for label,total in [('rtl',167),('mapped',57)]:
    rel=f'build/m50-regression/{label}.json';rows=read(rel);include(rel)
    flat=[r for group in rows.values() for r in group]
    assert len(flat)==total and all(r['exit_code']==0 and 'reused_from' not in r for r in flat),(label,len(flat))
    for row in flat:include(row['log']);include('tests/'+row['args'][0])
    counts[label]=dict(total=total,executed=total,reused=0)
reuse=checked('build/m50-regression/reuse-inputs.json');assert not reuse['cache_available']

# Frozen M48 is a manifest of required test outputs, never authorization to
# reuse changed inputs. Each output below is revalidated against CURRENT files.
prior=read('archive/m48/reports/receipt.json');include('archive/m48/reports/receipt.json')
excluded=('build/performance-','build/m48-regeneration/','build/evidence-reuse-m48-test/','build/timing-budget/')
legacy={}
special={'build/test/streaming-rtl.json','build/test/integer-divide-rtl.json','build/test/integer-divide-mapped.json'}
for rel in prior['artifact_sha256']:
    if rel.startswith('build/') and not rel.startswith(excluded) and (rel.endswith('results.json') or rel in special):
        legacy[rel]=checked(rel)
        # Early tests predate path-addressed SHA maps: bind their scalar hashes.
        d=legacy[rel]
        if 'models' in d:assert d['models'] and all(v.startswith('PASS ram-vector') for v in d['models'].values())
        if 'rtl_or_netlist_sha256' in d:
            if '/vector-memory-' in rel:top='SpinorVpu' if '/integration-spinor/' in rel else 'LishiVpuMemory'
            elif any('/'+family+'/' in rel for family in ['strided-memory','indexed-memory','context-memory','segment-memory','addressed-segment-memory','fof-memory']):
                top='LishiVpuMemory16' if 'memory16-' in Path(rel).name else 'LishiVpuMemory'
            elif '/fp-vector-' in rel or '/streaming-' in rel:top='RamVectorFp'
            elif '/fp-convert-' in rel:top='FloatingPointConvert'
            elif '/integer-divide-' in rel:top='IntegerDivide'
            elif '/fp-resize-native-' in rel:top='FloatingPointLaneResize'
            elif '/fp-native-' in rel:top='FloatingPointLaneWiden'
            else:assert '/fp-lane' in rel,rel;top='FloatingPointLane'
            rtl=f'build/synth/{top}/mapped.v' if 'mapped' in Path(rel).name else f'build/rtl/{top}.sv'
            bind(rtl,d['rtl_or_netlist_sha256'])
            stem=rel.removesuffix('-results.json').removesuffix('.json')
            tb='build/test/integer-divide-tb.sv' if top=='IntegerDivide' else stem+'-tb.sv'
            bind(tb,d['testbench_sha256'])
# Compare like-for-like compact/functional outputs, excluding assertion-only
# hierarchical instrumentation and simulator time-unit formatting.
paired_legacy=0
for rel,mapped in legacy.items():
    if 'mapped' not in Path(rel).name:continue
    if 'memory_cases' in mapped:
        mate=rel.replace('-mapped','-smoke')
    elif '/fp-widen-lane/mapped-' in rel:
        mate=rel.replace('/mapped-','/smoke-')
    elif any('/test/'+name+'-mapped-' in rel for name in ['fp-lane','fp-native','fp-resize-native']):
        mate=rel.replace('-mapped-','-smoke-')
    else:mate=rel.replace('-mapped','-rtl').replace('/mapped-','/rtl-')
    assert mate in legacy,(rel,mate)
    native=legacy[mate]
    for key in ['commands','cases','memory_cases','stop_cases','checks','flushes','vectors','types','coverage','encodings','performance','metrics','case_specs','stop_specs','benchmark_cases','observed_latency_cycles','latency','reads','writes','denied','held_cycles','snapshots','clears']:
        if key in native and key in mapped:assert native[key]==mapped[key],(rel,mate,key)
    paired_legacy+=1
regeneration=checked('build/m50-regeneration/results.json');assert regeneration['files']==223
for name in ['default','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:include(f'build/m50-regeneration/{name}.log')

model=checked('build/spike-model/results.json')
assert not model['semantics_modified'] and model['revision']=='5a760667bf0d0ab893173b9eeff9c109c8d7dd9a'
assert (model['vlen'],model['elen'],model['vstart_alu'])==(128,64,False)
for key in ['model_source_sha256','model_libraries_sha256']:
    for p,h in model[key].items():bind(p,h)
bind(model['binary'],model['binary_sha256'])
include('build/spike-model/make.log');include('build/spike-model/link.log')
catalog=read('build/spike-model/catalog.json')
assert [len(catalog[k]) for k in ['v_alu_int','v_alu_fp','v_ctrl']]==[213,101,3]
feature_ledger=read('build/m50-features/results.json');include('build/m50-features/results.json')
assert len(feature_ledger)==15 and all(r['exit_code']==0 for r in feature_ledger.values())
features={}
for label,row in feature_ledger.items():
    include(row['log']);args=row['args'];mapped='--mapped' in args
    if args[0]=='test_spike_differential.py':
        top=args[args.index('--top')+1] if '--top' in args else 'SpinorStandard'
        suffix='bounded' if '--bounded' in args else 'compact' if '--compact' in args else 'full'
        rel=f'build/spike-differential/{top}-{suffix}-'+('mapped' if mapped else 'rtl')+'/results.json'
    else:
        top=args[args.index('--top')+1] if '--top' in args else 'RamVectorFp'
        rel=f'build/fp-select/{top}-'+('compact' if '--compact' in args else 'full')+'-'+('mapped' if mapped else 'rtl')+'-results.json'
    features[label]=checked(rel)
    assert features[label]['mapped']==mapped
for label in ['standard','integer']:
    for key in ['commands','legal_encodings','illegal_encodings','timings']:
        assert features[f'spike-{label}-bounded'][key]==features[f'spike-{label}-mapped'][key],(label,key)
for prefix in ['select','select-deep']:
    native='select-compact' if prefix=='select' else prefix
    for key in ['commands','cases','case_specs','coverage','summary']:assert features[native][key]==features[prefix+'-mapped'][key],(prefix,key)
math_names={e['name'] for k in ['v_alu_int','v_alu_fp'] for e in catalog[k]}
full=features['spike-standard-full'];integer=features['spike-integer-full']
assert math_names<=full['legal_encodings'].keys()
assert {e['name'] for e in catalog['v_alu_int']}<=integer['legal_encodings'].keys()
with (OUT/'isa-coverage.csv').open('w',newline='') as output:
    writer=csv.writer(output,lineterminator='\n');writer.writerow(['encoding','class','match','mask','legal_type_blocks','illegal_type_blocks'])
    for group in ['v_alu_int','v_alu_fp']:
        for entry in catalog[group]:
            name=entry['name'];writer.writerow([name,group,hex(entry['match']),hex(entry['mask']),full['legal_encodings'].get(name,0),full['illegal_encodings'].get(name,0)])
include('reports/m50/isa-coverage.csv')
assert full['compared_registers_per_command']==32 and not full['memory_instructions'] and not full['probe']
inputs=read('build/spike-differential/SpinorStandard-full-rtl/inputs.json')
assert len({e['vtype_requested'] for e in inputs if 'vtype_requested' in e})==22
for entry in catalog['v_ctrl']:
    assert any(e['kind']=='I' and e['instruction']&entry['mask']==entry['match'] for e in inputs),entry['name']
select={kind:checked(f'build/spike-fp-select/{kind}/results.json') for kind in ['rtl','mapped']}
assert select['rtl']['commands']==select['mapped']['commands']==162
assert select['rtl']['timings']==select['mapped']['timings']
spike_negative=checked('build/spike-negative/results.json')
assert spike_negative['scope']=='NEGATIVE_CONTROL_EXPECTED_FAILURE' and spike_negative['simulation_exit_code']!=0

# Re-run the M49 compiler suite on the new hardware; never reuse its old receipt.
program_ledger=read('build/m49-regression/results.json');include('build/m49-regression/results.json')
expected={t+'-compact-'+k for t in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'] for k in ['rtl','mapped']}|{'SpinorStandard-full-rtl','SpinorInteger-full-rtl'}
assert set(program_ledger)==expected
programs={}
for label,row in program_ledger.items():
    assert row['exit_code']==0;include(row['log']);d=checked(row['results']);programs[label]=d
    assert not d['development_subset'] and d['compared_ram_bytes_per_case']==0xd000 and d['stack_excluded']
    assert d['cases']==len(d['metrics'])==len(d['case_specs'])
    assert sum(map(len,d['traces'].values()))==sum(m['commands'] for m in d['metrics'])
    for kernel in {s['kernel'] for s in d['case_specs'] if s['source']=='AUTO_VECTORIZED_C'}:
        raw=[int(v['instruction'],16) for s in d['case_specs'] if s['kernel']==kernel for v in d['traces'][str(s['id'])]]
        assert any(i&127==0x57 and (i>>12)&7!=7 for i in raw),(label,kernel,'no vector arithmetic')
        assert any(i&127==7 for i in raw),(label,kernel,'no vector load')
    for spec,metric in zip(d['case_specs'],d['metrics'],strict=True):
        assert spec['id']==metric['id'] and metric['ram_sha256']==spec['expected_ram_sha256']
        folder=Path(row['results']).parent
        assert hashlib.sha256(bytes.fromhex((ROOT/folder/f'{spec["id"]}.hex').read_text())).hexdigest()==spec['input_sha256']
        bind(folder/f'{spec["id"]}.bin',metric['ram_sha256'])
        if spec['expected_return'] is not None:assert metric['return_value']==spec['expected_return']
for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
    for key in ['cases','native_scalar_crosscheck_cases','families','case_specs','metrics','traces']:
        assert programs[top+'-compact-rtl'][key]==programs[top+'-compact-mapped'][key],(top,key)
negative=programs['SpinorInteger-compact-rtl']['negative_control'];assert negative['status']=='PASS' and negative['rejected_cases']
for ident in negative['rejected_cases']:
    p=f'build/programs/SpinorInteger-compact-rtl/{ident}.bin.bad';include(p)
    assert (ROOT/p).read_bytes()!=(ROOT/p.removesuffix('.bad')).read_bytes()
assert checked('build/program-scalar/results.json')['cases']==264
checked('build/programs/build.json')
program_counts=dict(program_calls=sum(d['cases'] for d in programs.values()),native_scalar_crosschecks=sum(d['native_scalar_crosscheck_cases'] for d in programs.values()),negative_rejected=len(negative['rejected_cases']))
assert program_counts['program_calls']==1082 and program_counts['native_scalar_crosschecks']==832

perf=read('build/performance-m50/results.json');include('build/performance-m50/results.json')
bind('tests/performance.py',perf['benchmark_source_sha256']);bind('build/performance-m50/performance-tb.sv',perf['testbench_sha256'])
for label,rel in [('M40','archive/m40/rtl/RamVectorFp.sv'),('M50','build/rtl/RamVectorFp.sv')]:bind(rel,perf['results'][label]['rtl_sha256'])
assert len(perf['results']['M50']['cases'])==220
assert perf['results']['M40']['cases']==perf['results']['M50']['cases']
for p in (ROOT/'build/performance-m50').iterdir():
    if p.suffix in ['.json','.sv','.log']:include(p.relative_to(ROOT))

resources={}
tops=['VpuHostBoundary','VectorMemoryEngine','LishiVpuMemory16','FloatingPointEstimate','FloatingPointConvertResize','FloatingPointLaneResize','FloatingPointLaneWiden','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','RamVectorFp16','IntegerMultiplyFractional','FixedPointLane','RamVectorFp','SpinorVpu','LishiVpuMemory','VpuMonitor','FloatingPointLane','IntegerDivide']
for top in tops:
    d=checked(f'build/synth/{top}/summary.json');checked(f'build/synth/{top}/paths.json')
    assert dict(Counter(c['type'] for c in read(f'build/synth/{top}/mapped.json')['modules'][top]['cells'].values()))==d['mapped_cells']
    for n in ['synth.ys','synth.log']:include(f'build/synth/{top}/{n}')
    c=d['mapped_cells'];resources[top]=dict(logic_LUT=sum(v for k,v in c.items() if k.startswith('LUT')),FF=sum(v for k,v in c.items() if k.startswith('FD')),DSP=c.get('DSP48E2',0),RAM={k:v for k,v in c.items() if k.startswith('RAM')})
gate=checked('build/timing-budget/m50-gate/results.json');assert gate['assumed_link_ps']==100 and gate['target_period_ns']==1000/300
anchor=read('build/timing-budget/m25-baseline/budget.json');budgets={}
for label in ['m25-baseline','m40-baseline',*['m50-'+k for k in ['spinor','compute','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','host']]]:
    rel=f'build/timing-budget/{label}/budget.json';d=checked(rel);include(rel.removesuffix('.json')+'.md')
    assert d['weights_ps']==anchor['weights_ps'] and d['provenance']==anchor['provenance']
    assert d['passes_300MHz'] is None and not d['placed'] and not d['routed'] and not d['speed_grade_calibrated']
    scenario,=[s for s in d['scenarios'] if s['assumed_link_ps']==100]
    budgets[label]=dict(budget_ns=scenario['worst']['budget_ns'],excluded_DSP_endpoints=scenario['DSP_tainted_endpoints_excluded'])
    if label.startswith('m50-'):assert budgets[label]['budget_ns']<=1000/300
for m in [25,40]:include(f'archive/m{m}/synth-SpinorVpu/mapped.json.gz')
include('archive/m49/reports/receipt.json')
previous=read('archive/m49/reports/receipt.json')
for name in ['RamVector.scala','VpuMonitor.scala','GenerateConfigured.scala']:
    bind('archive/m49/source/'+name,previous['source_sha256']['src/main/scala/vpu/'+name])
for name in ['RamVectorFp','RamVectorFp16','SpinorVpu','LishiVpuMemory']:
    bind(f'archive/m49/rtl/{name}.sv',previous['artifact_sha256'][f'build/rtl/{name}.sv'])
old_cells=previous['resources']['SpinorVpu']['mapped_cells']
assert resources['SpinorVpu']['logic_LUT']-sum(v for k,v in old_cells.items() if k.startswith('LUT'))==98
assert resources['SpinorVpu']['FF']==sum(v for k,v in old_cells.items() if k.startswith('FD'))
assert resources['SpinorVpu']['DSP']==old_cells.get('DSP48E2',0)
assert resources['SpinorVpu']['RAM']=={k:v for k,v in old_cells.items() if k.startswith('RAM')}

rows='\n'.join(f"| {top} | {d['logic_LUT']} | {d['FF']} | {d['DSP']} |" for top,d in resources.items() if top in ['SpinorVpu','LishiVpuMemory','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'])
program_summary={label:dict(cases=d['cases'],cycles=sum(m['cycles'] for m in d['metrics']),commands=sum(m['commands'] for m in d['metrics']),requests=sum(m['requests'] for m in d['metrics'])) for label,d in programs.items()}
(OUT/'performance.md').write_text('# M50 程序周期参考\n\n沿用M49标量测试适配器与单事务TileLink反压模型，全部在M50硬件上重跑。不是Orbital IPC或实际应用性能。\n\n| 矩阵 | 调用 | VPU命令 | TL请求 | 适配器周期 |\n|---|---:|---:|---:|---:|\n'+'\n'.join(f"| {k} | {v['cases']} | {v['commands']} | {v['requests']} | {v['cycles']} |" for k,v in program_summary.items())+'\n')
(OUT/'evaluation.md').write_text((ROOT/'docs/m50-spike-and-fp-select.md').read_text().replace('(../reports/m50/evaluation.md)','(evaluation.md)')+f'''\n\n## 本轮结果\n\n314种算术编码在标准预设22种合法SEW/LMUL配置中逐条对照Spike，共{full['commands']}条命令；每种编码至少有一个合法执行点。整数预设213种，共{integer['commands']}条命令。深流水预设使用紧凑矩阵；综合网表使用代表性子集，不宣称网表覆盖全部314种。每条命令比较全部32行VRF及已实现CSR。合法范围外的编码同时检查非法返回；测试分布不是所有操作数/舍入/重叠组合的穷举。\n\n新FP选择通路独立位模式参考通过{features['select-full']['commands']}条命令；专项Spike对照RTL/网表各162条命令。15项新功能矩阵、167项原RTL、57项原网表均通过；原算术缓存因核心改动失效，224项原矩阵全部重跑。7项局部SAT证明全部按当前输入SHA核对；增量地址证明因绑定核心源码而重新执行，其余6项输入一致并复用原证明。M49编译器矩阵重新运行10组，共{program_counts['program_calls']}次调用、{program_counts['native_scalar_crosschecks']}次本机C交叉检查，负控制检出{program_counts['negative_rejected']}次错误。220组性能对照周期保持M40基线，223份默认/预设生成文件重新生成逐字节相同。\n\n| 顶层 | 逻辑LUT | FF | DSP |\n|---|---:|---:|---:|\n{rows}\n\n公共顶层相对M49增加98逻辑LUT，FF/DSP/VRF RAM数量不变：32 RAM64M8、6 RAM32M16（LUTRAM）。固定100ps/link条件模型公共顶层与计算/访存均为{budgets['m50-spinor']['budget_ns']:.3f}ns，四预设均≤3.333ns。权重与M25不变；排除DSP影响端点，未布局布线、未进行-2器件STA/SDF。实际300/500MHz仍未知。\n\nmonitor实现ID为0x5001，ABI1与能力位布局保持。仍为VLEN128/ELEN64、单lane、单指令容量；未完成完整V/RVA23、Orbital或Linux计算驱动集成。完整输入/输出散列及范围见receipt；[逐编码覆盖](isa-coverage.csv)、[程序周期](performance.md)。\n''')
for n in ['evaluation.md','performance.md']:include('reports/m50/'+n)
source={ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']}
for directory in ['src','scripts','tests','docs','software','third_party']:
    source.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
receipt=dict(project='Spinor VPU',milestone='M50',status='PASS',source_sha256={str(p.relative_to(ROOT)):sha(p.relative_to(ROOT)) for p in sorted(source)},artifact_sha256={p:sha(p) for p in sorted(artifacts)},external_tool_dependency_sha256=external,
             regression_counts=counts,legacy_result_manifests=len(legacy),paired_legacy_results=paired_legacy,regeneration=regeneration,spike_revision=model['revision'],spike_semantics_modified=False,
             spike_coverage=dict(arithmetic_encodings=314,integer_encodings=213,configuration_encodings=3,legal_types=22,standard_commands=full['commands'],integer_commands=integer['commands'],all_registers_per_command=32,nonzero_vstart_arithmetic=False,memory_instructions=False),
             feature_counts={k:dict(commands=d['commands'],mapped=d['mapped']) for k,d in features.items()},spike_fp_select_commands=162,spike_checker_negative_control=spike_negative,program_counts=program_counts,program_summary=program_summary,
             resources=resources,conditional_budgets=budgets,conditional_reference_gate=gate,monitor_implementation='0x5001',monitor_abi=1,
             Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,actual_Orbital_integrated=False,full_V=False,full_RVA23=False)
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('PASS M50 report',len(legacy),'prerequisite manifests',len(artifacts),'artifact bindings',flush=True)
