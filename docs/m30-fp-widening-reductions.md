# M30：精确FP32→FP64宽化求和归约

新增RVV 1.0的 `vfwredosum.vs`、`vfwredusum.vs`。支持e32/m1、m2、m4、m8、mf2，源FP32、seed和结果FP64；五种合法frm。unordered使用规范允许的确定顺序折叠。没有对FP16、FP64→128或普通宽化转换指令作支持声明；VPU仍为单指令容量、部分RVV。

## RAM与浮点流水

源地址和提取宽度保持SEW32，seed/累加器/写回为64位。共享FloatingPointLane新增内部widenAdd模式：A走已有FP32规格化与精确recoded提升，B走FP64 recode，复用FMA加法和FP64最终舍入。没有先把seed截成FP32，也没有FP32中间舍入；sNaN保留至有效加法，NV由运算产生。复用现有RAM、累加器、流水状态与寄存器，无新增DSP、RAM端口或整组快照；普通FP时延保持M29。

seed和目的各EMUL1，故m8源仍合法，且目的允许与源或mask重叠；两个源seed/data因不同EEW不得共享物理寄存器，包括分数LMUL。目的仅写低64位、tail保留。VL0完全不写目的；VL>0但无有效元素，原样复制FP64 seed，保留sNaN/qNaN负载和-0，不产生新flags。版本与fflags在完成握手才发布，取消丢弃私有结果。保留frm、SEW不支持、非零vstart、对齐和masked源v0在VL0也检查。

Monitor ABI1.0，ID0x3001/caps0x3ffff，bit17表示宽化FP归约，保留已有能力位。

## 组合链优化

AVL/gather的低8位边界比较改为四个2位less/equal与平衡布尔组合，高56位非零仍直接返回false，减少该比较的carry链。独立SAT miter证明所有64位输入、所有8位limit与原数学比较等价；没有增加状态或周期。该证明不等于整个ISA/流水形式证明。

## 验证与性能

SoftFloat参考通过f32_to_f64再f64_add独立计算，7组新已知答案锚点验证该路径，原52组锚点保留。混合精度lane1292组、42次flush/reset完整RTL通过；98组RTL/映射通过。完整向量1664条命令，其中合法442、非法194、取消22；覆盖5种类型、NaN/无穷/±0/子正规/舍入边界、seed高位、顺序消去、全masked原位复制、VL0、每个源组位置的混合EEW seed别名、v24..v31、目的别名/tail、保留编码、背压以及fflags/版本不提前提交，并逐条回读32寄存器。

266条smoke当前RTL/映射逐项结果、flags与周期一致；无FP/16位切分版负向检查拒绝新FP编码。39条混合向量序列覆盖新宽化FP→普通FP/INT及compress/gather，当前RTL/映射通过。原6811组FP、5021组转换本轮重新运行；原220组性能结果与周期保持M29。公开SpinorVpu并发monitor流量下，访存279组RTL及119组RTL/映射和两类新归约、取消恢复、tail及非法seed别名通过；详见报告的本轮覆盖范围。

归约仍为串行反馈。e32/m8、VL32、RNE且无完成背压时，32个有效元素1229拍，包含命令与准备开销，不代表每拍执行一个元素或多向量指令并行。

## 固定云端参考

| 顶层 | 50ps/段 | 100ps/段 | 200ps/段 |
|---|---:|---:|---:|
| SpinorVpu | 2.700ns | 3.300ns | 4.577ns |
| LishiVpuMemory | 2.627ns | 3.277ns | 4.577ns |

固定100ps/段及原M25家族权重下均≤3.333ns，余量分别0.033/0.056ns。未布局布线或按ZU15EG-2校准，DSP相关端点、hold、时钟树、RAM写、IO与SDF未覆盖，物理300/500MHz通过仍为null。200ps档不满足300MHz周期。

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| SpinorVpu | 18344 | 12300 | 9 | 32 | 6 |
| LishiVpuMemory | 16146 | 10926 | 9 | 32 | 6 |

RAM另消耗器件LUT，不是BRAM块数；全局映射变化不等于新增功能的独立成本。除FloatingPointLane外的8个数值/RF/LSU/host单元RTL保持M29的SHA。

完整证据见[报告](../reports/m30/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m30.py`、`python3 scripts/package.py --milestone m30`。后续继续宽窄整数、FP转换和访存模式，实际Orbital/Linux接入尚待完成。
