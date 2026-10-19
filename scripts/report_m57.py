#!/usr/bin/env python3
"""Independent ISA directory ledger, new DUT runs and exact evidence binding."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from m57_evidence import ROOT, sha, check, baseline
sys.path.insert(0, str(ROOT/'tests'))
from m57_isa_catalog import audited_catalog, negative_controls

TOPS = ['SpinorStandard', 'SpinorDeep']


def main():
    previous = baseline()
    out = ROOT/'reports/m57'
    out.mkdir(parents=True, exist_ok=True)
    sources, artifacts = {}, {}
    def bind(rel, expected):
        target = sources if rel.startswith(('src/', 'scripts/', 'tests/')) else artifacts
        if rel in target:
            assert target[rel] == expected, ('contradictory binding', rel)
        target[rel] = expected
    def manifest(path):
        d = json.loads((ROOT/path).read_text())
        assert d['status'] == 'PASS', path
        check(d)
        artifacts[path] = sha(ROOT/path)
        for group in ('source_sha256', 'artifact_sha256'):
            for rel, h in d.get(group, {}).items():
                bind(rel, h)
        # Retain executable and compiled-model source identities too.
        if 'oracle_binary' in d:
            assert sha(ROOT/d['oracle_binary']) == d['oracle_binary_sha256']
            artifacts[d['oracle_binary']] = d['oracle_binary_sha256']
        if 'model_binary' in d:
            assert sha(ROOT/d['model_binary']) == d['model_binary_sha256']
            artifacts[d['model_binary']] = d['model_binary_sha256']
        return d
    entries = audited_catalog()
    catalog_negatives = negative_controls()
    ledger = []
    for r in entries:
        family = r['family']
        decode = 'VectorMemoryEngine.scala' if family == 'memory' else 'RamVector.scala'
        execute = {'integer': 'IntegerLane.scala / RamVector.scala', 'floating': 'FloatingPointLane.scala / FloatingPointConvertResize.scala / RamVector.scala',
                   'configuration': 'VectorConfig.scala / RamVector.scala', 'memory': 'VectorMemoryEngine.scala',
                   'zvbb': 'BitManipPipeline.scala / IntegerLane.scala'}[family]
        ledger.append(dict(extension=r['extension'], family=family, name=r['name'], match=f'0x{r["match"]:08x}', mask=f'0x{r["mask"]:08x}',
                           reference=r['source']+':'+str(r['line']), decode_source='src/main/scala/vpu/'+decode,
                           execution_source=execute, successful_direct_samples=r['successful_direct_samples'],
                           sample_evidence='reports/m55/canonical-coverage.csv', status='IMPLEMENTED_WITH_SAMPLES_NOT_SEMANTIC_SIGNOFF'))
    with (out/'isa-catalog.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(ledger[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(ledger)
    decode_commands = state_commands = memory_commands = policy_commands = run_negatives = 0
    records = {}
    for s in (8, 16, 32, 64):
        d = manifest(f'build/m57/decode/sew{s}/results.json')
        assert d['commands'] == 17365
    state_ref = manifest('build/m57/state/results.json')
    memory_ref = manifest('build/m57/memory-forms/results.json')
    assert state_ref['commands'] == 17064 and state_ref['csr_cases'] == 1512
    assert memory_ref['expanded_memory_forms'] == 310 and memory_ref['previous_forms_with_success'] == 298 and len(memory_ref['previous_unsampled_forms']) == 12
    (out/'memory-forms.csv').write_bytes((ROOT/'build/m57/memory-forms/coverage.csv').read_bytes())
    for top in TOPS:
        records[top] = {}
        cache = json.loads((ROOT/f'build/m55/gsim/bin/{top}/build.json').read_text())
        for rel, expected in cache['inputs'].items():
            assert sha(ROOT/rel) == expected, rel
            bind(rel, expected)
        for s in (8, 16, 32, 64):
            d = manifest(f'build/m57/decode/sew{s}/{top}/results.json')
            assert not d['numerical_arithmetic'] and not d['trace_replay'] and d['checked_registers_per_command'] == 32
            assert d['commands'] == 17365
            decode_commands += d['commands']
            run_negatives += len(d['negative_controls'])
            records[top]['decode_sew'+str(s)] = dict(commands=d['commands'], legal=d['legal'], rejected=d['rejected'])
        for suite, folder in [('state', 'state'), ('memory', 'memory-forms'), ('reserved', 'reserved')]:
            d = manifest(f'build/m57/{folder}/{top}/results.json')
            run_negatives += len(d['negative_controls'])
            records[top][suite] = dict(commands=d['commands'], summary=d['summary'])
            if suite == 'state': state_commands += d['commands']
            elif suite == 'memory':
                memory_commands += d['commands']
                assert d['scenarios'] == 418 and d['checked_ram_bytes_per_command'] == 8192
                assert 'requests=5048 responses=5048' in d['summary']
            else:
                assert d['oracle'] == 'NORMATIVE_RESERVED_REJECTION_POLICY_NOT_SPIKE' and d['reserved_cases'] == 336
                policy_commands += d['commands']
    differential = decode_commands + state_commands + memory_commands
    assert differential == 175556 and policy_commands == 2024 and run_negatives == 46
    gate = json.loads((ROOT/'build/m56/timing/gate/results.json').read_text())
    assert gate['passes_300MHz'] is None and {x['budget_ns'] for x in gate['results'].values()} == {3.3}
    artifacts['build/m56/timing/gate/results.json'] = sha(ROOT/'build/m56/timing/gate/results.json')
    for p in [*sorted((ROOT/'src/main/scala').rglob('*.scala')), *sorted((ROOT/'scripts').glob('*m57*.py')),
              *sorted((ROOT/'tests').glob('*m57*.py')), ROOT/'.gitattributes', ROOT/'README.md', ROOT/'CURRENT.md', ROOT/'docs/isa-coverage.md', ROOT/'docs/rvv-completion-plan.md', ROOT/'docs/m57-isa-audit.md']:
        sources[str(p.relative_to(ROOT))] = sha(p)
    for p in [*sorted((ROOT/'docs/references').glob('m57-*')), ROOT/'archive/m56/baseline.json',
              *sorted((ROOT/'archive/m56/source').rglob('*')), out/'isa-catalog.csv', out/'memory-forms.csv', out/'initial-scope-probe.txt', ROOT/'reports/m56/receipt.json', ROOT/'reports/m55/canonical-coverage.csv']:
        if p.is_file(): artifacts[str(p.relative_to(ROOT))] = sha(p)
    text = f'''# M57：ISA 目录清账与分段访存覆盖补齐

独立解析固定版本 riscv-opcodes 的 rv_v/rv_zvbb，与既有成功执行目录逐项比较：
**375 条基础 V、16 条 Zvbb，名称与 match/mask 全部一致，目录漏项 0**。
这确认目录覆盖，不能替代逐条规范语义或完整架构合规验收。

本轮没有修改 {previous['hardware_sources_unchanged']} 个 Scala 硬件源文件。标准/Deep
复用 M56 已确认默认 RTL 与 M55 逐字节一致所对应的 GSim 模型，**本轮重新执行新语料**，
没有重放旧 DUT trace；整数预设与宿主 FCSR 版沿用历史证据，不冒充本轮新测。

## 本轮新增验证

- 两预设、四种 SEW，各 17,365 条原始 OP-V 命令，共 **{decode_commands:,} 条**。
  覆盖 funct6/funct3/vm、单目选择码、scalar/immediate 寄存器字段和 vs2=0 搬运形式。
  **VL=0、LMUL1、固定向量寄存器布局**；检查完整 RF/CSR 和完成身份，不宣称数值算术、
  所有寄存器别名或全部 32 位编码穷举。参考拒绝编码也计入命令数。
- 每预设 **17,064 条 vtype/CSR 命令**：vsetvli 的全部 2,048 种立即数、
  vsetivli 的全部 1,024 种 vtype 立即数，vsetvl 的低 8 位及全部高位单 bit；
  覆盖所定义 AVL、x0 规则、六种 CSR 动作、源/目的零寄存器、只读与保留 CSR。
  使用未修改 Spike；改变 VLMAX 的 rd=rs1=x0 保留形式没有混入比较。
- NF 字段展开后，原参考语料 **310 种访存形式有 298 种成功样本**，
  缺口是 vlse/vsse 的 EEW16/64、NF5/6/7 共12种。新增语料让 **310/310 均成功**，
  含上述12种的负/零步长、掩码、VL0、非零 vstart。
  每预设 **418 场景、1,254 命令、5,048 次实际 TL 请求/响应**；每条比较32个向量
  寄存器、已实现CSR和8KiB RAM。它补齐了成功样本，不是新加12条硬件指令。
- 每预设 **336 个进位源混合 EEW 保留场景、1,012 条命令**，检查未改 RF/CSR、
  无 TL 请求、VL0 与非零 vstart。依据维护版规范的 source-EEW 澄清，
  **独立策略检查，不称为 Spike 比较**。原 v1.0 tag 与维护版均冻结且标明来源。
- 总计 **{differential:,} 条 Spike 差分命令 + {policy_commands:,} 条独立策略命令**；
  {run_negatives} 次运行比较器错误注入、{catalog_negatives} 次目录错误注入全部检出。

首次扫描的0x40004457属于上述保留源别名，Spike会执行；随后限定零vs2扩展只针对
标量搬运格式，分歧用独立策略重新验证。并行脚本曾重写共享零RF文件，导致读短；
修复为各SEW独立文件后，全部接受运行重跑。失败诊断保留在initial-scope-probe.txt，
没有计入成功命令或硬件问题。没有隐藏或修改上游参考语义。

## ISA、集成和时序的界限

[逐编码清单](isa-catalog.csv)、[310种访存形式](memory-forms.csv)、
[当前 ISA 结论及未关闭验收项](../../docs/m57-isa-audit.md)。
本轮没有发现缺失的目录指令，但尚未完成逐条规范语义映射和完整架构测试验收。
Zvfhmin 两种定义与 Zvbb 已实现；Zvkt 延迟抽样仍不等于合规证明。
CPU退休、VS/FS、MMU/PMP和一致性属于宿主集成，不计为VPU缺指令。

硬件未变，沿用 M56 宿主公共/计算顶层 **3.300ns 条件预算**；
默认独立版沿用 M55 的3.292/3.232ns。没有新综合或新器件时序通过声明。
预算排除DSP影响端点、未布局布线、未按ZU15EG-2校准，不是STA/SDF；
**当前实际300MHz仍待Vivado**。M53本地结果只适用于旧RTL。

```bash
python3 scripts/verify_m57.py
python3 scripts/verify_m57.py --check-only
```

前者执行本轮新矩阵，后者核对当前证据。需要保留的M55/M56工具和证据，
不在此入口静默下载或重建。旧文档原文保存在archive/m56/source，旧receipt不改写。
没有Orbital联编、Linux驱动、bitstream、板上程序或完整V/RVA23/Zvkt声明。
'''
    (out/'evaluation.md').write_text(text)
    sources['reports/m57/evaluation.md'] = sha(out/'evaluation.md')
    d = dict(status='PASS', milestone=57, hardware_changed=False, baseline=previous, families=dict(Counter(r['family'] for r in entries)),
             canonical_encodings=len(entries), missing_catalog_entries=[], expanded_memory_forms=310, prior_forms_without_success=12,
             new_spike_commands=differential, new_policy_commands=policy_commands, new_DUT_executions=True, reused_unchanged_default_models=True,
             runs=records, runtime_negative_controls=run_negatives, catalog_negative_controls=catalog_negatives,
             full_v=False, full_rva23=False, zvkt_claimed=False, passes_300MHz=None, passes_500MHz=None,
             source_sha256=sources, artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(d, indent=2)+'\n')
    check(d)
    print('PASS M57 ISA audit', differential, 'Spike commands;', policy_commands, 'policy commands;', len(artifacts), 'bound artifacts')


if __name__ == '__main__':
    main()
