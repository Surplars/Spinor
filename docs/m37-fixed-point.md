# M37：进位/借位、饱和、平均与舍入右移

本轮新增39种标准编码形式，继续以VLEN128/ELEN64、RAM候选提交和固定300MHz条件预算为约束。结果以[M37报告](../reports/m37/evaluation.md)的源码与证据散列为准。

| 指令族 | 编码数 | 范围 |
|---|---:|---|
| vadc/vmadc、vsbc/vmsbc | 15 | 加法vv/vx/vi、减法vv/vx；mask结果另有无进位/借位输入形式 |
| vsaddu/vsadd、vssubu/vssub | 10 | 饱和加法vv/vx/vi、饱和减法vv/vx |
| vaaddu/vaadd、vasubu/vasub | 8 | 平均加减vv/vx，全部四种vxrm模式 |
| vssrl/vssra | 6 | 逻辑/算术舍入右移vv/vx/vi，全部四种vxrm模式 |

均支持整数SEW8/16/32/64及22种合法SEW/LMUL组合，支持vstart及源/目的同宽别名。普通定点指令按v0过滤执行元素；carry指令的v0是数据输入：vm=0时仍执行全部body元素，不按v0跳过。vadc/vsbc只允许vm=0且目的不能为v0；vmadc/vmsbc可写v0，vm=1时进位/借位输入为零。保留的组对齐、mask与数据源不同EEW别名规则在VL0、全mask关闭和越界vstart时仍检查。

新的FixedPointLane使用8位CarrySelect逐字节传递进位，最多8次算术步覆盖64位；完成一个元素后处理其carry/borrow、饱和或精确SEW+1平均结果。平均运算保留额外位，再舍入和截断，包含unsigned减法下溢与signed加减溢出边界。舍入右移分三个radix-4阶段，每级保存guard/sticky，再复用字节加法器完成舍入增量。输入、状态和输出有独立寄存边界，没有新DSP或整组FF快照。旧IntegerLane、乘除和FP单元保持原实现；新增指令逐元素串行，不构成多指令并行。

vxrm使用RNU、RNE、RDN、ROD四种模式；vi舍入移位使用零扩展uimm5，饱和加法和carry加法使用符号扩展simm5。移位量按SEW-1掩码；移位0不舍入。平均和舍入右移不设置vxsat。

饱和指令只累计实际执行元素的溢出。累计结果先保存在指令私有fixedFlags中，在Completion接受时与原vxsat按位或；候选结果、vstart和vxsat在完成背压期间不提前发布，flush丢弃私有状态。原vxsat=1保持，VL0、全mask关闭、prestart与tail不产生新的饱和。vcsr/vxrm/vxsat CSR别名可读写，FP的frm/fflags不受这些整数指令影响。

独立Python参考使用任意精度整数、夹紧及数学商余数计算，不复制硬件分字节/分级移位结构。执行单元测试覆盖14种内部模式、全部SEW与舍入模式、边界和随机输入、输出背压及各状态撤销；架构测试逐条核对32个向量寄存器、版本、vstart、vxrm、vxsat和FP状态。完整/精简RTL、无FP和16位旧ALU配置、当前网表范围及实际数量见报告。

Monitor ABI仍为1.0，ID=0x3701，caps=0x3fffffff；新增bit26 carry/borrow、27饱和加减、28平均、29舍入右移。Command/Completion、TileLink与monitor外部端口不变。仍未接入Orbital或真实Linux计算驱动。

规范摘录及39条官方opcode见[参考](references/m37-fixed-point-v1.0.txt)。定点还缺vsmul和vnclip[u]；剩余FP、LSU及架构/SoC工作见[完整性计划](rvv-completion-plan.md)，当前仍为部分RVV。

云端工具为Yosys xcup、Icarus RTL/FPGA原语功能仿真、局部SAT及RapidWright家族表。两个顶层沿用M25固定权重和100ps/段假设，均要求≤3.333ns。该预算未布局、未按-2速度档校准，排除DSP端点，不包含RAM写时序、hold、时钟树与IO；M37实际300/500MHz需要Vivado验证，不能继承M31结论。

复现：`make bootstrap`，然后`python3 scripts/verify_m37.py`和`python3 scripts/package.py --milestone m37`。
