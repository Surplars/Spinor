# M36：宽化整数乘加、反减/比较与整组搬运

本轮补齐三组共17种标准编码，继续以RAM资源和300MHz条件时序门槛约束实现。功能、回归与映射结果以[M36报告](../reports/m36/evaluation.md)及其输入散列为准；当前仍是部分RVV，未接入Orbital。

| 新增指令 | 编码数 | 实现范围 |
|---|---:|---|
| vwmaccu/vwmacc/vwmaccsu vv/vx、vwmaccus vx | 7 | 源SEW8/16/32，完整2×SEW乘积加旧vd，目的EMUL≤8 |
| vrsub vx/vi、vmsgtu/vmsgt vx/vi | 6 | SEW8/16/32/64及合法LMUL，支持mask和vstart |
| vmv1r/2r/4r/8r.v | 4 | 复制1/2/4/8个完整寄存器，支持按SEW解释的vstart |

## 宽化整数乘加

宽化乘加计算`旧vd + 乘数1 × vs2`，结果按2×SEW取模。`vwmaccu`两个乘数均无符号，`vwmacc`均有符号；`vwmaccsu`的vs1或标量有符号、vs2无符号；`vwmaccus.vx`的标量无符号、vs2有符号。vx先截取标量低SEW位，再按相应类型扩展。标准没有`vwmaccus.vv`编码。

沿用M35乘加调度和M34宽化几何：窄源以SEW寻址，旧目的和结果以2×SEW寻址；旧vd读取使用目的地址，跨寄存器和重启时不沿用窄源偏移。乘积经现有64位归约暂存寄存，再送原分段ALU加旧vd。仍使用原16×16分时乘法器和原RAM端口，没有增加专用宽乘法器或整组FF快照。容量仍为一条指令，乘加逐元素串行。

目的组最大8个寄存器，源SEW64和源LMULm8宽化形式超出本实现范围并拒绝。窄源之间可以相互重叠；旧vd同时是2×SEW源，因此不能与任一窄源共享物理寄存器，即使是普通宽化运算允许的最高部分重叠也不合法。此规则来自同一指令不能以不同EEW读取同一源寄存器的约束。masked指令的v0与数据源不同EEW约束继续适用。

沿用版本化RAM提交：prestart、mask和tail保持，源读取已提交版本，结果先写候选组，接受完成后才翻转版本。VL0、全mask关闭和vstart越过VL仍进行编码/组合法性检查。取消丢弃候选结果；整数乘加不修改vxrm/vxsat或FP舍入和flags。

## 反减与大于比较

`vrsub`计算标量或立即数减vs2，在原操作数寄存阶段交换加减器输入，复用原分段减法流水。`vmsgt[u]`复用原有小于等于比较并翻转返回的比较位，写入单寄存器mask目的；有符号和无符号形式分别使用对应比较器。反减和比较模式在译码阶段寄存。

5位立即数先符号扩展到SEW，包括`vmsgtu.vi`；无符号形式比较的是扩展后的位模式。向量标量形式使用标量低SEW位。支持原mask/prestart/tail保留和同宽源/目的别名规则；mask目的可为v0，执行mask仍从已提交版本读取。没有新增`vrsub.vv`或`vmsgt[u].vv`编码，后者由交换源的`vmslt[u].vv`表达。

## 整组寄存器搬运

`vmvNr.v`只允许N=1/2/4/8、vm=1及相应组对齐；其组长度不取自LMUL，也不受VL或vill禁止。有效元素数为`evl=N×VLEN/SEW`，从`vstart×SEW/8`字节开始复制，之前的目的字节保留；vstart≥evl时不写数据。vd=vs2为架构NOP，成功完成仍清零vstart。组对齐保证相同长度的合法源/目的组要么相同、要么不重叠。

搬运先通过原复制阶段准备候选目的，再按128位RAM块读取已提交源并写候选目的；逐字节写使能保留重启前的字节。使用专门的读/写状态，不经整数ALU，也不把整组数据放入FF。撤销及完成背压继续受版本表提交边界约束。这是寄存器到寄存器搬运，整组load/store仍未实现。

## 时序分段

整组搬运新增独立wholeCheck阶段，先寄存编码检查和重启字节位置，再决定是否复制；该编码的检查增加1拍。copyRead/wholeRead阶段预存copyLast，下一写阶段直接使用比较结果，不增加旧指令周期。执行单元的实际位宽在原合法性检查阶段寄存，避免把指令funct字段译码与ALU输入掩码/比较连成组合链。

LSU在原decode阶段寄存高32位地址的3个进位前缀，addressHigh阶段以4个独立8位块增量，元素状态数和周期保持不变。FP转整数在原calculate阶段寄存每32位字的8/16/24位前缀；FMA在原phase0寄存低8至104位前缀，随后分块计算109位幅值。没有增加FP流水阶段，数学结果与延迟由重新执行的SoftFloat参考、RTL/网表测试和分块增量SAT证明检查，最终证据以报告为准。

## 验证与评估边界

`tests/test_widening_mac.py`用不可变三源快照和Python精确整数乘加作为独立参考，覆盖符号组合、标量截断、完整高半积、宽窄组边界、别名非法编码、mask/vstart以及候选写回和完成等待期间的取消。`tests/test_m36_integer.py`覆盖本轮17种编码，包括立即数、无符号高位比较、整组搬运的VL0/vill/自复制/重启及非法selector；精简模式用于当前映射网表的集成功能检查。测试逐条核对全部向量寄存器、版本与sticky架构状态；具体通过数量和输入绑定范围记录在报告，不把精简网表覆盖等同于完整RTL矩阵。

Monitor ABI保持1.0，实现ID为0x3601、caps为0x3ffffff；新增bit23宽化整数乘加、bit24反减/大于比较、bit25整组搬运。Command/Completion和TileLink外部端口不变，已有monitor用户态工具仍不构成计算作业驱动。

云端继续使用Yosys xcup映射、Icarus RTL/网表功能仿真、局部SAT及RapidWright家族延迟参考。固定M25权重与100ps/段连线假设，公共和计算/访存顶层条件预算都必须≤3.333ns；不通过时继续调整实现，不放宽模型。该模型排除DSP相关端点，也不含布局布线、-2速度档校准、hold、时钟树、RAM写时序或外部IO。M36实际300/500MHz需独立Vivado验证，不能继承M31结果。

复现入口：

```sh
make bootstrap
python3 scripts/verify_m36.py
python3 scripts/package.py --milestone m36
```

规范原文和17条官方编码保存在[参考摘录](references/m36-integer-v1.0.txt)。剩余主要工作是定点、进位/借位、剩余FP、完整LSU及架构/SoC验证，见[完整性计划](rvv-completion-plan.md)。
