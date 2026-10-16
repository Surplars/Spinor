# ZU15EG-2 向量原型 M1 开源评估

**状态：整数向量子集原型；完整 RVV/RVA23、Valence 整核接入、300/500 MHz 和 bitstream 均未完成。**

构建：Mill 1.1.7，Scala 2.13.18，Chisel 7.16.0，生成的 RTL 标识 firtool 1.160.0。

## 资源映射

Yosys `synth_xilinx -family xcup`，OOC，无 IOB/时钟缓冲；以下是映射单元数量。

| 候选 | 逻辑 LUT | FF | RAM32M16 | RAMB36E2 | 逻辑 CARRY4 |
|---|---:|---:|---:|---:|---:|
| IntegerLaneBaseline | 1,690 | 218 | 0 | 0 | 44 |
| IntegerLaneSplit | 1,181 | 1,111 | 6 | 0 | 28 |
| IntegerLaneSplit16 | 1,295 | 1,328 | 6 | 0 | 30 |
| VectorPrototype | 2,371 | 2,103 | 16 | 0 | 37 |
| VectorPrototype16 | 2,470 | 2,317 | 16 | 0 | 39 |
| VectorPrototypeFlops | 5,054 | 6,322 | 6 | 0 | 37 |
| VectorPrototypeBram | 2,510 | 2,228 | 6 | 2 | 37 |
| ValenceBoundary | 215 | 70 | 0 | 0 | 0 |

相同流水、接口、快照周期下，自动 RAM 版本比 FF 版本减少 **53.1% 逻辑 LUT、66.7% FF**。

RAM32M16 是分布式 RAM，每个使用 8 个存储 LUT；它不是免费的独立 BRAM。
自动 RAM 候选的逻辑 LUT + 存储 LUT 未打包合计约 2,499 个 LUT 位置。
该合计不包含 LUT 双输出合并、slice 打包、布线和原生 carry 打包优化，不能当作 Vivado 最终占用。
CARRY4 是开源映射中的逻辑单元；ZU15EG 的实际 CARRY8 打包未建模。

强制 BRAM 实验只改变 VRF 存储提示，使用 2 个 RAMB36E2；在小容量下周边逻辑成本没有改善。
BRAM 映射仅作资源实验，没有以原生器件 RAM 模型完成映射后功能/时序验证。

## 路径分析

**以下数字不是 ns，也不是 MHz。**只有映射逻辑图的寄存器/存储边界间单元跳数；
RAM 读和 CARRY 每个计为一个不带校准延迟的单元。未计入器件 -2 速度模型、连线、setup/hold、时钟偏差。

| 候选 | 最长数据路径跳数 | 最长控制路径跳数 | 最大非时钟扇出 |
|---|---:|---:|---:|
| IntegerLaneBaseline | 19 | 2 | 279 |
| IntegerLaneSplit | 11 | 4 | 185 |
| IntegerLaneSplit16 | 8 | 5 | 170 |
| VectorPrototype | 12 | 8 | 305 |
| VectorPrototype16 | 8 | 8 | 305 |
| VectorPrototypeFlops | 12 | 9 | 305 |

入口信用和结果 FIFO 把 split 数据通路从全局停顿使能中分离；代价是 FIFO 及额外控制。
16-bit 切分减小算术级进位路径，但会增加寄存器和延迟，仍不保证 500 MHz。
**300 MHz / 500 MHz 均为待验证目标；本轮不输出伪造的 Fmax/WNS/TNS。**

## 功能证据

- 三种整数 lane：每种 6,340 个刺激周期，覆盖所有已实现算术操作、四种 SEW、随机背压/flush，
  并以独立 Python 算术模型逐结果和逐拍检查；每种均拒绝注入的错误结果。
- 四种向量原型：每种 471 条真实编码命令、956 次上下文读检查，覆盖配置、mask/tail、别名、非法指令和撤销。
- 自动 LUTRAM 映射后的 VectorPrototype 网表通过同一组 471 条命令/956 次读检查。
- 候选 Valence 同钟域边界：128 次事务、171 次陈旧完成拒绝、640 个完成背压周期。
- 这些是原型子集测试，不是完整 ISA 合规测试，也没有执行 Valence CPU/Linux 程序。

## 指令周期

每种 SEW 运行相同的 64 条依赖 vadd.vv，VL=VLMAX、LMUL1，无完成背压；包含当前接口/快照/提交开销。

| 候选 | SEW8 | SEW16 | SEW32 | SEW64 |
|---|---:|---:|---:|---:|
| VectorPrototypeBaseline | 46.0 | 30.0 | 22.0 | 18.0 |
| VectorPrototype | 51.0 | 35.0 | 27.0 | 23.0 |
| VectorPrototype16 | 52.0 | 36.0 | 28.0 | 24.0 |
| VectorPrototypeFlops | 51.0 | 35.0 | 27.0 | 23.0 |

深流水增加短向量启动延迟。不能只比较目标 MHz；必须比较周期 × 实际周期时间，
以及未来加入 LSU 后的带宽和访存停顿。当前每两拍最多发射一个元素，不是每拍处理完整 64-bit SIMD 字。

## 交付和复现

- [源码与架构说明](../README.md)
- [机器可读证据及 SHA-256](receipt.json)
- `make verify` 使用 Mill 重新导出、仿真、映射、分析和生成报告。
- `make package` 打包源码、RTL 和报告，不包含约 714 MiB 的工具下载或本地凭据。

尚未实现的内容见 [架构合同](../docs/architecture.md)，不得将本报告中的低资源数字外推为完整 RVA23 VPU 的占用。

DSP 数据表答复：标准电压且使用全部内部寄存器时，-2 的 DSP48E2 指标为 775 MHz，-3 为 891 MHz；
它们均不等于完整 VPU 的最高频率。[AMD DS925](https://docs.amd.com/r/en-US/ds925-zynq-ultrascale-plus/DSP48-Slice-Switching-Characteristics)
