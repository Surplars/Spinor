# M55：Zvbb 位操作与 300 MHz 条件预算

Spinor 的四种大小预设均增加 Zvbb 的全部 10 类操作、16 种规范编码。仍是
VLEN128/ELEN64、单 lane、单向量指令在途，整数元素可以在固定延迟流水线内重叠。
这次没有增加指令级乱序或多发射，也没有修改 Orbital/Valence。

| 操作 | 格式 | 实现 |
|---|---|---|
| vandn | vv/vx | 与非 |
| vbrev8 / vbrev / vrev8 | v | 字节内反转、元素位反转、元素字节反转 |
| vclz / vctz / vcpop | v | 前导零、尾随零、置位计数 |
| vrol | vv/vx | 元素循环左移 |
| vror | vv/vx/vi | 元素循环右移，vi 使用 6 位无符号立即数 |
| vwsll | vv/vx/vi | 零扩展后左移，目的 EEW=2×SEW |

普通操作支持 SEW8/16/32/64。vwsll 的源 SEW8/16/32、目的 SEW16/32/64；
SEW64 扩为 128 位、目的 EMUL>8、组未对齐或不允许的重叠均拒绝。
支持掩码、tail/mask undisturbed、VL0、非零 vstart、跨寄存器组和 flush。
这说明上述操作集合已经实现，并不等于完整 V/RVA23 的合规声明。

规范来自冻结的 [Zvbb 扩展文本](references/m55-riscv-crypto-vector-zvbb.adoc) 及
逐操作文本；[来源与散列](references/m55-sources.json) 保留上游 URL。
指令参考是固定修订的未修改 Spike，新增适配器只更改启用的 ISA 字符串。

## 数据通路与接口

扩宽左移复用原 RAM 寄存器文件、几何检查与分段移位器；单目选择字段不作为 vs1
寄存器读取。新位操作旁路与原整数数据通路并行计算，共用原信用计数和响应队列。
循环移位先将有效元素复制到 64 位，再经过三级 radix-4 旋转，避免各级重复 SEW
选择；计数先在字节内计算，再分级归并。32/16 位分段配置的 ALU 延迟仍为 6/7 拍，
II=1；系统吞吐还受串行 RAM 读写、调度和指令级单在途限制。

为切断综合后发现的浮点估算长路径，浮点转换模式和输入宽度在接纳指令时锁存。
不增加新执行阶段，不更改结果舍入语义。已有 FP32/64、Zvfhmin 转换重新回归。

monitor 实现号 **0x5501**，生成 manifest 增加 `zvbb:true`，四预设均提供。
monitor ABI1.0、能力位布局、TileLink 接口和上下文 ABI1 的 576 字节格式保持。
现有能力位已用完，因此通过实现号/manifest 识别新增集合；不把既有能力位重新解释。

## 参考模型的边界

基础 V 规定：同一源寄存器在同一指令以多个 EEW 读取是保留编码，mask 的 EEW=1。
Spinor 拒绝 masked 数据源与 v0 的这种别名；固定 Spike 会执行其中一些情况。
这些情况单独用规范拒绝策略验证，不纳入 Spike 一致性成功计数。扩宽/未对齐、非法
SEW/EMUL 等其余边界则保留在独立模型的差分矩阵中。

固定 Spike 也不允许非零算术 vstart。非零 vstart 使用独立 Python 的整寄存器/CSR
参考验证，未给 Spike 打补丁。逐周期 flush 检查真实公共顶层的全部 64 个 RF 字，
包含执行与持有完成阶段，确认未提交结果不进入架构状态。

## 资源与时序

默认公共顶层 Yosys xcup 为 **24,184 逻辑 LUT、13,888 FF、9 DSP**，较 M54
+957 LUT/+529 FF；RAM64M8×32、RAM32M16×6 保持。整数/Deep 预设本轮有功能与
独立 ALU 映射验证，未据此声明每个完整预设都有器件 PPA 结果。

固定 M25 权重、100ps/link：公共顶层 **3.292ns**、计算/访存顶层 **3.232ns**，
均≤3.333ns。初次公共顶层 3.368ns 未过，寄存浮点宽度控制后重新综合过门槛；
没有改变预算权重。模型排除 DSP 影响端点，不含实际布线与时钟，不是 STA/SDF，
未按 ZU15EG-2 校准。**M55 的实际 300/500MHz 仍未知**；M53 本地已过 300MHz
的结果只适用于当时 RTL。实际寄存 DSP 延迟表不适用于当前 Yosys 的无内部寄存 DSP。

## 程序与后续

`software/programs/bit-features.S` 提供真实 strip-mining 位特征处理、32→64 位扩宽
移位两个例程，接口见同名头文件。Clang19 可汇编 Zvbb；固定版本未提供本轮尝试的
C intrinsic 名称，因此示例使用汇编，并核查目标文件的实际 match/mask 编码。
这是编译/编码检查，尚未在 Orbital 或 Linux 执行该程序。

下一步优先做 Zvkt 所需的操作数相关延迟审计，以及基础 V 的剩余异常/系统边界。
已有除法与浮点归一化等路径存在数据相关时长，不能凭这次新 ALU 的固定延迟宣称
Zvkt。真实退休、VS/FS/FCSR、PMP/页表/一致性和 Linux 驱动仍需与宿主接入验证。
完整 Zvfh、BF16、向量 crypto 和更大 VLEN/多 lane 不在当前实现声明中。

完整测试范围和复现见 [M55 执行报告](../reports/m55/evaluation.md)。
