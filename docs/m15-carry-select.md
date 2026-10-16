# M15 并行分段算术

## 除法条件取反

32位字先按negative条件异或，再分别执行低16位和高16位的增量。高段进位为cin且低段全1，最终进位为cin且整个翻转字全1；不需要从低段加法输出串行传播到高段。输入a/b取绝对值和输出符号恢复均使用同一生产辅助函数。状态和寄存器不变。

## CarrySelect

CarrySelect.add对宽度超过16的加法，用低16位算真实进位，高段并行计算carry0/carry1结果，最后选择；较短宽度直接加法。扩展低位将cin合入一次加法。保留结果最高进位，覆盖除法33位试减、整数乘法32位累加/校正、FP共享FMA的32/11位求和和转换输入32位条件取反。

这里没有新增流水级或RAM/整组向量快照。乘法仍SEW64低/高97/101周期；除法/余数仍4×SEW+8，即40/72/136/264；普通FP add仍31周期，转换延迟与M14相同。外部仍容量一，没有多请求窗口或新ISA。

## 证明与仿真

GenerateDividerProof直接调用生产IntegerDivide.negateWord纯函数和CarrySelect.add，参考为直接按位异或及数学扩展加法。Yosys SAT证明：取反32位字、negative、cin全部2^34组合；11/16/17/32/33位加法全部输入组合且包含carry-out（33位加法为2^67组合）。仅证明组合身份，不覆盖状态机、时序或物理实现。

流水顺序、除零、带符号溢出、数值、flags、tag、背压、flush及周期由独立Python任意精度整数/SoftFloat和映射后仿真另行检查。先前的IEEE重编码等价证据按输入SHA复用，编码算法未改动。

## 云端时序范围

相同RapidWright家族表与50/100/200ps每段连线假设作M14/M15对照。仍是未布局条件预算，不含-2标定、真实连线/引脚、DSP覆盖、时钟、hold及RAM写setup。模型中300MHz预算余量为正也不能声明实际通过。没有新Vivado或SDF。

make verify-m15 / make package-m15复现。全输入证明：python3 scripts/prove_divider_word.py。基线网表随包提供于archive/m14/synth-LishiVpuMemory/mapped.json；当前网表随包提供于build/synth/LishiVpuMemory/mapped.json。
