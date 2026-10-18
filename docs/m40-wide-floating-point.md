# M40：宽化浮点算术与融合乘加

新增基础V范围内的18种宽化浮点编码。目标仍VLEN128/ELEN64，当前仅支持FP32源→FP64结果；不是FP16算术或完整RVV/RVA23声明。整数预设继续拒绝浮点指令，四个规模预设保持不变。

| 指令 | 形式 | 编码数 |
|---|---|---:|
| vfwadd / vfwsub | vv、vf、wv、wf | 8 |
| vfwmul | vv、vf | 2 |
| vfwmacc / vfwnmacc / vfwmsac / vfwnmsac | vv、vf | 8 |

窄源SEW32、目的EEW64。允许LMUL m1/m2/m4/mf2（目的EMUL2/4/8/1），m8目的超出EMUL8而非法；SEW8/16及需要128位结果的SEW64也拒绝。vstart、mask、合法别名和全部五种有效frm均支持；tail/prestart/inactive保留。保留frm、组对齐和源重叠在VL0或无有效元素时也检查。

## 一套共享FP通路

FloatingPointLane新增可选enableWiden配置；默认配置保持旧端口与生成RTL。实际VPU实例使用FloatingPointLaneWiden，额外的内部两位精度选择在请求握手时锁存：0表示原同宽路径（含原FP32+FP64宽化归约），2表示FP64 A/FP32 B，3表示FP32 A/B；1保留。

FP32先经原始浮点解码、精确扩展为FP64 recoded操作数，再复用原FP64对齐、DSP部分积、归一化和舍入。乘加的旧vd作为FP64 C，直接走FMA通路并最终舍入一次，不截成FP32。信号NaN与特殊值信息保留至运算异常判断，结果NaN按现有规则规范化。没有另建浮点乘法器或完整向量组FF快照，DSP数量由综合结果核对。

原同宽转换、除法、sqrt、比较和符号操作仍走旧路径。宽化分支只接受指定算术及有效精度组合；不把内部精度位暴露为CPU命令端口。外部Command/Completion、context和TileLink布局不变。

## RAM几何与重叠

源vs2的EEW在vv/vf下为32，在wv/wf下为64；第二个向量源仍为32位，目的与FMA的旧vd为64位。分别形成源偏移，读完窄源后恢复目的位偏移，再读取宽累加器或写回，避免把32位索引当成64位目的偏移。

普通宽化算术允许规范规定的窄源最高部分重叠；分数LMUL的窄源不能这样重叠。wv/wf的宽vs2可与目的原地别名；wv的两个显式源EEW不同，不能共享物理寄存器。FMA的旧vd也是64位源，禁止其与任何32位源组重叠，即便窄源位于目的组最高部分。两个32位源之间可别名。

标量vf/wf始终按源SEW32检查FLEN64 NaN boxing；高32位不是全1时用canonical FP32 NaN，不能因目的为64位跳过检查。向量FP32源只取低32位，不要求NaN boxing。

异常标志先累积于指令私有fpFlags，完成接受时才并入fflags；候选RF版本与标志一起发布。flush撤销候选状态，完成等待不得提前更新。原vxrm/vxsat不受这些FP指令影响。

## 验证与限制

独立数值参考调用固定版本、未修改的Berkeley SoftFloat：逐个FP32→FP64转换并保留转换异常，再执行binary64加减、乘法或mulAdd，独立计算结果与标志，不复用HardFloat方程或RTL分段。另有手工已知答案覆盖最小subnormal、最大FP32乘积、精确乘积抵消、NaN、半ULP及定向舍入。

新增单元验证两种宽化精度、原同宽转换/RTZ/宽化归约兼容、非法精度组合、请求精度锁存、反压和撤销；原数值模式另用完整同宽测试矩阵对照。整核逐条检查全部32个向量寄存器、版本、vstart、fflags/frm和整数定点状态，覆盖18种编码、4种合法类型、非法SEW/EMUL、源重叠、mask与重启。精简网表范围有意限定，不能视为全部ISA合规测试。

旧整数宽化乘法与乘加回归曾把本轮新增的FP编码作为负例；对应探针改用仍保留的0x39编码。仅FP配置bad_opcode计数各增2，原命令数、非法总数、整数结果和性能记录仍逐项对照M39。新FP形式另有上述正向数值验证。

monitor ABI1.0，ID=0x4001；现有FP能力位继续表示部分FP支持。标准/深流水浮点配置caps仍0xffffffff，整数配置仍0xfffd7ff3。VLEN、lane、指令容量及VRF容量维持128、1、1和512架构字节。

固定M25家族权重与100ps/段假设，默认两个顶层及四个预设均需≤3.333ns。云端没有器件布局布线或-2速度档校准，不覆盖DSP端点、RAM写、hold、时钟树及IO签核；实际300/500MHz仍需Vivado。结果与SHA绑定见[M40报告](../reports/m40/evaluation.md)。

后续主要缺口：浮点宽窄转换、估算倒数/倒平方根及其余FP形式，扩展访存模式和完整架构/Orbital程序验证。FP16/Zvfhmin等RVA23要求另行跟踪。

[规范与18条官方编码](references/m40-wide-floating-point-v1.0.txt) · [规模参数](m39-configurations-and-fp-transfers.md) · [完整性计划](rvv-completion-plan.md)

复现：`make bootstrap`，`python3 scripts/verify_m40.py`，`python3 scripts/package.py --milestone m40`。
