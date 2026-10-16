# M19：Spinor 掩码逻辑、整数标量搬运与 300 MHz 参考

新增8种mask逻辑.mm和2种整数标量搬运，仍为VLEN128/ELEN64、容量1的部分RVV执行器。未接入实际Orbital、Linux计算驱动或实验OoO窗口。

## 功能证据

完整RTL：5372条命令，1409次合法mask逻辑、181次标量读、177次标量写、267次非法编码、60次flush，覆盖22种合法SEW/LMUL。所有32个寄存器、版本表、vstart和非零FP/定点CSR均核对；完成背压不得提前提交，撤销时同时拉高completion-ready。映射子集与同输入RTL的覆盖、结果和周期完全相同；无FP及16位分段版本另通过smoke。它们是有限差分验证，不是形式化或ISA全合规。

原有1411次整数归约、1673条整数乘除、2157条FP向量、789条旧版向量、251条streaming和7条归约/INT/MUL/FP混合程序通过，混合程序也通过映射网表。220组旧性能用例逐项周期与M18相同。标量搬运无完成背压时读6周期、写8周期；mask逻辑为逐位串行，非并行布尔向量单元。

默认访存顶层254组RTL通过。公开SpinorVpu在持续monitor读取时通过254组RTL与94组RTL/映射子集，另外执行真实归约、符号扩展标量读写、mask XOR生成v0、masked vadd并检查尾部。访存逐用例性能指标与M18相同；总周期包含新增末尾指令。Monitor生产RTL/映射和8位回绕各2600周期通过；UIO用户态工具通过编译及文件夹具，未测试实际内核/设备。ABI仍1.0，ID=0x1901、caps=0x1ff。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M18 LishiVpuMemory | 14790 | 10209 | 9 | 32 | 6 |
| M19 LishiVpuMemory | 15497 | 10218 | 9 | 32 | 6 |
| M18 SpinorVpu | 17014 | 11570 | 9 | 32 | 6 |
| M19 SpinorVpu | 17679 | 11579 | 9 | 32 | 6 |

LishiVpuMemory计算/访存顶层增加707 LUT、9 FF；含monitor的SpinorVpu增加665 LUT、9 FF。复用整数lane、单RF读口、候选写回和scalar completion；不增加DSP、向量FF快照或RF副本。上述RAM是分布式映射原语，不是BRAM块数。独立VpuHostBoundary仍不在Spinor顶层内，源码及RTL与M18一致，复用已记录的单元证据；实际CPU握手未验证。

## 300 MHz 尚未确认通过

300 MHz周期为3.333 ns。公开SpinorVpu的云端条件预算如下，余量仅是算术差值：

| 每段假设连线ps | M18 ns | M19 ns | M19相对3.333 ns余量 |
|---:|---:|---:|---:|
| 50 | 3.082 | 3.082 | +0.251 |
| 100 | 3.732 | 3.732 | -0.399 |
| 200 | 5.032 | 5.109 | -1.776 |

计算/访存顶层LishiVpuMemory的三档为3.100/3.800/5.200 ns。不同顶层综合优化产生不同映射，不能将其预算相加或混用。

公开顶层50/100 ps假设下的最大链仍是FP64舍入路径；200 ps时最大链变为vtype到状态寄存器的控制路径，比M18预算增加0.077 ns。100 ps假设下3.732 ns已经超过3.333 ns，因此不能说云端参考已通过300 MHz；50 ps档虽有正余量，也不能证明器件达标。

这是Yosys未布局网表、RapidWright家族参考弧及显式连线/建立假设。346个DSP相关端点排除，未做-2速度校准、时钟树/布线、hold、RAM写或I/O时序。没有器件SDF/STA、WNS、Fmax或本轮Vivado结果。RTL/映射功能仿真通过不等于满足给定MHz。历史M5的真实OOC结果不代表M19。

## 接入与复现

CPU合同见docs/cpu-spinor-contract.md，新指令与剩余范围见docs/m19-mask-scalar.md和docs/isa-coverage.md。仍缺vcpop/vfirst、排列、宽窄/定点、FP归约、完整访存、上下文/保护/一致性和实际Orbital接入。

复现：make bootstrap，然后python3 scripts/verify_m19.py；打包python3 scripts/package.py --milestone m19。receipt.json绑定本轮源码、RTL、网表、测试台与证据。没有执行Verilator或修改Valence/Orbital源码。
