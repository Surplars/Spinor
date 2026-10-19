# M54：FP16 最小转换与 ISA 支持边界

新增 SEW=16 的 `vfwcvt.f.f.v`（FP16→FP32）和 `vfncvt.f.f.w`（FP32→FP16）。
这是 [Zvfhmin 的两种转换定义](references/m54-zvfhmin.adoc)，不包含完整 Zvfh 的
半精度加乘、除法、FMA、比较或归约。FP32/FP64 的既有运算和整数 16 位转换保留。

RVA23U64 把 V、Zvfhmin、Zvbb、Zvkt 列为强制扩展，见
[冻结 profile 文本](references/m54-rva23.adoc)；完整 Zvfh 列为额外选项。基础 V
与 RVA23 是不同层次的声明。当前 VPU 尚无 Orbital 整核 ISA/操作系统合规声明。

## 硬件与接口

复用原有 widen/narrow 几何、寄存器 RAM、调度、元素读写和转换状态机。内部模式
5/6 原先用于 int16→FP32 / FP32→int16，现在还定义相应 FP16 浮点转换。
half 原始数先无舍入地扩成共享 recoded 格式，保留 NaN payload/signaling 状态；
新增 `StagedRound(11,64,5,11)` 直接舍入到 binary16，避免先舍入到别的格式。

支持 5 种标准 frm、规范 NaN、NV/OF/UF/NX 累积、次正规、signed zero、掩码、
tail/mask undisturbed、非零 vstart 与无工作量完成。SEW16 的 round-to-odd 转换及
其他尚未定义的半精度操作继续拒绝；frm5..7 拒绝，整数配置拒绝全部浮点操作。
组对齐、扩缩宽重叠规则、LMUL 与最大 EMUL 限制沿用标准转换检查。

VLEN128/ELEN64、单 lane、单向量指令在途。没有新增 RF 快照、DSP 或 CPU 耦合。
monitor 实现号更新为 **0x5401**，ABI1.0、原能力位和 MMIO 布局不变；生成 manifest
新增 `fp16_min_conversions`，整数预设为 false。上下文 ABI1 的 576 字节格式不变。
能力位本身没有新增“完整半精度算术”声明；宿主应结合实现号/manifest 使用。

## 当前支持清单

| 范围 | M54 状态 | 尚缺的系统条件或证据 |
|---|---|---|
| 基础整数/定点/掩码/置换/归约 | 已有实现及独立执行样本 | 非所有操作数/异常相位穷举 |
| FP32/64 计算、转换、归约 | 已实现，保留差分/数值验证 | 与 CPU 的 FCSR/FS/退休整合 |
| load/store、分段、FOF、整组/mask | 已实现，普通物理 RAM 测试 | VM/PMP、真实 MMIO、缓存一致性 |
| VL/vtype/vstart、定点/浮点 CSR | VPU 自身接口已实现 | CPU VS/FS、特权陷阱/上下文联动 |
| Zvfhmin 的 SEW16 两种转换 | 本轮已实现并验证 | 依赖的整核扩展声明仍需集成审计 |
| Zvbb | 尚未实现该扩展 | 逐指令实现及独立验证 |
| Zvkt | 未声明，尚待专门审计 | 按规范要求核查数据相关延迟，不能靠功能测试代替 |
| 完整 Zvfh、BF16、向量 crypto | 尚未实现/声明 | 分别确定目标范围 |
| Linux/Orbital 接入 | 保持 CPU 独立，已有命令和上下文契约 | 真实退休、异常、锁/排空、权限和作业驱动 |

原 375 种基础编码的目录数不会因这次功能增加变成 377：两条编码之前已有 SEW32
定义，本轮新增 SEW16 的合法定义。编码目录覆盖不是 ISA 合规百分比，也不代表
RVA23 的全部强制扩展完成。现阶段可以使用已支持的裸机/内核，不能让通用编译器
或 Linux 按尚未完成的完整 profile 自由选择指令。

## 验证和时序

数值单元以未修改的 Berkeley SoftFloat 为独立参考；公共顶层使用锁定上游 Spike
并显式启用 Zvfhmin，无语义补丁。算术、访存、扩展边界、保留编码策略、上下文和
monitor 都在新硬件重跑。非零算术 vstart 及 flush 由独立 SV/SoftFloat 覆盖，
不把 Spike 默认禁止非零算术 vstart 的行为改成 DUT 预期。

新 half rounder 还通过 10 步有界 SAT，比较全部任意 raw bits、模式及特殊标志，
带 done 见证避免空证明；这是局部舍入器等价性，不是整个 VPU 的形式证明。

默认公共顶层与计算/访存顶层重新综合及检查固定 M25 权重、100ps/link 的预算：
3.300ns / 3.232ns，均≤3.333ns。模型继续排除 DSP 影响端点，不含实际布线/时钟，
未按 ZU15EG-2 校准，不是器件 STA。**M53 的本地 +0.090/+0.042ns 结果仅适用于
旧 RTL，不能自动签核 M54 的 300MHz**；M54 的 300/500MHz 物理结果仍未知。

默认映射为 23,227 逻辑 LUT、13,359 FF、9 DSP，较 M53 Yosys 基线 +21 LUT/+155 FF；
RAM32M16×6、RAM64M8×32 不变。Vivado 的实际 BRAM/DSP 映射可能不同。
详见 [完整执行与证据](../reports/m54/evaluation.md)。

## 使用与复现

在已有锁定工具及 M53 产物的环境运行 `python3 scripts/verify_m54.py`；
`--check-only` 核查本轮证据和已归档的历史源码。全部新产物位于 `build/m54`，
M53 原 RTL/网表及本地报告保留；历史变动的 4 个 Scala 文件从 `archive/m53/source`
核对，而不是将新代码伪装成旧版本。首次工具准备仍按项目原 bootstrap 流程。

`software/programs/half-conversions.c` 是实际 RVV intrinsic strip-mining 示例。
Clang19 以 `-march=rv64gcv_zvfhmin` 可生成两种转换和向量 load/store；本轮检查了
编译输出，未把它称为真实 Orbital/Linux 程序执行。
