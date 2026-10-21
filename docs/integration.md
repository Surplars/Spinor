# Spinor 接入指南

本指南面向当前 `vpu.SpinorVpu` 顶层。接口与宿主 CPU 的内部 ROB、寄存器文件或总线库类型解耦；接入侧提供字段转换和提交授权。所有直接连接默认处于同一时钟域。

新工程若需切断CPU/总线组合路径，优先阅读[寄存隔离顶层](m61-isolation.md)，生成`SpinorIsolated`并使用preview/grant/done。以下描述保留的直接接口，其completion/reply同拍协议不能与新grant/done混接。

## 1. 选择接入方式

| 使用方式 | 推荐配置 | 接入侧需要提供 |
|---|---|---|
| 原生 RISC-V 向量指令 | `standard`/`deep`，共享标量 FPU 时选择 `host` FCSR | 译码、源操作数、队头提交、GPR/FPR 写回、VS/FS 和异常处理 |
| 独立测试或作业执行器 | 默认 `standalone` FCSR | 命令调度、完成消费、缓冲区和上下文所有权 |
| ARM 等宿主管理的加速器 | 可从 `standalone` 配置开始 | 命令队列或代理、驱动、地址/缓存管理与作业异常转换；这些软件尚待实现 |
| 仅观测 VPU | 任一匹配配置 | 映射 monitor MMIO；此端口不能提交向量计算 |

当前单指令在途。原生 CPU 应在指令不可撤销时提交，采用 `VpuHostBoundary` 与退休侧连接；独立执行器也必须遵守相同的访存副作用和完成规则。

## 2. 生成硬件与地址配置

安装步骤见[构建说明](repository.md)。以下地址为示例，须与实际互连和内存图一致：

```bash
./mill Vpu.runMain vpu.GenerateConfigured --out build/integration --name SpinorVpu --preset standard --fcsr-owner host --region-base 0x80000000 --region-bytes 0x10000000 --monitor-base 0xa0010000
./mill Vpu.runMain vpu.GenerateHostBoundary build/integration/VpuHostBoundary.sv
```

生成清单 `SpinorVpu.json` 是宿主配置依据，记录几何、FP 开关、FCSR 所有者、RAM 窗口和 monitor 地址。将该目录生成的相关 SV 文件及辅助文件一并交给 HDL 工程，顶层选择 `SpinorVpu`；提交边界是单独的模块。

- `--preset`：`standard`、`deep`、`integer`、`integer-deep`。整数预设不能配 `--fcsr-owner host`。
- `--fcsr-owner`：`standalone` 为默认；`host` 将 FCSR 留在宿主 CPU，并增加 flags 侧带。
- `--region-base` / `--region-bytes`：允许的数据 RAM 物理窗口。大小至少 8 字节、为 2 的幂，基址按窗口大小对齐；默认 `0x80000000` 起 256 MiB。
- `--monitor-base`：按 4 KiB 对齐。保留完整物理地址的互连须使用真实基址；互连若先减去窗口基址，则生成时使用 0。
- `--vlen 128 --elen 64 --lanes 1`：当前固定几何；其他值会被拒绝。`--alu-stage-bits` 只支持 16 或 32。

## 3. 连接顶层

| 端口 | 方向（相对 VPU） | 用途 |
|---|---|---|
| `clock` / `reset` | 输入 | 顶层时钟与复位；与直连宿主/边界同域，复位需满足总线静止或联合复位条件 |
| `io.core.command` | 输入，Decoupled | 32 位原始指令、解析后的标量输入、AVL、80 位 token |
| `io.core.completion` | 输出，Decoupled | token、原指令、标量结果、写回有效和非法指令标志 |
| `io.core.flush` | 输入 | 算术取消或访存延迟停止请求 |
| `io.core.context` / `contextResult` | 请求输入 / Valid 结果输出 | 空闲时访问 VRF 的 64 位块；结果端没有 ready |
| `io.core.vl/vtype/vstart/vxrm/vxsat` | 输出 | 向量状态观察；访存时可包含已提交前缀 |
| `io.core.frm/fflags` | 浮点配置输出 | FCSR 观察；整数配置中不存在 |
| `io.core.fcsrHost` | 条件存在，双向侧带 | 仅 `host` 模式：输入 frm/fflags，输出本条指令 flags |
| `io.core.busy/versions` | 输出 | 核心占用及版本观察；versions 不代替完成/所有权协议 |
| `io.memoryStatus` | Valid 输出 | 与访存完成配套的 fault、interrupted、cause、address、element |
| `io.tl` | A 主端 / D 接收端 | 64 位物理 RAM 数据访问 |
| `io.monitor` | A 接收端 / D 从端 | 独立 4 KiB MMIO 观测窗口 |

Chisel 集成时，以下连接放入已有 Module；宿主信号及两个总线端口仍需按表连接：

```scala
import chisel3._
import vpu._

val spinor = Module(new SpinorVpu(
  monitorBase = BigInt("a0010000", 16),
  config = SpinorParams(hostFcsr = true)))
val boundary = Module(new VpuHostBoundary)

spinor.io.core.command <> boundary.io.command
boundary.io.completion <> spinor.io.core.completion
boundary.io.memoryStatus := spinor.io.memoryStatus
spinor.io.core.flush := boundary.io.vpuFlush
```

宿主负责 `boundary.io.offer/reply`、`headValid/headToken`、`olderMemoryDrained`、`olderFpDrained`、`stop`，并处理 `active`、`canceled`、`protocolError`。`VpuHostBoundary` 不转接 FCSR、context 或总线，它们需单独连接。跨时钟连接须使用完整事务异步桥；不要直接同步 valid/ready 或 token 各个位。

## 4. 准备操作数并提交

`Command` 的字段必须在握手前解析好，valid 被阻塞时保持稳定：

| 字段 | 内容 |
|---|---|
| `instruction[31:0]` | 原始机器指令，包含寄存器编号、操作模式和立即数 |
| `scalar[63:0]` | `.vx` 的 GPR、`.vf` 的完整 FLEN64 位模式、CSR 源，或访存 rs1 物理基址 |
| `scalar2[63:0]` | `vsetvl` 的 vtype 源，或跨步访存的有符号字节步长位模式 |
| `avl[63:0]` | `vsetvli/vsetvl` 在非零 rs1 情况下解析出的 AVL；x0 与立即数规则仍按原指令解释 |
| `token[79:0]` | 宿主定义的完整身份，在命令、取消、完成和错误处理中原样保留 |

索引访存从 VRF 读取零扩展字节偏移，忽略 scalar2；恢复访存仍传原基址，不传已加 vstart 的地址。跨步编码 rs2=x0 时强制零步长。FP 的 f0 是有效源，不能沿用整数 x0 取零规则。

原生 CPU 的提交顺序：

1. 完成权限、VS/FS、源操作数和目标写回端口检查；等待旧标量访存与 FP 工作排空。
2. 让 offer 的完整 token 与有效队头 token 匹配，保持 offer 直到握手。
3. 命令接收后保留 PC、操作数和身份，直到 reply 被接受，或收到明确的算术 canceled 通知。
4. 仅在 `reply.fire` 时授权普通运算的向量/CSR 状态与 CPU 标量结果一起发布。访存前缀可提前提交，见下一节。

`Completion.writesScalar` 为真时仍须根据回显指令选择 GPR 或 FPR；`vfmv.f.s` 对 f0 也会写回。SEW32 的 FPR 返回已经 NaN-box 到 64 位。

## 5. 访存、异常与停止

数据端只访问配置窗口内的物理普通 RAM，单事务、单 beat。宿主负责地址翻译、保护和缓存可见性；不要将 Linux 用户虚拟地址直接送入 scalar。

算术 flush 取消候选状态，边界通过 `canceled.valid` 返回身份，该指令不再产生 reply。访存 flush 则请求延迟停止：已发布的 A/D 必须排空，store 不可撤销，保留所有者直至最终完成/status。不能将算术取消规则用于访存，也不能在挂起事务时只复位适配器。

接收访存 reply 时检查 `exception`、`stopped`、cause/tval 和 element；stopped 不是成功退休，也没有自动生成 CPU 中断 cause。故障/停止后保留原 PC 与操作数，按已发布 vstart 恢复。分段访存的 vstart 以整段为单位，当前段可能已有字段前缀；整组/mask 访存的单位见[访存协议](tilelink.md)。

FOF 后续元素错误可能正常完成并缩短 VL，后续 CSR 与算术必须读取最终 VL；不能仅根据一次总线错误决定重试。边界的 `protocolError` 表示身份/元数据错配，须协调停机、排空和复位恢复，不能消费错误完成来“清除”它。

## 6. FCSR 与上下文

原生共享 FCSR 选 `host` 模式：CPU 提供已提交 frm/fflags，VPU 在 `command.fire` 锁存执行用 frm。CPU 仅在 `core.completion.fire && fcsrHost.flags.valid` 同一边沿将 `flags.bits` OR 到架构 fflags；使用边界时该握手由 reply 授权。0x001/0x002/0x003 的 CSR 指令留在 CPU，误送 VPU 会报非法。详细说明见[宿主 FCSR](m56-host-fcsr.md)。

默认 `standalone` 模式在 VPU 内管理 FCSR，适合独立执行器；ARM 每作业的 RISC-V 格式 FCSR 不能直接等同于 FPCR/FPSR。

context 访问前先排空命令、未消费完成及总线，并独占设备。地址是块编号 `2*r`/`2*r+1`，不是字节地址；读写都等待 contextResult.valid，结果没有反压。VRF 为 64 个 64 位块，共 512 字节；[portable helper](../software/context/README.md) 的完整镜像为 576 字节。恢复先写 VRF、VL/vtype、vcsr/FCSR，最后恢复 vstart；host 模式的 helper 回调须将 FCSR 路由给 CPU 所有者。

## 7. 首次联调顺序

1. 校对生成 JSON、端口位宽、RAM 窗口、monitor 地址、时钟和联合复位条件；静止未使用的命令/context/monitor 输入。
2. 从 monitor 读取 magic `0x4c495348`、ABI major 1、配置 ID 和几何，确认地址桥接正确。
3. 空闲时写入已知 VRF 块，读取比对；确认每次 contextResult 都被采样，且访问不与普通命令交叠。
4. 提交 `vsetvli` 和一个整数 `vadd`，检查完整 token、VL、RF 和标量写回；再阻塞一次 reply，确认完成保持且未提前发布。
5. 用普通 RAM 做一条 load/store，核对字节 lane 与 A/D 元数据；随后测试 denied、越窗和访存 stop，确认身份保留和总线排空。
6. 浮点配置检查 frm 快照、flags 合并与 FPR 写回；再做上下文保存/恢复和故障恢复。
7. 加入真实 CPU/作业软件后，再验收 VS/FS、权限、缓存维护、异常优先级和时序约束。

RTL 生成和已有验证通过不等于完整 SoC 接入。当前验证边界及复现环境见[验证说明](validation.md)。
