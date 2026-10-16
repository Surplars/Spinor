# ZU15EG-2 M3：共享 FP32/FP64 接入

**已将第一组同宽浮点运算接入 RAM 向量引擎；完整 RVV/RVA23、Valence 整核接入、真实器件时序和 bitstream 仍未完成。**

构建仍为 Mill 1.1.7、Scala 2.13.18、Chisel 7.16.0 / firtool 1.160.0。
开源评估使用 Yosys 0.70+16、Icarus 14.0；独立数值参考使用固定版本 Berkeley SoftFloat。

## 实现范围

- FP32/FP64：vfadd/vfsub/vfmul/vfdiv、反向 vfsub/vfdiv、vfsqrt。
- 八种融合操作：vfmadd/vfnmadd/vfmsub/vfnmsub，以及 vfmacc/vfnmacc/vfmsac/vfnmsac。
- vfmin/vfmax、vfsgnj/vfsgnjn/vfsgnjx、vmfeq/vmfne/vmflt/vmfle、标量形式 vmfgt/vmfge、vfclass。
- 支持对应的 vv/vf 形式；sqrt/class 为一元 .v，总计 48 种合法编码形式。
- frm/fflags/fcsr CSR、五种舍入模式、RISC-V canonical NaN、非规格化数与异常标志。
- 复用原来的 LMUL、mask/tail/prestart、版本表和完成背压；标量 vf 的 FP32 操作数按 FLEN64 检查 NaN-boxing。

## 资源共享与提交

一个 53-bit FMA 通路同时处理两种精度；FP32 在输入侧精确扩展并保留 signaling NaN，
原始结果直接舍入到目标精度，避免先舍入到 FP64 再转 FP32。加减用乘数 1，
乘法加一个与乘积同号的零以保留 -0；除法与开方共用一个迭代单元。
乘积、四段 32-bit 对齐加法、规格化、舍入均有寄存器边界；单元素在途。

融合操作的旧 vd 从已提交 RAM 读取；候选结果写入另一版本。
元素产生的 flags 先在指令内 OR 累积，只有 completion.fire 才与寄存器版本一起提交。
mask 跳过、tail、prestart 元素不参与运算；flush 同时丢弃候选结果、待提交 flags 和迭代状态。

当前独立原型持有一份 FCSR 并支持相应 CSR 指令。整核接入时必须与 Valence 标量 FP 的
**同一份架构 FCSR** 协调，接入其 VS/FS、dirty、权限及退休流程；当前尚未实现这些核级连接。

## 资源映射

Yosys `synth_xilinx -family xcup`，OOC，无 IOB/时钟缓冲。以下不是 Vivado 布局后占用。

| 候选 | 逻辑 LUT | FF | DSP48E2 | 存储 LUT | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|---:|
| FloatingPointLane | 5937 | 1267 | 12 | 0 | 0 | 0 |
| RamVectorFp | 9090 | 3330 | 12 | 296 | 32 | 5 |
| RamVectorFpNoDsp | 15227 | 3330 | 0 | 296 | 32 | 5 |

DSP 候选较全 LUT 乘法候选减少 6137 个逻辑 LUT，保留 12 个 DSP48E2。
两者的数据阵列继续映射到 RAM，没有恢复整组 FF 快照。
存储 LUT 已单列；RAM64M8/RAM32M16 每个按完整单元 8 个 LUT 位置计数。
全 LUT 候选仅作资源对照；本轮映射后功能检查覆盖的是原生 DSP 候选。

## 独立检查

- 数值单元：6811 组，FP32/FP64 × 五种舍入模式 × 全部已实现数值操作，52 个已知答案锚点。
- 逐位对照数据与 NV/DZ/OF/UF/NX，含 NaN、±0、subnormal、overflow、融合抵消和半 ULP。
- 任意完成背压；85 个阶段撤销/复位情形；注入错误结果的负对照被拒绝。
- RAM 向量引擎：1649 条命令、7176 次寄存器读检查，含 219 次 CSR、9 种合法 FP SEW/LMUL 组合。
- 指令级检查源/目的别名、八种融合操作、NaN-boxing、mask/tail/vstart 不产生多余 flags、非法舍入/SEW/编码、12 次撤销。
- FP 开启时的整数回归：789 条命令、2968 次读检查。
- **含 12 个 DSP48E2 的映射网表通过同一组 1649 条命令，仿真周期数与 RTL 同为 95064。**
- DSP 单元使用公开的 Apache-2.0 Xilinx Unisim DSP48E2 功能模型，未修改模型；其余映射单元使用 Yosys 功能模型。
- 数值参考是独立 SoftFloat；HardFloat 自身及其上游 testbench 没有被当作黄金模型。

## 时序评估及限制

**FP 的 300/500 MHz 均未验证。映射后功能仿真不是 SDF/器件速度仿真；M2 的整数参考延迟结果不能套到 FP。**

| 候选 | 最长数据单元跳数 | 最长控制单元跳数 | 最大非时钟扇出 |
|---|---:|---:|---:|
| FloatingPointLane | 41 | 22 | 302 |
| RamVectorFp | 41 | 22 | 305 |
| RamVectorFpNoDsp | 41 | 22 | 305 |

跳数不是 ns/MHz。DSP 内部寄存器参数均为 0 才允许进入该组合图；DSP 和 RAM 读各按一个未校准单元计数。
目前最长数据链起于 FMA 后处理的 doSubMags，包含 28 个逻辑 CARRY4 和后续规格化逻辑。
这明确指出了继续分割的重点；已有乘加外部流水并没有消除 HardFloat 后处理内部的长链。
迭代除法/开方、规格化、舍入及控制路径也须在真实器件实现中继续评估，不能据本报告宣布 300 MHz 已关闭时序。

## LSU 结构选择

LSU 是 Load/Store Unit。计划让 VPU 具有独立向量 LSU 前端，负责元素地址、mask、
请求拆分和故障元素定位；通过宿主接口共用 CPU 的地址翻译/权限、缓存和总线，协调访问顺序。
当前未实现向量 LSU、访存故障/FOF 和可重启的部分提交。非故障算术的整条原子翻转不能替代这些语义。

## 尚未完成

浮点/整数转换、FP 宽化/窄化、归约、估算指令、FP16/Zvfhmin；剩余整数操作、向量 LSU、
标量/向量 FCSR 统一、精确异常及 Valence 核级验证、CDC、器件布线和板测。
当前不能发布完整 V/RVA23 合规声明。

## 复现

- `make bootstrap`；`make verify-m3`；`make package-m3`。首次另下载并校验固定版本 SoftFloat。
- [源代码/RTL/网表/工具参考 SHA-256 与结果](receipt.json)
- [数值单元结果](fp-lane-results.json)、[向量 RTL](fp-vector-results.json)、[DSP 网表](fp-vector-mapped-results.json)
- [架构合同](../../docs/architecture.md)、[归档 M2 报告](../../archive/m2/reports/evaluation.md)
