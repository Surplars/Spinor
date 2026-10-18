# M38：分数乘法与窄化裁剪

本轮补齐ELEN64目标范围内基础V定点指令族最后两组已知实现缺口：vsmul.vv/vx和vnclip[u].wv/wx/wi，共8种标准编码。完整RVV仍受剩余FP、LSU及架构/SoC验证限制，不据此声明misa.V或RVA23合规。验证范围与输入散列以[M38报告](../reports/m38/evaluation.md)为准。

| 指令 | 编码数 | 类型范围 |
|---|---:|---|
| vsmul.vv/vx | 2 | SEW8/16/32/64，22种合法SEW/LMUL |
| vnclipu.wv/wx/wi、vnclip.wv/wx/wi | 6 | 目的SEW8/16/32，源2×SEW≤64，15种合法类型，源EMUL≤8 |

两组均支持mask、vstart、源/目的合法别名、四种vxrm模式和随完成提交的vxsat。prestart、mask与tail保留；VL0或vstart≥VL不更新数据或新增饱和，成功仍清零vstart。非法编码、组对齐和不同EEW源别名在无有效元素时也检查。

## 共享乘法器

vsmul先得到两个SEW有符号数的完整2×SEW乘积，再右移SEW-1、按vxrm舍入并饱和。SEW64使用完整128位部分积；在截取结果前保留guard、sticky与保留位LSB。MIN×MIN的唯一正溢出返回MAX并置vxsat；其余乘积保留精确舍入结果。

IntegerMultiply新增可选fractional配置，目标VPU使用该配置共享原16×16乘积、128位累加和32位校正步骤。分数结果的符号校正使用2倍源操作数，再通过原校正通路完成舍入增量，没有第二个乘法器或新DSP。默认配置保持旧接口和生成RTL；共享版本的普通乘法与高半积仍使用原步骤与周期，实际对照见报告。外部Command/Completion与TileLink端口不变。

## 先舍入再裁剪

vnclip[u]读2×SEW源，移位量取低log2(2×SEW)位；wi使用零扩展uimm5。不能先截取目标SEW再判断饱和。FixedPointLane新增内部模式14/15，沿用三级radix-4移位和8位增量，保留完整宽源舍入结果，再在独立clipCheck阶段判断是否落在目标有符号或无符号区间，最后夹紧并截取。

例如SEW8时，vnclip对255右移1：RNU/RNE舍入得到128，饱和为127并置vxsat；RDN得到127，不新增饱和。负数边界、unsigned最大值及移位0也分别测试。64→32位裁剪保留全部64位，目的SEW64需要128位源，超出ELEN并拒绝。

裁剪复用既有窄化几何：vs2按2×SEW及2×LMUL寻址，向量移位量vs1与目的按SEW/LMUL寻址。目的只能重叠宽源最低部分；两个显式源不能以不同EEW共享物理寄存器。标量/立即数形式在读完宽源后恢复目的bitOffset，避免将宽源偏移错用为写回偏移。跨128位寄存器、最高组、原地写回、mask和非零vstart在架构参考中检查。

饱和先累积到指令私有fixedFlags，在Completion接受时并入架构vxsat；取消丢弃候选数据及私有flags。FP的frm/fflags独立。仍单条指令在途，新指令逐元素复用执行单元。

## 验证与时序边界

Python参考使用精确有符号乘积、数学商余数和目标区间夹紧，不复制RTL符号校正或分段结构。分数乘法测试含8位全部输入对×4舍入模式、64位完整乘积边界和普通mul/mulh/mulhu/mulhsu；裁剪含16→8位全部输入×4模式及宽源边界、移位量扫掠。架构测试逐条读取全部32个寄存器、版本、vstart、vxrm/vxsat和FP状态，并覆盖候选写回及完成等待期间撤销。具体数量和网表覆盖见报告。

Monitor ABI仍1.0，ID=0x3801，caps=0xffffffff；bit30表示vsmul，bit31表示vnclip[u]，此前bit0..29保留。UIO工具仍只提供监控，不是计算任务驱动。

云端继续使用Yosys xcup、Icarus RTL/FPGA原语功能仿真、局部SAT与RapidWright家族表。固定M25权重和100ps/段假设，两个顶层门槛均为3.333ns；未布局、未按-2速度档校准，DSP端点、RAM写时序、hold、时钟树和IO等不在签核范围。实际300/500MHz需Vivado验证，不能继承M31结果。

[规范与8条官方编码](references/m38-fractional-and-clip-v1.0.txt) · [完整性计划](rvv-completion-plan.md)

复现：`make bootstrap`，`python3 scripts/verify_m38.py`，`python3 scripts/package.py --milestone m38`。
