# M56：宿主管理 FCSR，VPU 只返回本条指令的异常标志

本轮没有扩展 CPU 取指、ROB、标量执行或特权状态。Spinor 增加可选的宿主 FCSR
接口，使 Orbital 的标量 FPU 与向量 FPU 使用同一份架构 FCSR。VPU 内保留执行
所需的舍入快照和指令内异常累积，不再保存第二份架构 fflags。

## 选择与端口

```scala
val spinor = Module(new SpinorVpu(config = SpinorParams(hostFcsr = true)))
```

```bash
./mill Vpu.runMain vpu.GenerateConfigured --out build/host --name SpinorVpu --preset standard --fcsr-owner host
```

`--fcsr-owner standalone` 是保留的默认值，四种既有独立预设的 SV 与变更前逐字节
一致。`host` 支持 standard/deep 浮点预设；integer/host 组合会在 elaboration 拒绝。
manifest 明确提供 `fcsr_owner`、`fflags_delta_port`；宿主版 monitor ID 为 **0x5602**，
独立版保持 **0x5501**。monitor ABI1.0 与原能力位布局保持。

宿主模式在 `io.core` 增加 `fcsrHost`：

| 信号 | 方向 | 合同 |
|---|---|---|
| frm[2:0] | 宿主→VPU | 架构 frm；在接收算术命令的 command.fire 边沿取快照 |
| fflags[4:0] | 宿主→VPU | 宿主架构 flags，仅用于状态/monitor 观察 |
| flags.valid | VPU→宿主 | 当前完成属于成功的向量 FP 执行；没有独立 ready |
| flags.bits[4:0] | VPU→宿主 | 本条指令自身产生的累计异常；无有效更新时为零 |

CPU 应在 **core.completion.fire && fcsrHost.flags.valid** 时执行
`cpu.fflags_next = cpu.fflags | flags.bits`，与向量完成同一退休边沿。
不能见到 valid 就提前合并。使用 VpuHostBoundary 时仍由其完整 token/身份检查、
reply.ready 和异常处理授权 completion；不能绕开边界单独消费 flags。

flags 包含本条指令的全部新增异常，不能用旧/新 sticky flags 的 XOR 计算。例如
入口已置 NV，本条又产生 NV，flags.bits 仍须包含 NV。反压时 flags 与完成保持；
非法指令、取消和内存完成不会发布此更新。合法 VL0 或全 masked FP 操作可返回零
flags。FP 位搬运不产生 flags；FS/VS dirty 仍由 CPU 按指令和架构规则处理，不能
仅看是否有非零异常。

`io.core.frm/fflags` 与 monitor 在宿主模式观察宿主输入，执行单元使用锁存的 frm。
输入扰动测试验证快照，但不授权年轻标量 CSR 指令越过尚未退休的向量指令。
CPU 仍须在接收前排空旧标量访存/FP 工作，管理权限、VS/FS、异常优先级和全局退休。

## CSR 与上下文

宿主模式不接收 0x001/0x002/0x003 的 CSR 指令：包括零源读取，意外转发均报非法。
这些访问必须由 CPU 的唯一 FCSR 所有者处理。vl/vtype/vstart/vxrm/vxsat 等向量
状态仍由 VPU 管理，按原命令/提交接口访问。

576 字节上下文镜像 ABI1 保持。使用 portable C helper 时，execute 回调应将上述
三个 CSR 路由到 CPU 所有者，其余操作送 VPU；acquire/release 仍须覆盖 CPU 与 VPU
共同排空和所有权。已有两种宿主预设的完整镜像/恢复/失败注入测试验证这种路由。
这是独立 CPU 所有者模型，尚未修改或连接实际 Orbital，也不是 Linux 驱动验收。

ARM 作业模式可由驱动维护每作业的 RISC-V 格式 FCSR；它不自动等同于 ARM 的
FPCR/FPSR。ARM 作业队列、驱动和异常格式转换仍待实现。

## 地址流水线与时序

宿主模式综合暴露原 LSU 地址进位路径超出条件预算。本轮在单位步长地址计算的
低 16 位与中间 16 位之间增加一个状态，复用 address/addressCarry；每次单位步长
元素地址生成增加一拍。跨步/索引的 16 位加法改成两个 8 位 carry-select 段，拍数
保持。无新增整组寄存器快照，仍用 RAM 保存向量状态。

默认宿主公共顶层 Yosys xcup：**24,247 逻辑 LUT、13,882 FF、9 DSP**，相对 M55
默认版 +63 LUT/-6 FF，RAM64M8×32、RAM32M16×6 保持。两个宿主顶层的固定 M25
权重、100ps/link 预算均为 **3.300ns**，通过≤3.333ns 条件门槛。

这是未布局布线、未按 -2 校准且排除 DSP 影响端点的模型；主输入/输出路径也不在
此门槛覆盖内。FCSR 侧带与 CPU 的实际连接需 SoC STA，M56 的实际 300/500MHz
仍未知。Deep 完成功能与延迟抽样，未另声明其完整器件时序。

## Zvkt 审计范围

冻结 [Zvkt 规范](references/m56-zvkt.adoc) 明确排除浮点算术、除法、存储、归约、
压缩等家族；不能把它们的数据相关时长笼统当作 Zvkt 的否决条件。早期 M55 说明
对此的表述过于笼统，本轮以规范清单为准。`vfslide1up/down.vf` 是明确列出的
搬运例外。标量 Zkt 属于 CPU，向量 Zvkt 才是本次 VPU 审计范围。

391 种现有目录编码中按清单明确分出 164 种 required、226 种 excluded；`vmv.x.s`
因 copy 列表的速记文字需进一步核对，列为 review 并保守额外测试。没有把排除项
标成未实现，也未声称完整 Zvkt 合规。

两个宿主预设各对 **165 种编码、22 种 SEW/LMUL、3 种掩码配置、4 种数据模式**
测量 command 接收至 completion.valid 的周期。每个组固定控制参数和总线条件，
变化活动/非活动数据；gather 索引及 slide amount 按规范豁免保持，merge 的选择
数据另作变化。每预设 43,560 个样本，合法组 9,783，全部数据模式的完成时长一致；
非法几何组也检查拒绝与时长一致。该检查不比较数值正确性，数值由独立差分矩阵
另行验证；有限样本不构成全输入 DIEL 证明或 Zvkt 合规认证。

完整证据、失败尝试与复现入口见 [M56 报告](../reports/m56/evaluation.md)。
