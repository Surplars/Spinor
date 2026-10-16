# M23：向量索引生成

新增viota.m、vid.v，完善VPU本体；仍为部分RVV、VLEN128/ELEN64和单指令容量，不声明完整V/RVA23、Orbital接入或Linux运行。

## 实现

viota.m输出每个元素之前的有效源mask置位数；masked-out元素不计数。源为单mask寄存器，目的按正常LMUL分组。非零vstart、源位于目的组内、masked目的v0和目的未对齐非法，零VL仍检查。vid.v输出原始元素索引，支持mask和vstart恢复，vs2非零编码非法。全部22种合法SEW/LMUL均支持；保留tail和inactive值。

复用整数流水线、版本化RAM与已有scalarResult低8位作私有前缀计数；没有整组快照和新增RF副本。viota每个有效元素读取源mask，8位独立前缀进位完成计数更新；vid略过RAM源读取。新值进入原有Op.move流水和带tag写回。候选版本仅在完成握手后发布，flush取消，既有整数/FP周期基准保持一致。

## 验证

独立Python模型对整条有效索引集合求数学前缀和，不复制RTL逐元素反馈。完整新指令RTL 1674条命令，viota 455、vid 283、非法296、撤销62；覆盖22种类型、全部128个one-hot源位、部分tail、分数LMUL、源v0、目的v0、源未对齐、目的组内部重叠、非零vstart/恢复及完成背压。所有32寄存器、版本与CSR逐条核对。smoke RTL/映射网表功能和周期一致，无FP及16位切分另通过smoke。

8位前缀计数递增连同原32/55/109位增量器、地址与配置比较由SAT全输入检查；这是局部组合证明。旧前缀掩码回归2888条、mask/scalar10198、mask scan2894、归约3418、整数乘除1673、FP向量2157、streaming251及混合INT/FP/归约通过。旧前缀保留1505次合法操作；16/17两个selector现归新指令，旧reserved检查改由专门的新指令模型覆盖。原220组性能结果及周期与M22一致。

物理访存封装254组RTL；公开SpinorVpu在持续monitor流量下254组RTL及94组RTL/映射通过，末尾新增viota→标量提取→vid并核对RAM。逐访存请求/周期和M22一致。monitor ID=0x2301/caps=0xfff，新增bit11索引生成，ABI仍1.0；生产RTL/映射和8位计数回绕通过。

SHA核对9个数值、RF、访存与CPU边界单元RTL未变，复用已绑定输入的单元验证和舍入/重编码/除法证明；新顶层功能回归重新执行。真实CPU未参与测试。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M22 SpinorVpu | 17731 | 11968 | 9 | 32 | 6 |
| M23 SpinorVpu | 17767 | 11972 | 9 | 32 | 6 |
| M22 LishiVpuMemory | 15417 | 10594 | 9 | 32 | 6 |
| M23 LishiVpuMemory | 15474 | 10598 | 9 | 32 | 6 |

Yosys xcup未布局映射；RAM为分布式LUTRAM，不能当成BRAM数量。

## 条件时序预算

| 每段连线假设ps | M22公开ns | M23公开ns | M23计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.791 | 2.791 | 2.791 |
| 100 | 3.391 | 3.391 | 3.391 |
| 200 | 4.668 | 4.591 | 4.591 |

100ps档公开顶层3.391ns，300MHz周期3.333ns的算术余量-0.058ns；路径vpu.vpu.unit.r32.sAdjustedExp[0]到vpu.vpu.unit._r32_io_out[22].D。计算/访存封装3.391ns。保持相同权重和RapidWright家族表来源，对M22冻结图核对SHA后重新分析。

这不是器件STA或Fmax：无放置布线、-2校准、DSP相关端点、时钟树/hold、RAM写及I/O路径检查，无器件SDF、WNS或Vivado运行。300/500MHz通过状态仍为null，M5物理结果不能继承。

## 复现和范围

make bootstrap；python3 scripts/verify_m23.py；python3 scripts/package.py --milestone m23。receipt.json绑定源码、RTL、映射图、测试台、冻结基线与报告。后续继续排列、宽窄/定点、FP归约和LSU模式；Orbital集成、VM/PMP/一致性和Linux计算驱动仍待完成。未使用Verilator或修改Valence。
