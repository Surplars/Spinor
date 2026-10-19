#!/usr/bin/env python3
"""Bind numerical policy/fault recovery verification and bounded clause coverage."""
import csv
import json
from pathlib import Path
from m58_evidence import ROOT,sha,check,baseline

TOPS=['SpinorStandard','SpinorDeep']


def main():
    previous=baseline();out=ROOT/'reports/m58';out.mkdir(parents=True,exist_ok=True)
    sources={};artifacts={}
    def bind(rel,h):
        target=sources if rel.startswith(('src/','tests/','scripts/')) else artifacts
        if rel in target:assert target[rel]==h,('contradictory binding',rel)
        target[rel]=h
    def manifest(rel):
        d=json.loads((ROOT/rel).read_text());assert d['status']=='PASS',rel;check(d)
        artifacts[rel]=sha(ROOT/rel)
        for group in ('source_sha256','artifact_sha256'):
            for p,h in d.get(group,{}).items():bind(p,h)
        if 'oracle_binary' in d:
            assert sha(ROOT/d['oracle_binary'])==d['oracle_binary_sha256'];artifacts[d['oracle_binary']]=d['oracle_binary_sha256']
        return d
    refs=[]
    for policy in range(4):
        d=manifest(f'build/m58/policies/p{policy}/results.json')
        assert d['commands']==29040 and d['scenarios']==7260 and len(d['successful_encodings'])==330
        assert d['legal_targets']==5421 and d['rejected_targets']==1839
        assert d['oracle']=='UNMODIFIED_SPIKE_ACTUAL_VTA_VMA_BITS_NO_EXPECTATION_NORMALIZATION'
        refs.append(d)
    recovery=manifest('build/m58/recovery/results.json');assert recovery['commands']==1384 and recovery['scenarios']==404
    clauses=manifest('build/m58/clauses/results.json');assert len(clauses['clauses'])==5
    assert clauses['counts']==dict(legal_targets=21684,tail_elements=86872,inactive_elements=49450,elementwise_targets=10104,all_inactive_fp=740)
    runs={};commands=negatives=0
    for top in TOPS:
        # Compile records bind the exact current cached production models and
        # test harness; the latter has no numerical instruction semantics.
        build_path=ROOT/f'build/m58/bin/{top}/build.json';build=json.loads(build_path.read_text())
        for rel,h in build['inputs'].items():assert sha(ROOT/rel)==h,rel;bind(rel,h)
        runs[top]={}
        for policy in range(4):
            d=manifest(f'build/m58/policies/p{policy}/{top}/results.json')
            assert not d['trace_replay'] and d['commands']==29040 and d['checked_registers_per_command']==32
            commands+=d['commands'];negatives+=len(d['negative_controls']);runs[top]['policy'+str(policy)]=d['summary']
        d=manifest(f'build/m58/recovery/{top}/results.json');assert not d['trace_replay'] and d['commands']==1384 and d['checked_ram_bytes_per_command']==8192
        assert 'requests=6232 responses=6232' in d['summary'];commands+=d['commands'];negatives+=len(d['negative_controls']);runs[top]['recovery']=d['summary']
    assert commands==235088 and negatives==36
    gate=json.loads((ROOT/'build/m56/timing/gate/results.json').read_text())
    assert gate['passes_300MHz'] is None and {v['budget_ns'] for v in gate['results'].values()}=={3.3}
    artifacts['build/m56/timing/gate/results.json']=sha(ROOT/'build/m56/timing/gate/results.json')
    (out/'recovery-cases.csv').write_bytes((ROOT/'build/m58/recovery/cases.csv').read_bytes())
    (out/'semantic-clauses.json').write_text(json.dumps(dict(scope=clauses['scope'],counts=clauses['counts'],
        elementwise_encodings=clauses['elementwise_encodings'],clauses=clauses['clauses'],negative_controls=clauses['negative_controls']),indent=2)+'\n')
    table=[]
    for policy,d in enumerate(refs):
        for name,count in sorted(d['successful_encodings'].items()):table.append(dict(name=name,vta=policy&1,vma=policy>>1,successful_geometries=count,attempted_geometries=22))
    with (out/'policy-coverage.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator='\n');w.writeheader();w.writerows(table)
    for p in [*sorted((ROOT/'src/main/scala').rglob('*.scala')),*sorted((ROOT/'scripts').glob('*m58*.py')),*sorted((ROOT/'tests').glob('*m58*')),
              ROOT/'.gitattributes',ROOT/'README.md',ROOT/'CURRENT.md',ROOT/'docs/isa-coverage.md',ROOT/'docs/rvv-completion-plan.md',ROOT/'docs/m58-semantics.md']:
        if p.is_file():bind(str(p.relative_to(ROOT)),sha(p))
    for p in [ROOT/'archive/m57/baseline.json',*sorted((ROOT/'archive/m57/source').rglob('*')),ROOT/'reports/m57/receipt.json',
              ROOT/'docs/references/m57-v-spec-maintained.adoc',ROOT/'docs/references/m57-sources.json',out/'policy-coverage.csv',out/'recovery-cases.csv',out/'semantic-clauses.json']:
        if p.is_file():artifacts[str(p.relative_to(ROOT))]=sha(p)
    text=f'''# M58：尾部/掩码数值语义与字段级恢复

硬件保持M56/M57：{previous['hardware_sources_unchanged']}个Scala源文件不变，VLEN128/ELEN64、单lane、
单指令在途、版本化RAM不变。没有为了测试复制CPU或改变宿主所有权。
本轮在标准/Deep的实际公共命令、上下文和TileLink端口重新运行新独立语料。

## 四种策略的数值矩阵

每预设 **330种算术编码×22种SEW/LMUL配置×4种vta/vma = 29,040目标场景**，
每场景含配置、vcsr/FCSR初始化和目标指令，共 **116,160条命令**。
**两预设合计232,320条命令**，每条比较全部32个向量寄存器与已实现CSR。
22种配置是基础合法vtype；具体操作不支持的宽度/EMUL组合由参考拒绝，
每种策略有5,421合法目标、1,839拒绝目标；330种编码每种均有合法点。
[逐编码/策略覆盖](policy-coverage.csv)。

本轮使用VL>0与非零数据；请求VL为1或max(1,VLMAX-1)，包含跨寄存器体和尾部。
mask形式按操作/配置/策略循环选择未掩码、全关、交错、全开；编码固定vm的形式
保持规范位。**不是所有mask模式与每个几何的完整笛卡尔积**。
所有目标vstart=0，寄存器组固定为vd8/vs2=16/vs1=24，单目/搬运字段服从编码mask。
因此不声称本轮穷举重叠或非零算术vstart；它们仍是后续条款工作。

参考是未修改的固定Spike，传入**实际vta/vma位**；没有用TU/MU替换配置、
没有掩去tail/mask数据，也没有从DUT结果生成期望值。固定Spike与Spinor都选择
允许的undisturbed策略，完整位比较通过不意味着规范要求所有实现选择同样结果。
数据包含sNaN、subnormal、符号边界、舍入/饱和边界、标量未NaN-box值与gather边界。
每策略有实际fflags/vxsat变化，旧FCSR中已有异常位也被保留比较。

对独立参考结果再按明确规范谓词核对，且这些结果都已完整比较DUT：
**10,104个选定同宽逐元素目标、86,872个tail元素、49,450个inactive元素**保持，
**740个全mask关闭的合法FP目标**从fflags=0开始且没有产生flags，避免已有标志掩盖异常。
FP分类使用实际指令格式位；vfmerge的v0是选择数据，不归入执行mask全关。
以上是**独立语料计数**，
不是两份DUT执行相加；特定同宽集合见[条款及操作清单](semantic-clauses.json)。

## 恢复与后续使用VL

每预设 **404场景、1,384命令、6,232次TL请求/响应**，每条比较32个向量寄存器、
CSR、8KiB RAM、访存fault/status/tval与所有者身份。

- 324个跨步分段场景：EEW16/64、NF5/6/7的load/store，正/负步长，
  每字段在元素0/1出错；另含全mask关闭、被掩去的故障段、非零vstart后首活动段。
  故障保留原VL，vstart以整段计；清除故障后从该段恢复，比较字段前缀和最终RF/RAM。
- 80个单位步长分段FOF场景：四种EEW、NF2/8、每字段、元素0/1。
  40个元素0故障保留VL并返回异常；40个后续故障正常完成、VL从2缩为1。
  **随后真实执行vadd和CSR读VL，再清故障重试**，确认算术/CSR消费已发布VL。
  FOF缩短后重试继续使用缩短的VL，没有假装自动恢复原VL。

规范允许故障段/FOF截断点留部分字段，两边当前策略匹配，完整比较通过。
这是物理普通RAM的有界故障模型，不是页表/PMP/缓存一致性或实际CPU异常处理验收。
[逐场景结果](recovery-cases.csv)。

总计 **235,088条新Spike参考命令**，包含初始化/拒绝命令；目标向量指令数另列。
36次运行比较器错误注入（身份、RF、CSR、load数据、RAM、tval）与2次条款谓词
错误注入全部检出。规范映射使用逐字引文、行号和有界检查，不修改参考语义。

## 资源、时序与剩余工作

没有新增硬件、DSP、RAM或综合；通过54个硬件源文件的精确SHA证明本轮未改RTL输入。
沿用M56宿主公共/计算顶层 **3.300ns条件预算**，独立默认沿用M55的3.292/3.232ns。
模型排除DSP影响端点、没有器件布线/时钟、未按ZU15EG-2校准，不是STA/SDF。
**实际300MHz仍需当前RTL的Vivado结果**，没有把测试执行速度当作硬件时序。

已建立5项具体规范条款及有界证据映射，并未关闭全部RVV条款。
寄存器重叠、非零算术vstart、更广架构测试、Zvkt完整验收与实际SoC接入仍待推进。
旧375+16目录与310种访存形式的成功样本结论保持，**不声明完整V/RVA23/Zvkt**。
CPU取指/退休、特权、VS/FS、MMU/PMP和一致性仍属于宿主。

```bash
python3 scripts/verify_m58.py
python3 scripts/verify_m58.py --check-only
```

需要保留的M55/M56/M57工具和历史证据。新增inline RF只改变测试传输，仍复用原公共
端口检查器；压缩流与各运行独立临时文件避免大量golden文件和并行覆盖。
没有旧DUT trace重放、旧receipt改写、Orbital联编、Linux或板上程序声明。
'''
    (out/'evaluation.md').write_text(text);sources['reports/m58/evaluation.md']=sha(out/'evaluation.md')
    d=dict(status='PASS',milestone=58,hardware_changed=False,baseline=previous,new_spike_commands=commands,policy_target_scenarios_per_top=29040,
           recovery_scenarios_per_top=404,runs=runs,semantic_predicate_counts=clauses['counts'],runtime_negative_controls=negatives,predicate_negative_controls=2,
           full_v=False,full_rva23=False,zvkt_claimed=False,passes_300MHz=None,passes_500MHz=None,source_sha256=sources,artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(d,indent=2)+'\n');check(d)
    print('PASS M58',commands,'new commands;',len(artifacts),'bound artifacts',flush=True)


if __name__=='__main__':main()
