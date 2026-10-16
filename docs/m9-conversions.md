# M9 同宽整数与浮点转换

新增 `vfcvt.xu.f.v / vfcvt.x.f.v / vfcvt.f.xu.v / vfcvt.f.x.v` 和 `vfcvt.rtz.xu.f.v / vfcvt.rtz.x.f.v`，仅 SEW32/64 的同宽形式。使用 RVV OPFVV、funct6=0x12、vs1 子码 0/1/2/3/6/7；vs1 为子码而非源寄存器，不读取它。

保留 mask、tail/prestart、源目标别名和版本原子提交。普通转换使用 frm 的五种合法舍入模式；RTZ 固定向零，不依赖 frm，因此 frm=5/6/7 时仍可执行 RTZ 形式。异常按 RISC-V 饱和结果与 NV/NX 规则处理，转换产生的标志仅在整条指令完成接受时合入 fflags，flush 不泄漏标志。

整数转浮点使用低/高 32 位取绝对值、逐位规格化和分级舍入，容量为 1，延迟随数值变化。浮点转整数在 IEEE→recoded 格式之后寄存，再进行寄存的对齐、舍入决策与低/高 32 位进位。修正了综合器将逐位增量前缀合成长 LUT 链的风险，相关增量器按局部 16 位进位分组。

核心算法继续使用固定版本 HardFloat，并为派生文件保留完整许可。独立 SoftFloat 计算舍入与标志；默认 SoftFloat 的整数 invalid 结果特化不符合 RISC-V，因此测试包装器在 NV 时按 RISC-V 明确选择 signed/unsigned 的饱和值，未修改 SoftFloat 源码。另用手工常量锚点检查 NaN、正负范围边界及基本转换。

未实现宽化/窄化转换、FP32↔FP64、FP16/Zvfhmin、round-to-odd 窄化形式。转换保持单元素在途，不把 M8 的基础整数吞吐结论扩展到 FP 转换。
