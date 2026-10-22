# ZU15EG-2 M2：RAM 寄存器组与参考延迟仿真

**当前为整数向量子集。未完成完整 RVV/RVA23、Valence 整核接入、真实器件时序和 bitstream。**

Mill 1.1.7 / Scala 2.13.18 / Chisel 7.16.0 / firtool 1.160.0；Yosys 0.70+16 和 Icarus 14.0。

## 本轮设计

- VLEN128、ELEN64；m1/m2/m4/m8/mf2/mf4/mf8，22 种合法 SEW/LMUL 组合。
- vstart、vxrm、vxsat、vcsr，以及只读 vl/vtype/vlenb；真实 vset* 编码及 x0 特殊规则。
- 每个架构寄存器有两个 RAM 版本，源读已提交版，结果写候选版；完成被接受时翻转 32-bit 版本表。
- 不保存整个 LMUL 寄存器组的 FF 快照；仅缓存 v0 和当前元素，撤销不清空 RAM。
- 当前单元素在途，是存储/提交正确性基线；整数乘除、浮点和 LSU 等仍待实现。

## 资源

Yosys `synth_xilinx -family xcup` 的 OOC 映射，无 IOB/时钟缓冲；不是 Vivado 布局后资源。

| 候选 | 逻辑 LUT | FF | 存储 LUT | RAM32M16 | RAM64M8 | RAMB36E2 |
|---|---:|---:|---:|---:|---:|---:|
| RamVector | 2793 | 1984 | 296 | 5 | 32 | 0 |
| RamVector16 | 2867 | 2193 | 296 | 5 | 32 | 0 |
| RamVectorFlops | 8800 | 10298 | 40 | 5 | 0 | 0 |
| RamVectorBram | 2938 | 2122 | 40 | 5 | 0 | 2 |
| VersionedRegisterFileRam | 80 | 38 | 256 | 0 | 32 | 0 |

同接口、同周期的 RAM/FF 对照：RAM 减少 68.3% 逻辑 LUT、80.7% FF。
RAM32M16、RAM64M8 各占 8 个存储 LUT；自动 RAM 总计 3089 个未打包逻辑+存储 LUT 位置。
这不含 slice 打包、双输出 LUT 合并或布线成本；CARRY4 是逻辑映射，不代表原生 CARRY8 打包。
强制 BRAM 只改变寄存器堆存储提示；该候选尚未做原生 RAMB36E2 模型的网表功能验证。

## 功能证据

- 双版本寄存器堆：4160 次事务、3295 次读检查、605 次随机原子提交。
- 三种 M2 RTL 和自动 LUTRAM 映射网表：各 789 条命令、2968 次上下文读检查。
- 覆盖 553 次向量运算、137 次 CSR、99 次配置、7 次撤销和 26 次非法操作。
- 每拍检查版本表在完成接受前保持不变；覆盖目的/源别名、mask/tail/prestart、分数组、完成背压及部分写后撤销。
- 独立 Python 算术/架构状态模型；属于原型子集检查，未做完整 ISA 合规或 Valence 核级仿真。

## 周期与代价

每项为 VL=VLMAX、LMUL1 的 64 条依赖 vadd.vv，无完成背压，包含接口/复制/提交开销。

| 候选 | SEW8 周期/条 | SEW16 | SEW32 | SEW64 |
|---|---:|---:|---:|---:|
| RamVector | 216.0 | 112.0 | 60.0 | 34.0 |
| RamVector16 | 232.0 | 120.0 | 64.0 | 36.0 |
| RamVectorFlops | 216.0 | 112.0 | 60.0 | 34.0 |

M1 的 32-bit 切分原型对应为 51/35/27/23 周期；M2 当前为单元素在途，因此更慢。
节省存储资源不代表提高吞吐；后续需重叠 RAM 访问、执行和候选写回，并保持同一提交协议。

## 参考时序仿真

**以下是未校准的假设延迟实验，仅覆盖整数 lane，不是整个 VPU 的时序仿真，也不是 AMD SDF/器件 STA。**
输入在时钟沿后 0.25 ns 发出；Icarus 事件仿真计入自定义 LUT/连线/CARRY/触发器/队列 RAM 延迟，
手工监视 setup/hold 和 RAM 写 setup。未包含位置、实际扇出、PVT、时钟树/偏差和器件速度文件。
时序违规只计数，不向寄存器注入 X；因此结果匹配且所有计数为零才记为该场景通过。

三个零延迟对照都通过；另用故意缩短 setup/hold 的独立刺激验证监视器能报错。
每个场景 1108 周期，含四种 SEW、20 种已实现运算、随机停顿和撤销。

| 假设（ns） | LUT | 连线 | 每 bit carry | CQ | setup | hold | RAM 读 |
|---|---:|---:|---:|---:|---:|---:|---:|
| assumption_A | 0.1 | 0.05 | 0.025 | 0.12 | 0.06 | 0.02 | 0.2 |
| assumption_B | 0.16 | 0.1 | 0.035 | 0.18 | 0.1 | 0.03 | 0.3 |

| 场景 | MHz | 候选 | 结果匹配 | setup / hold / RAM 写违规 |
|---|---:|---|---|---|
| assumption_A | 300 | IntegerLaneBaseline | 是 | 0 / 0 / 0 |
| assumption_A | 300 | IntegerLaneSplit | 是 | 0 / 0 / 0 |
| assumption_A | 300 | IntegerLaneSplit16 | 是 | 0 / 0 / 0 |
| assumption_A | 500 | IntegerLaneBaseline | 否 | 2 / 0 / 0 |
| assumption_A | 500 | IntegerLaneSplit | 是 | 0 / 0 / 0 |
| assumption_A | 500 | IntegerLaneSplit16 | 是 | 0 / 0 / 0 |
| assumption_B | 300 | IntegerLaneBaseline | 否 | 0 / 1 / 0 |
| assumption_B | 300 | IntegerLaneSplit | 是 | 0 / 0 / 0 |
| assumption_B | 300 | IntegerLaneSplit16 | 是 | 0 / 0 / 0 |
| assumption_B | 500 | IntegerLaneBaseline | 否 | 2 / 165 / 0 |
| assumption_B | 500 | IntegerLaneSplit | 否 | 146 / 7 / 0 |
| assumption_B | 500 | IntegerLaneSplit16 | 否 | 24 / 8 / 0 |

在 A 假设下，两种切分都通过 300/500 MHz；在 B 假设下，两种切分通过 300 MHz、500 MHz 出现违规及数据错误。
这说明结论依赖延迟假设；支持把 300 MHz 留作基线、继续优化 500 MHz 候选，不能推导真实 ZU15EG 的 Fmax。

## 映射路径（不带时间）

| 候选 | 数据路径单元跳数 | 控制路径跳数 | 最大非时钟扇出 |
|---|---:|---:|---:|
| RamVector | 12 | 10 | 305 |
| RamVector16 | 11 | 10 | 305 |
| RamVectorFlops | 13 | 11 | 1026 |
| VersionedRegisterFileRam | 4 | — | 224 |

这些仅为逻辑图跳数；RAM 读和逻辑 CARRY 都按单元计数，不能换算 ns/MHz。
整机 RAM 选择、CSR/地址控制路径尚未做参考延迟仿真。

## 复现与证据

- `make bootstrap`；`make verify-m2`；`make package-m2`。
- [机器可读证据与源/产物 SHA-256](receipt.json)
- [原始参考仿真结果](timing-reference.json)、[检查器故意违规对照](https://github.com/Surplars/Spinor/blob/63de85ede691ba438dcca9b34b0fd78d588f0878/archive/m2/reports/model-check.log)
- [设计合同](../../docs/architecture.md)、[M1 原始报告](../../archive/m1/reports/evaluation.md)
- 真实时序、最终 bitstream 仍需支持 XCZU15EG 的 AMD 实现工具；开源结果用于推进设计。
