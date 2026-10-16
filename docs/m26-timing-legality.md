# M26：FP流水与云端门槛

本轮完善保留编码与时序，没有增加指令种类。工具保持Chisel7.16.0、Mill1.1.7、Yosys xcup映射、Icarus功能仿真、Yosys SAT局部证明、SoftFloat数值参考及RapidWright家族延迟参考。

## 数据通路

StagedRound在rounded significand之后寄存修正指数、fraction及overflow/underflow/inexact，再封装特殊值。其done由第5相位推迟到第6相位，拥有者保持输入到done。

FP lane新增StagedIeeeUnrecode，将recoded到IEEE的指数、非规格化移位距离及有效数先寄存，下一拍再做移位、格式选择和canonical NaN封装。flags在同一owner下先保存，tag保持；flush清除owner，旧的中间寄存器不会单独产生valid。转换级相对固定HardFloat进行任意recoded位、capture/hold的局部有界等价证明。

FMA族（含add/sub/mul）和DIV/SQRT每有效元素增加2拍；整数转FP因共享rounder增加1拍；FP比较/分类/符号、FP转整数和整数执行周期保持。容量仍是一条指令，新增级没有使FP吞吐变成每拍一元素。

index递增和mask字节推进使用已有ParallelIncrement；5位字节推进仍能产生128终止值，不截断成0。组合等价检查覆盖5/8/32/55/109位及地址/配置运算；元素和mask字节周期不增加。

## 保留编码

依RVV 1.0的源EEW约束，一个物理向量寄存器不能为同条指令提供不同EEW的源。执行mask v0是EEW1；masked指令将v0同时作为SEW数据源保留，归约seed也在此约束内。masked store v0同样不合法。检查在任何VL/vstart提前结束之前执行。

Python算术、FP、滑移、归约和访存参考同步修正。新增独立编码表检查INT、FP、乘除、归约、滑移的两类数据源，包含VL0、全mask关闭、vstart越过VL；逐条读取32寄存器，核对版本及CSR保持、完成背压。合法零字段反例防止误伤FP单目选择字段、scalar寄存器编号和EEW1 mask源。完整旧mask/viota数值测试继续覆盖源v0的合法masked执行。

## 固定验收门槛

`scripts/check_timing_gate.py`要求公开SpinorVpu及LishiVpuMemory在固定100ps/段连线假设、原RapidWright家族权重和100ps setup下，预算均≤1000/300ns。冻结M25网表按SHA恢复；改权重、漏掉顶层、输入网表变更或任一超预算都会中止交付。

| 顶层 | 50ps/段 | 100ps/段 | 200ps/段 |
|---|---:|---:|---:|
| SpinorVpu | 2.700ns | 3.300ns | 4.500ns |
| LishiVpuMemory | 2.609ns | 3.209ns | 4.409ns |

100ps档两种顶层满足云端条件门槛；公开顶层只余0.033ns。200ps档不满足3.333ns。它是未布局图上的显式连线敏感性预算，不是时序仿真、器件STA或实际Fmax。未校准ZU15EG-2，DSP相关端点排除；无时钟树/hold、RAM写或I/O检查。物理300/500MHz的通过字段仍为null。

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| SpinorVpu | 18314 | 12300 | 9 | 32 | 6 |
| LishiVpuMemory | 15922 | 10926 | 9 | 32 | 6 |

RAM为LUTRAM，还消耗器件LUT，不是BRAM数量；RF容量、端口数未增加。Monitor ABI1.0，ID0x2601/caps0x3fff。

完整结果、局部证明和SHA见[报告](../reports/m26/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m26.py`、`python3 scripts/package.py --milestone m26`。仍为部分RVV，尚未接实际Orbital/Linux。后续继续compress、宽窄整数、FP归约及更多访存模式。
