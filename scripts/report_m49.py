#!/usr/bin/env python3
"""Bind compiler programs, exact M48 reuse, re-elaboration and fixed timing."""
import hashlib
import json
import re
from pathlib import Path
from m49_evidence import ROOT,base_evidence,sha

OUT=ROOT/'reports/m49'
OUT.mkdir(parents=True,exist_ok=True)
base,reuse=base_evidence()
artifacts=set(base['artifact_sha256'])|{'reports/m48/receipt.json'}
tool_dependencies={}


def include(rel):
    assert (ROOT/rel).is_file(),rel
    if Path(rel).parts[0]=='tools':
        # Tool inputs stay hash-bound but are obtained by the pinned bootstrap,
        # just like the compiler and RapidWright, rather than shipped in ZIPs.
        tool_dependencies[rel]=sha(ROOT/rel)
        return
    artifacts.add(rel)


def checked(rel):
    data=json.loads((ROOT/rel).read_text());assert data['status']=='PASS',rel
    include(rel)
    for key in ['sha256','input_sha256','source_sha256','artifact_sha256']:
        for path,h in data.get(key,{}).items():
            assert sha(ROOT/path)==h,(rel,path)
            include(path)
    return data


policy=checked('build/m49-policy/results.json')
assert policy['checks']==7
regeneration=checked('build/m49-regeneration/results.json')
assert regeneration['files']==223
scalar_adapter=checked('build/program-scalar/results.json')
assert scalar_adapter['cases']==264
for name in ['default','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
    include(f'build/m49-regeneration/{name}.log')
gate=checked('build/timing-budget/m49-gate/results.json')
assert gate['assumed_link_ps']==100 and gate['target_period_ns']==1000/300
budgets={}
for label in ['spinor','compute','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','host']:
    path=f'build/timing-budget/m49-{label}/budget.json'
    data=json.loads((ROOT/path).read_text())
    assert data['weights_ps']==base['conditional_budgets']['m48-spinor']['weights_ps']
    assert data['provenance']==base['conditional_budgets']['m48-spinor']['provenance']
    assert data['passes_300MHz'] is None and data['passes_500MHz'] is None
    assert not data['placed'] and not data['routed'] and not data['speed_grade_calibrated']
    for rel,h in data['input_sha256'].items():assert sha(ROOT/rel)==h,rel;include(rel)
    include(path);include(path.removesuffix('.json')+'.md')
    scenario,=[s for s in data['scenarios'] if s['assumed_link_ps']==100]
    assert scenario['worst']['budget_ns']<=1000/300
    budgets[label]=dict(budget_ns=scenario['worst']['budget_ns'],excluded_DSP_endpoints=scenario['DSP_tainted_endpoints_excluded'])

ledger_path='build/m49-regression/results.json';include(ledger_path)
ledger=json.loads((ROOT/ledger_path).read_text())
expected={t+'-compact-'+kind for t in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'] for kind in ['rtl','mapped']}
expected|={'SpinorStandard-full-rtl','SpinorInteger-full-rtl'}
assert set(ledger)==expected
programs={}
for label,row in ledger.items():
    assert row['exit_code']==0,row
    include(row['log']);d=checked(row['results'])
    assert label.startswith(d['top']+'-') and d['mapped']==label.endswith('-mapped')
    assert not d['development_subset'] and d['assertions_enabled']==(not d['mapped'])
    assert d['compared_ram_bytes_per_case']==0xd000 and d['stack_excluded']
    assert len(d['metrics'])==len(d['case_specs'])==d['cases']
    assert sum(len(v) for v in d['traces'].values())==sum(m['commands'] for m in d['metrics'])
    expected_cases=(50 if 'Integer' in label else 56) if 'compact' in label else (309 if 'Integer' in label else 349)
    assert d['cases']==expected_cases,(label,d['cases'])
    assert d['native_scalar_crosscheck_cases']==(39 if 'compact' in label else 260)
    for s,m in zip(d['case_specs'],d['metrics'],strict=True):
        assert s['id']==m['id'] and m['ram_sha256']==s['expected_ram_sha256']
        folder=Path(row['results']).parent
        image=bytes.fromhex((ROOT/folder/f'{s["id"]}.hex').read_text())
        assert hashlib.sha256(image).hexdigest()==s['input_sha256']
        assert hashlib.sha256((ROOT/folder/f'{s["id"]}.bin').read_bytes()).hexdigest()==m['ram_sha256']
        if s['expected_return'] is not None:assert s['expected_return']==m['return_value']
    # Prove every automatically vectorized kernel actually reaches arithmetic
    # and RAM instructions; a vlenb CSR read alone is not vector execution.
    for name in {s['kernel'] for s in d['case_specs'] if s['source']=='AUTO_VECTORIZED_C'}:
        traces=[v for s in d['case_specs'] if s['kernel']==name for v in d['traces'][str(s['id'])]]
        instructions=[int(v['instruction'],16) for v in traces]
        assert any(i&127==87 and (i>>12)&7!=7 for i in instructions),(label,name,'arithmetic not executed')
        assert any(i&127==7 for i in instructions),(label,name,'load not executed')
    programs[label]=d

for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:
    rtl=programs[top+'-compact-rtl'];mapped=programs[top+'-compact-mapped']
    for key in ['cases','native_scalar_crosscheck_cases','families','case_specs','metrics','traces']:
        assert rtl[key]==mapped[key],(top,key)
negative=programs['SpinorInteger-compact-rtl']['negative_control']
assert negative['status']=='PASS' and negative['mutation']=='XOR_BIT0_EVERY_TL_RESPONSE_DATA'
assert negative['rejected_cases']
folder=ROOT/'build/programs/SpinorInteger-compact-rtl'
for ident in negative['rejected_cases']:
    path=folder/f'{ident}.bin.bad'
    assert path.read_bytes()!=(folder/f'{ident}.bin').read_bytes()
    include(str(path.relative_to(ROOT)))

build=checked('build/programs/build.json')
assert '19.1.7' in build['compiler']
all_assembly=(ROOT/'build/programs/kernels.s').read_text()+(ROOT/'build/programs/stripmine.s').read_text()
mnemonics=sorted(set(re.findall(r'^\s+(v[a-z0-9.]+)\s',all_assembly,re.M)))
assert {'vwmacc.vv','vredsum.vs','vlseg2e32.v','vluxei64.v','vle8ff.v','vfadd.vv','vdiv.vv','vnmsub.vv','vsra.vv'}<=set(mnemonics)
summary={label:dict(cases=d['cases'],native_scalar_crosschecks=d['native_scalar_crosscheck_cases'],
                    cycles=sum(m['cycles'] for m in d['metrics']),commands=sum(m['commands'] for m in d['metrics']),
                    requests=sum(m['requests'] for m in d['metrics']),families=d['families']) for label,d in sorted(programs.items())}
counts=dict(program_calls=sum(d['cases'] for d in programs.values()),
            native_scalar_crosschecks=sum(d['native_scalar_crosscheck_cases'] for d in programs.values()),
            rtl_runs=6,mapped_runs=4,negative_control_rejected_calls=len(negative['rejected_cases']))
assert counts['program_calls']==1082 and counts['native_scalar_crosschecks']==832

rows=[]
for label,d in summary.items():
    rows.append(f"| {label} | {d['cases']} | {d['commands']} | {d['requests']} | {d['cycles']} |")
performance='''# M49 编译器程序周期参考

程序从ELF函数入口执行至返回，标量测试适配器每条标量指令记一拍，VPU命令等待真实completion；TL采用单事务、请求反压、1～4拍响应计数后注册发布D，completion额外等待1～4拍。复位、ELF/数据装入和结果导出不计入表内周期。这不是Orbital IPC、器件频率或实际应用吞吐率。RTL与网表对相同预设/输入的逐调用数值、总线次数、周期和动态VPU轨迹一致。

| 预设/矩阵 | 函数调用 | VPU命令 | TL请求 | 适配器周期 |
|---|---:|---:|---:|---:|
'''+ '\n'.join(rows)+'\n'
function_rows=[]
full=programs['SpinorStandard-full-rtl']
for spec,metric in zip(full['case_specs'],full['metrics'],strict=True):
    if spec['n']!=129 or spec['kernel']=='fof_copy':continue
    function_rows.append(f"| {spec['kernel']} | 129 | {metric['commands']} | {metric['requests']} | {metric['scalar_instructions']} | {metric['cycles']} |")
performance+='''
## 标准预设的129元素调用

含标量尾部、VPU指令等待和上述TL/完成反压；不同函数的数据宽度、访存量与工作量不同，不能把行间周期比当作等工作量加速比。

| 函数 | 元素 | VPU命令 | TL请求 | 标量指令 | 适配器周期 |
|---|---:|---:|---:|---:|---:|
'''+ '\n'.join(function_rows)+'\n'
(OUT/'performance.md').write_text(performance);include('reports/m49/performance.md')
doc=(ROOT/'docs/m49-compiled-programs.md').read_text()
evaluation=doc+f'''

## 本轮结果

6组RTL、4组综合网表程序矩阵全部通过，共{counts['program_calls']}次函数调用；其中{counts['native_scalar_crosschecks']}次普通C函数同时由本机标量C与Python逐字节参考交叉核对。每次检查完整0xd000字节RAM，包含代码、输入、输出和保护区域；仅栈区域排除。故意翻转TL读数据bit0后，RAM参考检出{counts['negative_control_rejected_calls']}次调用结果错误。

默认生成与四预设共{regeneration['files']}份SV/manifest重新生成逐字节相同。沿用M48硬件执行证据：校验{reuse['checked_sources']}项原源码及全部{reuse['checked_artifacts']}项证据；允许变化的交付说明文件为{', '.join(reuse['changed_delivery_only']) or '无'}。M48原矩阵167项RTL/57项网表本轮未重跑；其原账本包含124/24项M42算术证据复用，本轮未将其计为新执行。新程序矩阵全部本轮运行。

固定100ps/link模型：公共顶层{budgets['spinor']['budget_ns']:.3f}ns、计算/访存{budgets['compute']['budget_ns']:.3f}ns；四预设{min(budgets[t]['budget_ns'] for t in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']):.3f}～{max(budgets[t]['budget_ns'] for t in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']):.3f}ns。权重与M25不变，均通过3.333ns条件门槛。没有布局布线、-2校准或完整DSP时序覆盖，实际300/500MHz未知。

硬件资源与M48完全相同：默认公共顶层23108逻辑LUT、13204 FF、9 DSP、32 RAM64M8和6 RAM32M16；其中RAM为LUTRAM。monitor实现ID仍为0x4801。本轮新增编译/执行验证能力，没有新增指令或宣称完整V/RVA23。

[周期明细](performance.md)。逐调用输入、实际RAM、期望散列、动态指令轨迹、编译器版本/参数和全部证据路径见receipt及build/programs。
'''
(OUT/'evaluation.md').write_text(evaluation)
source={ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']}
for directory in ['src','scripts','tests','docs','software','third_party']:
    source.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
receipt=dict(project='Spinor VPU',milestone='M49',status='COMPILED_RVV_PROGRAMS_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
             source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted(source)},
             artifact_sha256={rel:sha(ROOT/rel) for rel in sorted(artifacts)},
             external_tool_dependency_sha256=tool_dependencies,
             hardware_changed=False,monitor_implementation='0x4801',m48_evidence_reuse=reuse,
             reuse_policy_test=policy,scalar_adapter_test=scalar_adapter,
             compiler=build,program_counts=counts,programs=summary,vector_mnemonics=mnemonics,
             regeneration=regeneration,resources=base['resources'],conditional_budgets=budgets,conditional_reference_gate=gate,
             full_rvv=False,independent_ISA_model_differential=False,actual_Orbital_integrated=False,Vivado_executed=False,
             passes_300MHz=None,passes_500MHz=None,
             scope='Freestanding LLVM RVV C ELF functions on a simulation-only scalar adapter and real public VPU; no ISA compliance or SoC claim')
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(receipt['status']);print(json.dumps(counts));print('All four RTL/mapped program traces and per-call cycle counts match')
