# CPU—Spinor 提交协议

本协议适用于同一时钟域的 `SpinorVpu` 与 `VpuHostBoundary`。首次集成步骤和连接示例见[接入指南](integration.md)。边界容量为一条不可撤销指令，CPU 的取指、ROB、权限和全局退休由宿主实现。

## 指令与所有权

`Command` 含 32 位 instruction、64 位 scalar/scalar2/avl 和 **80 位 token**。token 的索引、tag、epoch 由宿主打包，边界原样保存和比较；不能截断为早期接口的位宽。

边界仅在以下条件同时成立时接受 offer：空闲、无 stop/协议错误、headValid、headToken 与 offer token 完整匹配、olderMemoryDrained 和 olderFpDrained。CPU 在此之前还须完成 VS/FS、权限、数据依赖与写回端口检查；边界无法推断这些条件。

`command.fire` 后保留 token、instruction、访存类别和所有者，直至 `reply.fire` 或明确的算术取消。即使前端恢复，CPU 也必须保留 PC 和错误归属，不能复用该身份对应的退休槽。

## 完成与发布

`reply.ready` 是最终授权，控制底层 `completion.ready`。普通算术、VSET 和 CSR 的候选向量版本、CSR 更新与 CPU 标量结果应在同一完成握手边沿发布。完成被反压时保持 payload，不能先写 CPU 寄存器后再丢弃 VPU 完成。

`VpuHostReply` 包含原 Completion、memory、stopped、exception、cause、tval、rawMemoryCause 和 element。CPU 根据回显原指令选择 GPR/FPR 目的；`vfmv.f.s` 对 f0 也返回有效写回，SEW32 返回值已按 FLEN64 NaN-box。

访存允许逐元素提交前缀，其副作用不受普通算术的候选版本回滚保证覆盖。异常/停止回复禁止标量写回；最终异常优先级、中断 cause 和全局退休仍由 CPU 决定。

## stop、取消与总线排空

- 算术 stop：向 VPU 发 flush，经 `canceled.valid` 返回原 token；候选状态丢弃，该指令不产生 reply。
- 访存 stop：保留 active 和 token，等待已发布 A/D 排空及最终 completion/status。已发 store 不可撤销，不能按算术取消处理。
- stopped 回复：CPU 保存原 PC、前缀状态和操作数，决定中断/恢复后再授权 reply；stopped 不能直接当作成功退休。
- 若 stop 到达时指令已完全完成，可以返回普通完成，不能根据 stop 电平自行伪造中断状态。

reset 须在接口静止时进行，或与 VPU、宿主和互连协调联合复位；只复位边界无法排空旧 D 或恢复 store 的错误归属。

## 异常映射与协议错误

| 条件 | CPU cause | tval |
|---|---:|---|
| 非法指令 | 2 | 零扩展原始 instruction |
| load 不对齐，原始 LSU cause=4 | 4 | LSU address |
| store 不对齐，原始 LSU cause=6 | 6 | LSU address |
| 其他当前 load fault | 5 | LSU address |
| 其他当前 store fault | 7 | LSU address |

当前没有页故障或虚拟地址 tval 映射。stopped 不生成中断 cause；调试 watchpoint 也不能作为可截短的普通 FOF 访问错误传入。

Completion 必须与保存的完整 token 和 instruction 一致；访存完成须同时提供 memoryStatus，算术完成不得带 memoryStatus。无所有者、身份不匹配或元数据错位会触发粘滞 `protocolError`，阻止接收新命令和消费完成。不得靠吞掉错误完成解除状态，因为 completion.fire 本身可能提交 VPU 架构状态。恢复须停机、排空并协调复位。

## 操作数与恢复单位

| 指令类别 | scalar | scalar2 | vstart 单位/恢复规则 |
|---|---|---|---|
| 算术 `.vx` / `.vf` | GPR / 完整 FPR 位模式 | 不使用 | 按操作定义解释；特殊归约、prefix 等有非零起点限制 |
| `vsetvl` | 按原指令使用 | vtype 源 | 完成清零 vstart |
| 单位步长访存 | rs1 原物理基址 | 不使用 | 普通元素；故障/停止保留已提交前缀 |
| 跨步访存 | rs1 原物理基址 | rs2 有符号字节步长 | 普通元素；编码 rs2=x0 强制零步长 |
| 索引访存 | rs1 原物理基址 | 不使用 | 索引从 vs2 组读取，为零扩展字节偏移 |
| 分段访存 | 原基址 | 跨步时为字节步长 | 以整段为单位，当前段可能已有字段前缀；从该段字段0恢复 |
| 整组访存 | 原基址 | 不使用 | 按编码 EEW 计数；store EEW 固定8；使用 EVL |
| mask 访存 | 原基址 | 不使用 | 按字节计数，传输 ceil(VL/8) 字节 |

恢复始终传原基址和原指令，不能再次加上 vstart 偏移。地址计算按模 2^64；索引不再乘数据宽度。所有形式当前仅支持物理普通 RAM。

FOF 元素0错误按异常处理且保持原 VL；后续元素错误可能正常完成并缩短 VL。消费最终 completion/status 后，后续算术和 CSR 读取必须看到新 VL；即使无 RF 更新，VL 变化也须由宿主管理 VS dirty。分段截短点的部分字段不属于新 VL 的有效体。

## FCSR、上下文与 Linux

共享标量/向量 FCSR 时选择 `SpinorParams(hostFcsr=true)` 或 `--fcsr-owner host`。CPU 提供已提交 frm/fflags；VPU 接收命令时锁存 frm，只返回本条成功 FP 指令产生的 flags。CPU 在 completion.fire 且 flags.valid 时 OR 合并，同一身份、同一退休边沿。FCSR 的 0x001/0x002/0x003 CSR 留在 CPU；误转发到宿主模式 VPU 会报非法。见[宿主 FCSR 细节](m56-host-fcsr.md)。

context 仅在 CPU/边界/VPU/总线共同空闲后独占使用，不能与普通命令或恢复竞争。monitor clear 只清统计，不授予上下文所有权。[上下文 helper](../software/context/README.md)保存 576 字节镜像；host 模式的 execute 回调将 FCSR 访问路由到 CPU。

原生 RISC-V Linux 仍需真实 CPU 侧的 VS/FS、上下文切换、异常/中断、保护/翻译和一致性接入及对应验收。其他处理器执行向量作业还需队列/代理与驱动；monitor UIO 只提供观测。

## 证据与兼容接口

当前数字运算和访存验证见[M60 报告](../reports/m60/evaluation.md)，宿主边界与 FCSR 的验证范围见[M56 报告](../reports/m56/evaluation.md)。这些使用独立宿主模型，不能替代实际 CPU 或 Linux 验收。

旧 `ValenceBoundary` 是早期算术实验适配器，flush 会直接丢弃所有者，不适用于当前 LSU；新接入使用本页的 `VpuHostBoundary`。整理前的协议原文保留在[文档快照](../archive/docs-m60/source/docs/cpu-spinor-contract.md)。
