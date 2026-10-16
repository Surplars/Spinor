# M25：RAM gather与广播

新增vrgather.vv/.vx/.vi、vrgatherei16.vv。保持单条指令容量、VLEN128/ELEN64、版本化RAM与现有整数lane；仍是部分RVV，尚未接入实际Orbital或Linux。

## 编码和边界

| 指令 | funct6 | funct3 | 索引 |
|---|---:|---:|---|
| vrgather.vv | 0x0c | 0 | vs1每个SEW位无符号元素 |
| vrgather.vx | 0x0c | 4 | 完整XLEN64标量 |
| vrgather.vi | 0x0c | 3 | 零扩展5位立即数 |
| vrgatherei16.vv | 0x0e | 0 | vs1每个16位无符号元素 |

目的活动元素i取数据源vs2的第index[i]元素；索引达到VLMAX时补0。VL只限制目的写入，不限制源读取。vx/vi把同一源元素广播到所有活动目的元素。支持mask与vstart，保留tail、inactive及vstart之前元素；合法完成清vstart。FP位模式按原样搬运，不产生FP异常标志。

普通数据源、目的与普通vv索引使用SEW/LMUL；EI16索引使用EEW16、EMUL=(16/SEW)*LMUL。索引组有独立对齐和占用，例如e8/m4需要m8索引组，e64/m8只需m2；e8/m8的EMUL16是保留编码，必须报非法。分数EMUL只占一个物理寄存器的低部。

目的不能重叠数据或索引组；不同EEW的两个源不能共享物理寄存器。同EEW源可别名。masked时数据/索引源不能与执行mask v0形成双EEW读取，目的不能为v0；非masked时可读取数据/索引v0，也可写目的v0。这些约束在VL0或vstart≥VL时仍检查。

例如VL=3、VLMAX=4、数据[10,20,30,40]、索引[3,1,4]，有效结果为[40,20,0]。SEW8下标量索引256仍越界，不能截成8位后读元素0；EI16索引256/257与SEW32/64高位索引同样保持精度。

## 微架构与吞吐

没有新增FSM状态。vv/ei16复用readB/captureB读取索引，在现有a寄存器保留完整值；slideAddress阶段通过高位OR及低8位比较判界，然后选择数据RAM行和位偏移。最后复用readA/captureA、整数move流水及tag写回。索引解析、判界和数据读取不连成一条大组合链。

EI16索引组计数由5位vtype常量表得到，在FP版译码阶段寄存后再做重叠与对齐检查。VLMAX复用nextVl私有暂存，kind=0不会把它提交为架构VL。目的先复制到候选版本；源均读已提交RAM，完成等待流水与RAM写排空，完成背压不发布，flush取消。

vx/vi第一次源读取后把结果保存在已有b操作数寄存器，只增加一个缓存有效位；后续目的元素直接送同一个值入lane。越界广播也缓存零。正常矢量索引每个有效元素读取索引与数据各一次；标量索引整个指令至多读取一次源元素。没有整组快照、新RF副本、读端口或DSP。

e8/m4、VL64、无掩码时，普通vv与EI16均470周期，vx/vi为153周期，包含握手、组复制与排空。标量广播首元素取源后，后续有效元素发射间隔2周期；普通有效索引路径7周期，越界省掉数据读取。周期基准检查广播的摊销收益，不能把这些周期数换算成已经通过的物理频率。

## 验证与限制

完整RTL3675条命令，覆盖四种编码、22种数据类型、700次非法和136次撤销；404条smoke覆盖8种类型，在RTL及映射中比较功能与周期。无FP和16位切分版各402条。参考模型先复制源数组，用完整Python数学索引选元素，以索引字节数推导组占用，不复刻RTL的EMUL查表和高位/低位比较。

检查所有32寄存器、版本与CSR，包含0..255索引、源tail读取、64位高位索引、EI16高位与256/257、索引EMUL独立对齐、分数/大组、跨行/重复索引、重叠非法、mask/vstart、完成背压与各阶段撤销。19条INT/FP/归约/滑移/gather交替命令、既有整数/FP与220组性能、TL/monitor继续回归。公开顶层末尾执行四类gather、取消、越界和非法数据/索引重叠。

Monitor ABI仍1.0，ID=0x2501、caps=0x3fff，bit13表示gather。公开顶层相对M24增加283逻辑LUT、9 FF，DSP和LUTRAM原语数量不变。RAM另消耗器件LUT，不能当作BRAM数量。

云端公开顶层50/100/200ps每段连线假设预算为2.791/3.391/4.591ns；计算/访存封装同值。最慢参考路径仍在FP32。未布局布线、未按-2校准，排除DSP相关端点及I/O/hold/RAM写时序，没有器件STA/SDF或WNS。实际300/500MHz通过状态保持未知。

本轮确认旧普通算术/滑移的v0数据源与执行mask双EEW别名限制尚未统一；该保留编码缺口已记入[ISA矩阵](isa-coverage.md)，下一轮应先统一检查和参考模型。新gather已做该检查；当前结果不构成完整RVV合规声明。

完整证据见[报告](../reports/m25/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m25.py`、`python3 scripts/package.py --milestone m25`。后续继续compress、宽窄整数、FP归约、更多LSU模式与SoC集成。
