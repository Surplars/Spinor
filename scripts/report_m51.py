#!/usr/bin/env python3
"""Bind the unchanged M50 hardware evidence to the new LSU and GSIM checks."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
MEMORY=['SpinorStandard-compact-rtl','SpinorStandard-full-rtl','SpinorIntegerDeep-compact-rtl','SpinorStandard-compact-mapped']
BENCH=['SpinorStandard-bounded','SpinorStandard-compact-memory']
def check(d):
    assert d['status']=='PASS'
    for key in ['source_sha256','artifact_sha256','external_tool_dependency_sha256','external_source_sha256','sha256']:
        for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
def baseline():
    path=ROOT/'reports/m50/receipt.json';d=json.loads(path.read_text());check(d)
    count=sum(len(d[k]) for k in ['source_sha256','artifact_sha256','external_tool_dependency_sha256'])
    r=dict(status='PASS',baseline=str(path.relative_to(ROOT)),receipt_sha256=sha(path),checked_files=count,hardware_changed=False,
           conditional_reference_gate=d['conditional_reference_gate'],resources=d['resources'])
    (ROOT/'build/m51-base-check.json').write_text(json.dumps(r,indent=2)+'\n');return d,r

def main():
    prior,base=baseline();memory={};bench={};external={};artifacts=[ROOT/'reports/m50/receipt.json',ROOT/'build/m51-base-check.json',ROOT/'reports/m51/oversized-mapped-cancel.json']
    for group,names,root in [(memory,MEMORY,'spike-memory'),(bench,BENCH,'gsim-benchmark')]:
        for name in names:
            path=ROOT/'build'/('spike-memory-bounded' if name=='SpinorStandard-compact-mapped' and group is memory else root)/name/'results.json';d=json.loads(path.read_text());check(d);artifacts.append(path)
            artifacts += [ROOT/p for p in d['artifact_sha256']]
            if group is memory:
                assert d['canonical_memory_encodings']==58
                assert len(d['legally_exercised_encodings'])==(7 if d.get('bounded') else 58)
                assert d['negative_control']=='CORRUPT_TL_READ_REJECTED'
                group[name]={k:d[k] for k in ['commands','canonical_memory_encodings','segment_forms','memory_faults','illegal_commands','summary','negative_control','legally_exercised_encodings']}
            else:
                assert d['negative_control']=='WRONG_RF_BIT_REJECTED'
                group[name]={k:d[k] for k in ['commands','cycles','output_checks','times','gsim_cpp_compile_seconds','median_wall_speedup','limitations']}
    for rel in ['build/spike-memory-model/results.json','build/gsim-model/results.json','build/gsim/SpinorStandard/results.json']:
        path=ROOT/rel;d=json.loads(path.read_text());check(d);artifacts.append(path)
        artifacts += [ROOT/p for key in ['artifact_sha256','sha256'] for p in d.get(key,{})]
        external.update(d.get('external_source_sha256',{}))
        if 'binary' in d:external[d['binary']]=d['binary_sha256']
    out=ROOT/'reports/m51';out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,d in bench.items():
        ts=d['times'];rows.append(f"| {name} | {d['commands']} | {d['cycles']:,} | {statistics.median(ts['icarus_wall_seconds']):.3f} | {statistics.median(ts['gsim_wall_seconds']):.3f} | {d['median_wall_speedup']:.1f}x | {d['gsim_cpp_compile_seconds']:.2f} |")
    text='''# M51：Spike 访存差分与 GSim 后端测量

本轮扩展验证工具，没有修改 VPU 数据通路或指令支持。VLEN128/ELEN64、单 lane、单指令容量和 monitor 实现 0x5001 保持；这不是完整 RVV 或 Orbital 整核集成。

## 独立访存参考

新的适配器链接 M50 固定提交的未修改上游 Spike，普通物理 RAM 通过回调提供，失败地址范围由测试台注入。实际指令解码、访存、CSR 和异常语义均来自 Spike；适配器只运输输入和状态。原 M50 算术适配器与参考二进制保持不变。

从上游 MATCH/MASK 提取全部 58 种基础向量访存编码。标准全矩阵遍历 22 种合法 SEW/LMUL 配置；SEW32/LMUL1 额外展开 NF1..8 分段形式，共 310 种编码几何形式，包含应拒绝的组越界组合。原生 RTL 每种基础编码都有合法执行点；综合网表另用 7 种代表编码、26 条命令的有界矩阵，保持每条命令的完整 RF/RAM/CSR 与错误检查，不把子集称为全部 58 种网表覆盖。AVL 主要为 3/4，并非全 VL/操作数/别名/边界组合穷举。

每条命令通过真实 context 口比较全部 32 个向量寄存器、8 KiB RAM、VL/vtype/vstart/vxrm/vxsat 和浮点预设的 frm/fflags。TL 普通 RAM 模型施加 A 背压与变化的 D 延迟，检查自然对齐、大小、掩码、源 ID、opcode 和事务排空。访存允许架构规定的前缀进度，完成结果及错误状态在反压下须保持。

覆盖单位步长、正/负/零跨距、有序/无序索引、掩码、整寄存器和 FOF 访存；注入首/后续元素访问错误并保留实际状态重试，检查 FOF 缩 VL、非零 vstart 恢复、未对齐及物理窗口外错误。当前独立 Spike 故障点集中在分段的第一个字段，未穷举每个字段错误。原 M50 定向验证仍提供其他分段字段前缀和中止检查。没有 VM/PMP、缓存一致性、真实 MMIO 或异步中断 Spike 联合验证。

| 矩阵 | 命令 | 内存错误 | 非法命令 |
|---|---:|---:|---:|
'''
    for name,d in memory.items():text+=f"| {name} | {d['commands']} | {d['memory_faults']} | {d['illegal_commands']} |\n"
    text+='''
开发期一次可选的完整网表访存矩阵超过本轮运行预算，已中止，隔离的测试夹具随后完整恢复；该中止记录不计入正常通过，也不作为硬件失败。上表网表一行仅指实际完成的有界子集。

每组另将 TL 读回复的数据位故意翻转，必须由原 RF 比较逻辑检出，记录为负控制通过。正常测试与故意失败分开记录。

## GSim 速度与验证方式

使用与 Valence 相同的固定 GSim 提交 `93b8cd23edd3228807c4f2a08c19c3936a463cb2`、本地 Clang19.1.7、单线程。直接导出同一生产 Spinor 顶层的 CHIRRTL，编译为 C++。GSim 词法器把合法 FIRRTL 信号名 `old` 当作保留字，因此仅在仿真输入中重命名该信号及引用；保留原始 CHIRRTL、规范化文件与散列，上游 GSim 和硬件源码未改。

测试先由 Icarus 执行真实 SV 驱动，并独立对照 Spike。随后 GSim 回放完全相同的逐周期输入，比较每个上升沿的公共输出；有效载荷按 valid 限定，只跳过 Icarus 明确为 X/Z 的未定义位。算术测试原本未驱动、且不使用的 TL A ready 在两边都固定为 0。记录来源 receipt 及回放文件散列，防止旧回放混用新测试。额外破坏一个已知 RF 输出预期位，要求 GSim 检查器失败。

这已验证新后端的周期行为；当前是回放适配器，尚未替换所有自适应 SV 驱动，也不是将 Orbital 接入 Spike。Spike 是参考模型，GSim 是执行 DUT 的仿真后端，两者承担不同工作。

三次运行的中位数，秒：

| 用例 | 命令 | 周期 | Icarus 总耗时 | GSim 总耗时 | 总耗时比 | C++ 编译 |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(rows)+'''

GSim 总耗时包含进程启动、回放文件装载和所有输出比较；内部 sim_seconds 另排除了文件装载。Icarus 执行 SV/Spike 状态检查，GSim 执行逐周期输出比较，两边检查开销不同，因此这些是当前测试的后端测量，不能当作所有工程的通用加速比。C++ 编译、Mill 导出、GSim 代码生成和首次工具构建不计入运行倍数。短测试需考虑编译成本；长回归可复用模型。

GSim 接受 CHIRRTL，不能直接执行现有 SystemVerilog 测试台、FPGA 原语映射网表或 SDF。保留 Icarus 网表检查；功能仿真加速不提供 FPGA 物理时序。

## 硬件证据与复现

重新核验 M50 的全部 6,899 项源码、产物及外部工具散列。硬件没有变化，保留 M50 资源结果与固定 M25 权重、100ps/link 的条件门槛：公共顶层 3.292ns，≤3.333ns。该模型排除了 DSP 影响端点，未布局布线、未按 ZU15EG-2 速度等级校准。实际 300/500MHz STA 仍未知；本轮没有 Vivado/SDF 或真实板级时序结果。

在已有 M50 云端构建产物上运行：

```bash
python3 scripts/verify_m51.py
```

首次环境先按 M50 文档执行 bootstrap/verify-m50，以建立锁定的工具、RTL、网表与独立参考产物。新依赖仅解包到 tools；不修改 Valence，不安装系统包。新入口也可单独运行：

```bash
python3 scripts/bootstrap_spike_memory.py
python3 tests/test_spike_memory.py --compact
python3 scripts/bootstrap_gsim.py
python3 scripts/emit_gsim.py
python3 tests/benchmark_gsim.py
python3 tests/benchmark_gsim.py --suite memory --case compact
python3 scripts/report_m51.py
```

仅复核已有产物：`python3 scripts/verify_m51.py --check-only`。报告 receipt 绑定新增测试、输入/输出、模型及二进制，并通过固定 M50 receipt 绑定原有硬件证据。完整 GSim 驱动迁移和实际 Orbital/SoC 接入仍需继续。
'''
    doc=out/'evaluation.md';doc.write_text(text);artifacts.append(doc)
    sources=[*sorted((ROOT/'src').rglob('*.scala')),ROOT/'scripts/bootstrap_gsim.py',ROOT/'scripts/bootstrap_spike_memory.py',ROOT/'scripts/emit_gsim.py',ROOT/'scripts/report_m51.py',ROOT/'scripts/verify_m51.py',ROOT/'tests/benchmark_gsim.py',ROOT/'tests/spike_memory_adapter.cc',ROOT/'tests/spike_memory_tb.sv',ROOT/'tests/test_spike_memory.py',ROOT/'tests/test_spike_memory_mapped.py',ROOT/'third_party/gsim-reference.json']
    result=dict(project='Spinor',milestone='M51',status='PASS',hardware_changed=False,base_evidence=base,memory=memory,benchmarks=bench,
      monitor_implementation='0x5001',passes_300MHz=None,passes_500MHz=None,full_V=False,actual_Orbital_integrated=False,
      external_tool_dependency_sha256=external,source_sha256={str(x.relative_to(ROOT)):sha(x) for x in sources},artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in sorted(set(artifacts))})
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS M51 report',len(memory),'LSU groups',len(bench),'backend comparisons',len(result['artifact_sha256']),'artifacts')
if __name__=='__main__':main()
