# M24：整数滑移

新增vslideup.vx/.vi、vslidedown.vx/.vi、vslide1up.vx、vslide1down.vx。仍为VLEN128/ELEN64的部分RVV、单指令容量，继续完善VPU本体；未接入Orbital或Linux，不声明完整V/RVA23。

## 实现与边界

支持全部22种合法SEW/LMUL、mask、vstart恢复和tail/inactive保留。上移禁止源目的组重叠；下移允许完全别名，始终读已提交RAM，避免读取本条候选写。vslidedown以VLMAX判断源越界，允许读取VL外的源tail；超VLMAX才补0。标量滑移量保持XLEN64精度，立即数为无符号5位；slide1按VL位置插入截到SEW的标量。VL0与vstart>=VL不改目的，非法对齐、上移重叠与masked目的v0在VL0仍检查。

保留全部旧状态编码和5位状态宽度，增加一个slideAddress阶段。译码寄存8位低偏移和高位非零标志；以9位精确计算源索引，暂存在现有a操作数寄存器。随后独立做VLMAX比较与RAM行/元素选择，沿用同步RAM、整数Op.move、tag写回及版本提交。VLMAX复用未提交的nextVl暂存，kind=0不会发布该私有值。没有新增整组FF快照、RF副本或DSP。普通源读取比旧基础整数多一个地址阶段；标量插入/补0绕过源RAM读取。

## 验证

独立Python参考先取整个源组的不可变元素数组，再以完整64位数学偏移计算目的，不复制RTL的低位/高位标志与9位分级实现。完整RTL 5576条命令，非法760、撤销128；六种编码、22种类型、跨寄存器、VL/VLMAX差异、超大偏移、立即数16..31、上下行重叠规则、源/目的v0、mask、vstart、零VL、标量插入和抑制、完成背压均覆盖。逐条核对32个寄存器、版本及CSR。376条smoke在RTL与映射中功能、异常、撤销和周期完全一致；无FP和16位切分也通过smoke。

M23索引生成1674条、前缀掩码2888、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及旧向量789重新通过RTL；13条混合INT/FP/滑移/归约序列通过RTL/映射，检查滑移模式及私有VLMAX不会泄漏到旧操作。220组旧性能结果与周期保持M23值。新滑移的逐配置周期保存在slide证据中，不把周期数当作物理频率。

物理访存254组RTL通过；公开SpinorVpu在monitor流量下254组RTL及94组RTL/映射通过，末尾包含新旧mask/index，以及滑移→别名下移→标量插入、非法上移别名与撤销。逐访存请求/周期与M23一致。Monitor ABI1.0，ID0x2401/caps0x1fff，bit12表示整数滑移；生产RTL/映射及8位回绕检查通过。

9个未修改数值/RF/访存/CPU边界单元按RTL和网表SHA复用已绑定单测及局部证明；增量器组合证明重新执行以绑定当前源码。旧mask/index本轮完整RTL与公开顶层映射集成已检查，没有把旧完整顶层的映射证据冒充为当前网表结果。实际CPU、Linux和器件时序未验证。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M23 SpinorVpu | 17767 | 11972 | 9 | 32 | 6 |
| M24 SpinorVpu | 17826 | 11983 | 9 | 32 | 6 |
| M23 LishiVpuMemory | 15474 | 10598 | 9 | 32 | 6 |
| M24 LishiVpuMemory | 15564 | 10609 | 9 | 32 | 6 |

Yosys xcup未布局映射；表中LUT是逻辑LUT计数，RAM另外占用器件LUT。RAM为LUTRAM，不能当作BRAM数量。

## 条件时序

| 每段假设连线ps | M23公开ns | M24公开ns | M24计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.791 | 2.718 | 2.791 |
| 100 | 3.391 | 3.368 | 3.391 |
| 200 | 4.591 | 4.668 | 4.591 |

100ps档公开顶层3.368ns，相对300MHz周期3.333ns算术余量-0.035ns；路径vpu.vpu.unit._r32_io_out[24]到vpu.vpu._unit_io_out_bits_data[0].D。计算/访存封装3.391ns。使用完全相同的权重及RapidWright家族表来源，M23图恢复后核对冻结SHA。

这不是器件STA或Fmax：没有布局布线、-2校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，无器件SDF、WNS或Vivado。300/500MHz通过状态仍为null，旧M5物理时序不自动继承。

## 复现与范围

make bootstrap；python3 scripts/verify_m24.py；python3 scripts/package.py --milestone m24。receipt.json绑定源码、RTL、网表、测试台、冻结基线与报告。继续补gather/compress、宽窄/定点、FP归约和访存模式；vfslide1 FP标量滑移、实际Orbital接入、VM/PMP/一致性及Linux上下文仍待完成。未修改Valence，未调用Verilator。
