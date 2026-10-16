# M14 时序路径优化

## 整数乘法

acc/term四个32位字在每次累加时旋转，从固定位置0读数，将结果放到位置3；四次后恢复原顺序。避免动态word索引读/写与进位链串联，不增新状态、数据寄存器或整组向量快照。对加法使用扩展低位，Cat(x,1)+Cat(y,carry)的高33位等于x+y+carry，避免两个串联加法器；高位乘法的校正亦使用此形式。

SEW8/16/32/64低位乘法延迟仍7/7/25/97，高位乘法均增加4周期。仍是容量一、16×16 DSP复用，不是每周期一个元素。

## FP64与转换

FP64原有输入规格化链的前导零计数放在recode，移位/指数编码放在已有recodeFinish；普通FP64请求没有新增周期。FP32保留M13的RawFloat规格化注册，普通浮点add仍31周期。

浮点转整数的toIntRecode只记录前导零，新增toIntPack计算精确recFN，增加一个周期；fromInt路径不变。使用本地IeeeRecode辅助函数，来源为固定HardFloat rawFloatFromFN/recFNFromFN的公式适配，完整BSD版权/许可保留于源码，第三方源码未修改。

辅助函数的FP32、FP64输出通过Yosys SAT与固定HardFloat组合编码器比较，覆盖全部64位输入图样。该证明只覆盖组合编码，不证明流水状态机；数值、flags、flush/reset及背压另由独立SoftFloat和映射后检查覆盖。

## 时序模型与范围

沿用M13同一条件预算脚本和家族表；50/100/200ps每段连线及100ps建立预算是显式假设。未覆盖DSP端点排除，不含速度等级标定、布局布线、实际引脚、时钟、hold或RAM写setup。不得把预算余量当作WNS或报告通过300/500MHz。

本轮没有新ISA、请求队列、多请求窗口、实际Valence接入或Vivado实现。LSU与M13相同，仍逐元素提交、故障前缀和延迟停止。

make verify-m14 / make package-m14复现。SAT独立命令为python3 scripts/prove_recode.py，生成build/recode-proof；预算基线使用包内archive/m13/synth-LishiVpuMemory/mapped.json。
