# M16 前缀增量与拆分地址

ParallelIncrement逐位计算x_i XOR (enable且所有低位为1)，等价于固定宽度的x+enable，不输出溢出位。与旧16位增量分组相比，避免长归约之后再串接局部进位链。用于FP后处理55/109位增量及LSU高32位地址递增，无新增寄存器或周期。

LSU低32位地址使用已证明的CarrySelect.add，保留第33位进位，高字按该进位递增后拼接。地址运算仍为base+(index<<EEWlog)模2^64；不是饱和地址、分页或PMP。正常RAM窗口、对齐、故障前缀和延迟停止合同不变。

VectorConfig.belowLimit对64位AVL和8位VLMAX，先归约AVL高56位，再比较低8位；fractionalLegal以布尔条件表示原分数LMUL规则，避免译码中的小减法。所有组合等价，不增加配置指令周期。

新增32组地址故障测试，覆盖每种EEW及load/store的低16位进位、低32位进位、64位回绕和任意高字递增，检查完整fault address、vstart、原因及零总线请求。新用例也修正了测试setstart对CSR旧值的假设：连续故障后的旧vstart可能非零，期望值必须跟踪真实模型状态；不是修改硬件CSR语义。

GenerateIncrementProof直接使用生产ParallelIncrement/CarrySelect/VectorConfig，Yosys SAT对32/55/109位增量全部输入、拆分64位地址公式（base64/index8/EEWlog2）、分数LMUL规则及64对8位比较证明等价。仅是组合公式证明，流水、flush、配置状态和异常前缀由独立数值及映射后仿真检查。

make verify-m16 / make package-m16复现；证明命令python3 scripts/prove_increment.py。仍使用固定RapidWright家族表和显式50/100/200ps每段连线假设；没有速度等级标定、布局布线、真实时钟树、DSP全覆盖、hold或RAM写setup，预算不是WNS。没有新ISA、请求队列、多请求并行或实际Valence集成。
