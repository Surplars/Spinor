# M25：RAM gather与标量广播

新增vrgather.vv/.vx/.vi、vrgatherei16.vv。继续完善VPU本体，仍为VLEN128/ELEN64、单条指令容量的部分RVV，未接Orbital或Linux，不声明完整V/RVA23。

## 语义与实现

支持正常22种SEW/LMUL；EI16索引按EEW16、EMUL=(16/SEW)*LMUL计算，e8/m8因索引EMUL16而按规范报非法。索引可访问VL之外、VLMAX之内的数据，超VLMAX补0。vx保持完整64位索引，vi为无符号5位；支持mask、vstart恢复和tail/inactive保留。

目的不得重叠数据或索引组，索引按自己的EMUL对齐；不同EEW的索引/数据源不能读同一物理寄存器，执行mask与v0数据/索引源的双EEW别名同样检查。同EEW的两个源可以别名，非masked的源v0与目的v0可使用。非法检查在VL0仍执行。

没有新增状态或扩大状态宽度。复用readB/captureB读取索引，a操作数暂存完整索引，slideAddress阶段做高位OR和8位比较、数据RAM地址选择，再经原整数move流水和tag写回。索引组计数由5输入位常量表计算，在FP版译码阶段寄存后再检查几何。VLMAX沿用nextVl私有暂存。

vx/vi首次取源后用已有b寄存器缓存广播值，仅新增一个valid位；后续元素不重复读RAM，零值广播也缓存。正常矢量索引每个有效元素两次RAM读取，广播源至多读取一次；不增加整组快照、读端口、RF或DSP。所有写入仍到候选RAM，完成握手才发布版本，flush撤销。

## 验证

独立Python参考从不可变全源组数组按数学索引取值，以索引字节数推导EMUL占用，不复制RTL的常量表或高位/低位比较实现。完整RTL 3675条命令，非法700、撤销136，覆盖22种类型、四种编码、跨行、重复索引、VL/VLMAX边界、所有8位索引值、64位高位索引、EI16的256/257与高位、独立对齐及部分组重叠、mask/vstart、VL0、完成背压与CSR保持。逐条检查32寄存器和版本。

404条smoke在RTL和映射网表功能、异常、撤销及周期一致，覆盖8种类型；无FP和16位切分版另通过smoke。广播基准的周期上限检查防止退回逐元素重复RAM读取。

旧滑移5576、索引生成1674、前缀掩码2888、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及旧向量789重新通过RTL。19条INT/FP/归约/滑移/gather交替序列通过RTL/映射，检查新模式与缓存不会泄漏到旧操作。原220组性能结果与周期和M24一致。

物理访存254组RTL通过；公开SpinorVpu在monitor流量下254组RTL及94组RTL/映射通过，末尾执行四类gather、源/索引重叠非法、超大索引、取消，并保留旧mask/index/slide检查。逐访存请求和周期与M24一致。Monitor ABI1.0，ID0x2501/caps0x3fff，bit13表示gather。

9个数值/RF/访存/CPU边界单元RTL按SHA确认未变，复用已绑定单测及局部证明；增量器组合证明重新执行以绑定当前源码。旧完整顶层的映射证据没有冒充当前网表结果。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M24 SpinorVpu | 17826 | 11983 | 9 | 32 | 6 |
| M25 SpinorVpu | 18109 | 11992 | 9 | 32 | 6 |
| M24 LishiVpuMemory | 15564 | 10609 | 9 | 32 | 6 |
| M25 LishiVpuMemory | 15755 | 10618 | 9 | 32 | 6 |

Yosys xcup未布局映射；表中是逻辑LUT，RAM另占器件LUT。RAM为LUTRAM，不是BRAM数量。

## 条件时序

| 每段连线假设ps | M24公开ns | M25公开ns | M25计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.718 | 2.791 | 2.791 |
| 100 | 3.368 | 3.391 | 3.391 |
| 200 | 4.668 | 4.591 | 4.591 |

100ps档公开顶层3.391ns，300MHz周期3.333ns的算术余量-0.058ns；路径vpu.vpu.unit.r32.sAdjustedExp[0]到vpu.vpu.unit._r32_io_out[22].D。计算/访存封装3.391ns。保持同一权重及RapidWright家族参考，基线冻结图恢复后校验SHA。FP32仍为参考最慢路径，新增gather没有取代它。

没有布局布线、-2校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，没有器件STA/SDF、WNS或Vivado。300/500MHz通过仍为null，不能继承旧M5物理结果，也不能把映射变化解释成确定的Fmax变化。

## 范围与复现

make bootstrap；python3 scripts/verify_m25.py；python3 scripts/package.py --milestone m25。receipt.json绑定源码、RTL、网表、测试台、冻结基线和报告。后续继续compress、宽窄/定点、FP归约及访存模式。旧普通算术/滑移的v0数据源与执行mask双EEW别名约束尚未统一，旧正向回归不构成这些编码的架构合法性证明；该已知限制列入ISA矩阵。实际Orbital接入、VM/PMP/一致性与Linux上下文仍未完成。未修改Valence，未调用Verilator。
