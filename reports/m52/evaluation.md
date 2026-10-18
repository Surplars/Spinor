# M52：直接 GSim/Spike 差分与访存边界验收

本轮把 GSim 从 M51 的逐周期输入回放推进为直接、自适应的生产顶层测试。C++ 驱动通过公开端口初始化/读取寄存器，根据实际握手提交命令、等待完成、返回普通 RAM 的 TileLink 回复；没有使用 Icarus 轨迹驱动 GSim，也没有从 DUT 输出生成期望值。全部架构期望来自锁定的、语义未修改的上游 Spike；同一独立参考语料可在四个预设间复用，复用前检查源码、模型、输入和产物散列。

硬件数据通路、指令支持、RAM、接口及 monitor 实现 0x5001 均未改变。仍是 VLEN128/ELEN64、单 lane、单向量指令在途；整数元素可流水重叠。新增的是可扩展验证能力，不是多发射、乱序或实际 Orbital 接入。

## 已完成矩阵

| 预设 | 算术命令 | 基础访存命令 | 扩展边界命令 |
|---|---:|---:|---:|
| SpinorStandard | 9793 | 3154 | 9564 |
| SpinorDeep | 1819 | 718 | 9564 |
| SpinorInteger | 5319 | 3154 | 9564 |
| SpinorIntegerDeep | 999 | 718 | 9564 |

另有标准配置 340 条代表边界命令由独立 SV 驱动和直接 GSim 驱动分别完成，输入事件、独立期望 CSR、32 行寄存器和 8 KiB RAM 逐项一致。两个测试台采用各自的相位和总线回复调度，因此不把不同总周期当作微架构性能改进。

直接 GSim/Spike 正常矩阵共 **64,270 条命令**。每条命令检查完整 32 个向量寄存器和已实现 CSR；访存矩阵还比较全部 8 KiB RAM。驱动检查命令/上下文仲裁、完成身份和高位 token、背压保持、算术提前发布、访存状态、TL 元数据/掩码/自然对齐、物理窗口和总线排空；非法指令不得发出 RAM 请求。含规范矩阵和 SV 交叉检查，共 **79 次故意错误检出检查**，覆盖 token、CSR、RF、RAM、读回复和故障地址，要求正例先通过且负例由相应比较器明确拒绝。

固定上游目录的 213 种整数、101 种浮点、3 种配置和 58 种基础访存编码，共 **375 种基础编码**，均有标准预设直接执行成功的样本，见 [逐项覆盖](canonical-coverage.csv)。分段字段数和 SEW/LMUL 变体另行展开；此目录统计不是全部操作数、保留编码、异常/重启组合的合规百分比，也不包括 RVA23 的额外扩展。

## 访存边界

扩展矩阵每个预设 9,564 条命令，包含：

- 单位步长 load/store 和 FOF：SEW8/16/32/64、NF2..8，每个字段在元素 0 与后续元素出错，保留实际状态重试。
- 跨步及四种 ordered/unordered indexed load/store：SEW32、独立 8 位索引、NF2..8，每个字段的首/后续元素故障。
- 掩码关闭全部元素、跳过故障元素、元素 0 被屏蔽后的首个有效元素错误，以及非零 vstart 恢复；包括分段 FOF 的部分字段前缀和缩 VL。
- 58 种基础访存编码遍历 22 种合法 SEW/LMUL，AVL 为 0、VLMAX、VLMAX+1；正/负/零 stride、rs2=x0、整组/mask 的 vill 与 vstart 边界、索引重叠及部分保留形式。

算术差分沿用 TU/MU 保留策略及合法 frm。Spike 默认 vstart_alu=false，算术执行使用 vstart=0；非零算术重启和 flush 继续由已有独立定向验证覆盖。

这仍不是所有地址、别名、掩码、数据与中断相位的穷举。没有异步中断的 Spike 联合模型，也没有 VM/PMP、真实 MMIO 或缓存一致性验证。

## 模型对保留编码的选择

规范禁止同一向量寄存器以不同 EEW 提供多个源。锁定 Spike 对某些 indexed store 的这种保留编码仍允许执行；小型可复现探针分别在 VL0 和 VL3 记录该选择。本轮没有更改 DUT 来追随保留编码的模型行为，也没有忽略合法指令中的差异。

该保留族从严格 Spike 输入中单列，另用 [冻结规范摘录](../../docs/references/m44-indexed-v1.0.txt) 的独立拒绝策略测试：每个预设 **72 个场景、216 条命令**，覆盖单字段及分段、不同 EEW、源组不同位置、VL0/非空和非零 vstart。要求非法完成、完整 RF/RAM/vstart 保持、零 TL 请求。四预设均通过；此项明确不标为 Spike 一致性结果。

## 时序、资源与范围

M50/M51 的源码、生成 RTL/网表、参考模型和原有执行证据重新按散列核对，硬件 Scala 文件集合及字节均一致。原 RTL/网表、SoftFloat、局部证明和编译器程序证据按相同输入复用，没有重复进行无关的长回归。

固定 M25 权重和 100ps/link 的云端条件门槛本轮重新检查：SpinorVpu 与计算/访存顶层均 **3.292ns ≤ 3.333ns**。四预设资源与原预算保持；标准版 23,206 逻辑 LUT、13,204 FF、9 DSP；整数版 12,737 LUT、6,322 FF、1 DSP，VRF 继续使用版本化 RAM。

模型排除 DSP 影响端点，未布局布线，未按 ZU15EG-2 速度等级校准，不是器件 STA/SDF。实际 300/500MHz 仍未知，旧 M31 的物理结果不能作为当前版本签核。

## 当前完成边界

目标配置下基础 V 的主要数据计算和访存编码已落地并有独立执行样本，后续应集中在架构审计、异常/重启和系统闭环。仍不能发布完整 misa.V 或 RVA23 声明：FP16/Zvfhmin、Zvbb、Zvkt 以及目标 profile 条件需单独实现/审计；Orbital 的真实退休、VS/FS/FCSR、上下文、地址保护/翻译和内存一致性尚未接入。ARM monitor 工具也不等于计算作业驱动。

GSim 直接差分现已可用于后续功能验证；现有 LLVM ELF 标量控制流适配器仍使用原测试平台，尚未整体迁移至 GSim，未运行真实 Orbital/Linux 程序。

## 复现

在已通过 M51 的 Linux x86-64 环境中：

```bash
python3 scripts/verify_m52.py
python3 scripts/verify_m52.py --check-only
```

首次环境先按 M50/M51 文档准备锁定的工具、模型、RTL、网表与证据。本轮为四预设生成独立目录，不改写 M51 的导出文件。直接驱动与参考语料都仅在源码、工具、输入和产物散列一致时复用。可单独运行：

```bash
python3 scripts/emit_gsim_m52.py --top SpinorStandard
python3 tests/test_gsim_spike.py --suite arithmetic
python3 tests/test_gsim_spike.py --suite memory
python3 tests/test_gsim_spike.py --suite edges
python3 tests/test_spike_memory_edges_rtl.py
python3 tests/test_gsim_reserved_eew.py
python3 scripts/check_spike_reserved_policy.py
```
