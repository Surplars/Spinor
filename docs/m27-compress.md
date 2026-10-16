# M27：RAM式vcompress

新增RVV 1.0的vcompress.vm，支持本核全部22种SEW/LMUL；VPU仍为部分RVV，单条指令容量，不声明完整V/RVA23。

## 语义

vs1是一个EEW1显式掩码寄存器。源组vs2中索引小于VL且掩码为1的元素，按原顺序紧密放到vd组前部；其余目的元素属于tail，当前选择允许的undisturbed保留。掩码高于VL的位忽略。vs1不需要按数据LMUL对齐。

仅vm=1且vstart=0合法。目的组不能重叠源数据组或掩码；同一物理寄存器也不能同时提供EEW1掩码和SEW数据。VL0仍检查这些保留编码。v0可以分别作为合法的数据、掩码或目的，只要满足重叠约束。

## RAM与流水

使用已有indexGenerate模式3、scalarResult中的8位密集目的计数，以及slideAddress地址阶段，没有新增状态、寄存器、整组快照或RF端口。显式掩码从已提交RAM读取一次到已有128位缓存。扫描源索引，未选中只推进索引；选中才读源元素，下一阶段计算密集目的地址，再通过整数move写候选RAM。完成握手才发布目的版本；flush撤销候选结果。压缩采用串行元素执行，原基本整数元素流水和FP执行方式保留。

旧mask目的、viota、gather/EI16和新compress的组几何检查使用幂次对齐后的高位匹配。alignment由布尔式产生；不同组尺寸取较大范围的对齐掩码比较。非法对齐和EI16不支持的count=0仍先检查。局部SAT证明覆盖所有5位寄存器号、四种组尺寸与合法对齐下的成员、重叠及末端不越过32；不是整个ISA的形式证明。

Monitor ABI1.0，ID0x2701、caps0x7fff，bit14表示compress；TileLink接口保留。

## 验证与周期

独立Python参考用不可变全源组数组加列表过滤，完整RTL1229条命令、363条非法、37次取消，覆盖22种类型和32寄存器/版本/CSR检查。189条smoke通过RTL及当前映射网表；无FP、16位切分版也通过。24条混合指令序列包含compress→FP→viota→compress→gather；公开SpinorVpu另检查取消、tail保留、非法编码和返回整数执行。

e8/m8、VL128、完成无背压时：选中0/1/64/128个元素分别151/162/855/1559拍（包含命令与复制准备开销）。当前该类型满足23+VL+11×选中数，不宣称每拍压紧一个元素。旧220组基准逐组核对结果及周期，保持M26。

## 云端条件门槛

| 顶层 | 50ps/段 | 100ps/段 | 200ps/段 |
|---|---:|---:|---:|
| SpinorVpu | 2.500ns | 3.050ns | 4.227ns |
| LishiVpuMemory | 2.700ns | 3.300ns | 4.577ns |

固定100ps/段及原家族权重下均≤3.333ns；计算/访存只余0.033ns。仍无布局布线和ZU15EG-2器件校准，DSP相关端点、时钟树/hold、RAM写、IO等不在此门槛中；200ps档不满足300MHz周期，物理300/500MHz通过字段仍为null。

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| SpinorVpu | 18292 | 12300 | 9 | 32 | 6 |
| LishiVpuMemory | 15888 | 10926 | 9 | 32 | 6 |

这是Yosys xcup未布局映射；RAM还占用器件LUT，原语数量不是BRAM数量。逻辑LUT的小幅变化包含全局映射变化，不能直接当作新增功能本身的成本或实际Fmax改善。

完整证据见[报告](../reports/m27/evaluation.md)。复现：make bootstrap；python3 scripts/verify_m27.py；python3 scripts/package.py --milestone m27。尚未接实际Orbital/Linux，后续继续宽窄整数、FP归约和访存模式。
