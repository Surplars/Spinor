# M20：Spinor FP 路径优化与掩码扫描

新增vcpop.m/vfirst.m，优化FP舍入、FP32分类、除法与浮点转整数的进位、FMA规格化和monitor回绕检测。仍为VLEN128/ELEN64、容量1的部分RVV执行器，未接入实际Orbital或Linux计算驱动。

## 功能证据

掩码扫描完整RTL973条命令：vcpop和vfirst各177次、非法90次、撤销14次，覆盖22种合法SEW/LMUL。含masked、v0源、未对齐单寄存器源、rd=x0、vl=0、无置位、非零vstart非法。核对全部32个寄存器、版本表和CSR，完成背压禁止提前提交。映射smoke与同输入RTL的覆盖、周期一致；无FP与16位切分版本另通过smoke。

FP独立数值回归6811组，5种舍入模式、FP32/64、205次flush/reset，通过SoftFloat位精确结果和异常标志检查；385组映射子集与RTL延迟相同。浮点转换另通过5021组和492次flush/reset。整数除法符号修正改为8位分组，RTL/映射各2894组与270次flush通过，延迟不变。四种原始格式的StagedRound通过10步、单次稳定输入的有界SAT等价检查，含完成信号非空检查；这不等于完整流水线形式化。FP32/64重编码、FP32分类、23/52/54位平衡前导零编码和加法/递增含进位的组合等价证明通过，输入与模式约束见各proof结果。

M19的5372条mask/标量搬运测试（含1409次mask运算、358次标量读写、267次非法、60次flush）继续通过完整RTL。旧归约1411次、整数乘除1673条、FP向量2157条、旧版向量789条、streaming251条和7条混合INT/FP程序通过，混合程序另通过映射网表。220组性能用例全部校验结果，其中216组周期不变，4组vfadd按每活动元素增加1周期；差值记录在performance_cycle_deltas。

舍入多一级流水使使用它的算术/整数转浮点增加1周期，其余优化没有增加周期。FP向量回归从222811到225358周期，增加2547。4组vfadd的额外周期为32/256/16/128，对应8条指令乘活动元素数；整数周期不变不代表FP吞吐不变。

默认访存顶层254组RTL通过。公开SpinorVpu在持续monitor读取时通过254组RTL与94组RTL/映射子集，另执行归约、标量搬运、mask生成/消费、vcpop/vfirst并检查monitor功能位。所有访存请求数量和独立吞吐基准周期与M19相同。FP加法后store的用例197从82变81周期：新增FP流水改变了测试台cycles%3控制A-ready的相位，不是LSU吞吐改善；其余逐用例周期不变。总周期也包含新增末尾指令。Monitor生产RTL/映射、8位回绕各2600周期通过。回绕预测增加13个标志寄存器，overflow仍在实际回绕当拍置位；clear行为不变。ABI1.0，ID=0x2001/caps=0x3ff。UIO工具只作编译/文件夹具测试。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M19 LishiVpuMemory | 15497 | 10218 | 9 | 32 | 6 |
| M20 LishiVpuMemory | 15675 | 10570 | 9 | 32 | 6 |
| M19 SpinorVpu | 17679 | 11579 | 9 | 32 | 6 |
| M20 SpinorVpu | 17863 | 11944 | 9 | 32 | 6 |

复用单RF读口和scalar completion。新增FF主要用于舍入分级与monitor回绕预测；不增加DSP、整组向量快照或RF副本。RAM数字是分布式映射原语而非BRAM块数。独立VpuHostBoundary源码/RTL与M19一致，仍不在Spinor顶层内，实际CPU接入未验证。

## 300 MHz 尚未确认通过

300 MHz周期为3.333 ns。公开SpinorVpu的云端条件预算如下，余量仅是算术差值：

| 每段假设连线ps | M19 ns | M20 ns | M20相对3.333 ns余量 |
|---:|---:|---:|---:|
| 50 | 3.082 | 2.682 | +0.651 |
| 100 | 3.732 | 3.232 | +0.101 |
| 200 | 5.109 | 4.332 | -0.999 |

计算/访存顶层LishiVpuMemory的三档为2.791/3.391/4.591 ns。不同顶层综合优化产生不同映射，不能将其预算相加或混用。

公开顶层100 ps假设的最大预算为3.232 ns，相对300MHz周期余量+0.101 ns。路径为vpu.vpu.unit.r32.sAdjustedExp[0]到vpu.vpu.unit._r32_io_out[0].D。独立计算/访存封装100 ps档仍为3.391 ns，不在3.333 ns预算内。两种封装的综合映射不同，不能选择较小数字当作全设计时序结论。

预算有正余量只说明该假设下覆盖路径在预算内，不能判定器件通过300MHz；负余量提示仍应处理的路径。两版使用相同的单元、连线及建立假设。

这是Yosys未布局网表、RapidWright家族参考弧及显式连线/建立假设。346个DSP相关端点排除，未做-2速度校准、时钟树/布线、hold、RAM写或I/O时序。没有器件SDF/STA、WNS、Fmax或本轮Vivado结果。RTL/映射功能仿真通过不等于满足给定MHz。历史M5的真实OOC结果不代表M20。

## 接入与复现

CPU合同见docs/cpu-spinor-contract.md，新指令与优化见docs/m20-timing-mask-scan.md，剩余范围见docs/isa-coverage.md。仍缺排列、宽窄/定点、FP归约、完整访存、上下文/保护/一致性和实际Orbital接入。

复现：make bootstrap，然后python3 scripts/verify_m20.py；打包python3 scripts/package.py --milestone m20。receipt.json绑定本轮源码、RTL、网表、测试台与证据。没有执行Verilator或修改Valence/Orbital源码。
