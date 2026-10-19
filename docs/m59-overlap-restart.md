# M59：原地运算、寄存器组重叠与非零vstart

标准/Deep分别通过228,800条公共端口命令，合计457,600条。
本轮推进VPU内部语义验收，没有新增ISA指令或修改硬件。

26种代表操作覆盖22种vtype、16种寄存器布局、5种起点/掩码profile。
每预设45,760个目标中，16,635合法、29,125按编码/几何规则拒绝；
12,780个合法目标使用非零vstart，5,878个在起点之后仍有计算范围。
其中5,847个包含活动元素，31个全mask关闭；每种操作都有实际活动的恢复样本。
包括同宽原地、缩窄最低部、扩宽最高部、分数EMUL、mask目标、
gather/EI16、slide和浮点MAC/转换，全部26种操作都有非零起点计算样本。

独立参考按规范的EEW/EMUL区间解释重叠，整数使用Python运算，浮点使用SoftFloat。
固定Spike拒绝非零算术vstart，故先用16,298个vstart=0场景交叉核对模型，
再按独立模型验证非零起点；**不能把这轮非零vstart称为Spike差分**。
维护版规范的混合源EEW保留策略与固定Spike有分歧，明确排除这些交叉核对点，
但仍在DUT完整矩阵中验证拒绝，没有修改Spike语义。

每条命令完整比较RF/CSR/Completion身份。独立条款检查确认81,312个prestart、
172,040个tail、15,149个inactive元素保持；非法指令保留vstart，合法完成清零。
961个目标改变fflags，399个改变vxsat；24次运行错误注入和2次条款负控制均检出。
另有23个明确合法/拒绝的重叠锚点，避免只用一套区间算法自证。

这不是全部330种算术编码、所有策略/起点/布局的穷举；特殊归约、compress、
viota等规则保留既有证据。本轮写入RF和vstart模拟恢复入口，没有真实CPU中断或trap声明。
规范允许某些实现拒绝自身不会产生的非零起点，本轮记录Spinor支持行为。

54个Scala文件精确不变，仍为VLEN128/ELEN64、单lane、单指令在途、RAM寄存器文件。
资源及云端3.300ns条件预算沿用M56；不是当前ZU15EG-2的实际300MHz签核。
CPU退休、VS/FS、FCSR所有权、MMU/PMP与一致性边界不变，没有联编Orbital。

[完整报告和复现](../reports/m59/evaluation.md)、
[逐操作覆盖](../reports/m59/operation-coverage.csv)、
[规范引文、锚点与计数](../reports/m59/semantic-clauses.json)。

入口：`python3 scripts/verify_m59.py`；`--check-only`审计精确源码与产物。
完整V/RVA23/Zvkt声明仍待剩余条款、架构套件及对应验收。
