# M33：宽化整数加减

新增 `vwaddu/vwadd/vwsubu/vwsub` 的 `vv/vx/wv/wx` 共16种编码，支持源SEW8/16/32、目的16/32/64位，共15种合法SEW/LMUL组合。`vv/vx`将两个窄源分别零/符号扩展后计算；`wv/wx`的vs2已经是双宽，另一源仍为SEW宽。标量先截取低SEW位，再按有符号/无符号扩展，结果按2×SEW回绕。x0标量可表达`vwcvt.x.x.v`与`vwcvtu.x.x.v`伪指令。不是饱和运算，vxrm/vxsat及FP状态保持不变。

复用原整数add/sub分段流水、RAM端口、源EEW寄存器和64位操作数暂存，不增加状态、流水级或整组FF快照。内部sew记录目的宽度，sourceSew记录vs2宽度，第二向量源按配置SEW独立寻址；tag退休地址与候选字节mask按目的宽度生成。架构vtype/vl不变。目的寄存器组扩大到2×LMUL，复制、候选版本与提交掩码覆盖整个目的组；未执行的mask/tail/prestart字节保留。

目的EMUL≤8且EEW≤ELEN64；m8或源SEW64保留非法。宽源按宽EMUL对齐，窄源按LMUL对齐。目的可与同宽vs2原地重叠；与窄源重叠只允许源EMUL≥1且窄源占目的最高部分。分数窄源即使共用同一物理寄存器也不得与目的重叠。`.wv`的不同EEW源组不能共享物理寄存器。VL0、全mask关闭与vstart越过vl仍先检查保留编码；合法非零vstart可重启，完成握手才提交版本，flush丢弃候选结果。公共monitor ABI仍1.0，ID0x3301、caps0x1fffff，新增bit20表示宽化整数加减。

独立Python参考模型以不可变源快照、实际字节数和寄存器区间计算EEW/EMUL、重叠与逐元素结果；逐条核对全部32个寄存器、版本、配置及sticky状态。包含不同宽度跨寄存器、进位/借位、负数、标量高位截断、最高部分合法重叠、`.w`原地写回、非法源别名、上界v24..v31、掩码、VL0、vstart和取消/完成停顿。无FP与16位切分版本也有smoke覆盖。独立SAT继续对照组计数表与布尔对齐/最高重叠表达式。旧宽化归约负例的funct3=2已是合法vwaddu，因此换用仍保留的funct3=3立即数形式；归约用例数量和非法检查计数保持不变。58条混合序列覆盖宽化加减与原归约、扩展、窄化、INT/FP及排列的模式切换；公共顶层并发monitor下追加宽化、掩码、flush和非法重叠检查。

64个e8/m4元素、目的e16/EMUL8：无完成停顿时vv/wv约414周期，vx/wx约286周期；均为当前单指令流水、包含配置外的指令执行/目的复制与提交开销。数值与周期在RTL及smoke网表之间核对。旧220组性能用例以冻结M32为基线，当前周期、完整测试计数与资源/时序结果由[本轮报告](../reports/m33/evaluation.md)给出。

云端工具为Yosys映射、Icarus功能/网表仿真、SAT与RapidWright家族延迟权重。沿用冻结M25权重和100ps/段的条件门槛，两个顶层预算必须≤3.333ns。该模型排除DSP相关端点，缺少器件布局布线、速度档校准、hold、时钟树、RAM写及外部IO/SDF时序，不能代表实际ZU15EG-2已通过300/500MHz。M31实际本地OOC setup+0.392ns、hold+0.009ns只保留为历史基线，不能传递给M33。

仍为部分RVV、指令容量1，尚未接实际Orbital或Linux，不能发布完整V/RVA23或misa.V声明。接下来继续宽化乘法、定点饱和/clip、FP宽窄转换与访存模式；Orbital异常、上下文和内存模型集成另行推进。

复现：

```sh
make bootstrap
python3 scripts/verify_m33.py
python3 scripts/package.py --milestone m33
```

M33项目包含当前源/RTL/测试与网表、固定M25/M32比较图及M31本地基线记录。本轮继续云端验证，不要求立即重跑Windows；旧M31 Windows包只对应M31。RVV规则与编码摘录见`docs/references/widening-add-sub-v1.0.txt`。
