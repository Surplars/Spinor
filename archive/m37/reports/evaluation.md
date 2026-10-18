# M37：进位/借位、饱和、平均与舍入右移

本轮新增39种标准编码形式，继续以VLEN128/ELEN64、RAM候选提交和固定300MHz条件预算为约束。结果以[M37报告](evaluation.md)的源码与证据散列为准。

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

规范摘录及39条官方opcode见[参考](../../docs/references/m37-fixed-point-v1.0.txt)。定点还缺vsmul和vnclip[u]；剩余FP、LSU及架构/SoC工作见[完整性计划](../../docs/rvv-completion-plan.md)，当前仍为部分RVV。

云端工具为Yosys xcup、Icarus RTL/FPGA原语功能仿真、局部SAT及RapidWright家族表。两个顶层沿用M25固定权重和100ps/段假设，均要求≤3.333ns。该预算未布局、未按-2速度档校准，排除DSP端点，不包含RAM写时序、hold、时钟树与IO；M37实际300/500MHz需要Vivado验证，不能继承M31结论。

复现：`make bootstrap`，然后`python3 scripts/verify_m37.py`和`python3 scripts/package.py --milestone m37`。


## 验证结果

独立FixedPointLane完整RTL 80956组输入，覆盖14种内部模式、4种SEW、4种舍入模式和364次撤销；精简RTL/映射各1398组。架构完整RTL 10171条命令，39种编码、22种合法类型，非法718、取消144；精简主配置/无FP/16位旧ALU配置均通过。精简架构RTL/当前网表各401条，数学结果、架构状态及周期一致。

旧M36全部RTL族重跑通过，包括宽化乘加5961条和M36新增整数3732条；当前网表通过M36精简17编码、旧整数MAC、89条混合序列、LSU143组、公共顶层143组和monitor。公共顶层完整RTL303组访存及新增饱和、carry、平均、舍入指令混合序列通过。当前网表覆盖为定向集成测试，未重跑全部ISA矩阵。回归子进程记录见receipt绑定的build/m37-regression。

旧220组性能及所有既有指令族性能记录相同。生成RTL逐字节相同的8个旧数值/存储/边界单元保留SHA绑定证据；FP数值证据绑定的单元RTL未改变，旧向量FP集成回归重跑。增量/地址SAT因顶层源码输入绑定变化重跑，未把其当作新定点指令的形式证明。详见[性能](performance.md)。

## Yosys xcup资源（括号相对M36）

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 / RAM32M16 |
|---|---:|---:|---:|---:|
| SpinorVpu | 20763 (+1010) | 12727 (+359) | 9 | 32 / 6 |
| LishiVpuMemory | 18414 (+888) | 11353 (+359) | 9 | 32 / 6 |
| RamVectorFp | 17092 (+803) | 10341 (+359) | 9 | 32 / 6 |

资源为未布局估计，LUTRAM另占LUT，不等于Vivado BRAM数量。

## 固定条件时序预算

| 连线ps/段 | M36公共ns | M37公共ns | M37计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.700 | 2.700 | 2.662 |
| 100 | 3.300 | 3.300 | 3.292 |
| 200 | 4.500 | 4.577 | 4.592 |

100ps/段下公共3.300ns、计算/访存3.292ns；余量0.033/0.041ns。固定M25模型/权重与3.333ns门槛未放宽。未布局、未按-2速度档校准；DSP、RAM写时序、hold、时钟树和IO等未签核。未执行M37 Vivado或SDF，实际300/500MHz未知。
