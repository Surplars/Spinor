# TileLink 与向量访存

当前公开顶层 `SpinorVpu` 已将向量 LSU 接到 `io.tl` 数据主端。另一个 `io.monitor` 是独立 MMIO 从端，方向和用途不同，见[monitor 指南](monitor-soc.md)。整体连接步骤见[接入指南](integration.md)。

可选`SpinorIsolated`在RAM和monitor的A/D四个方向增加非直通寄存切片，字段不变、无flush丢弃路径；参数和访存语义仍适用本页。其额外延迟、monitor缓冲和新提交协议见[隔离指南](m61-isolation.md)。

## 数据主端参数

采用工程内的 `VpuTileLinkMaster` / `VpuTLA` / `VpuTLD` 类型，定义于 [TileLinkReservation.scala](../src/main/scala/vpu/bus/TileLinkReservation.scala)。这些是显式 Bundle，不提供 Diplomacy 节点或参数协商；接入其他总线库时需字段转换，接 AXI 等协议需另设桥。

| 项目 | 当前公开顶层 |
|---|---|
| 通道 | A/D，非一致性单 beat；无 B/C/E、Acquire 或原子操作 |
| 地址 / 数据 | 64 / 64 位 |
| source / sink / size | 4 / 1 / 3 位；主端 source 固定0 |
| 在途请求 | 1；收到 D 并处理结果后才复用 source |
| A opcode | Get=4、PutFullData=0、PutPartialData=1 |
| D opcode | 读返回 AccessAckData=1，写返回 AccessAck=0 |
| param / corrupt | A 输出 0 / false；D 检查 param、opcode、size、source、denied 和 corrupt |
| size | log2(字节数)，0..3，对应1/2/4/8字节，自然对齐 |

内部请求的 data/mask 右对齐，A 端按 address[2:0] 移到总线字节 lane。例：地址 `0x...06`、2 字节写入 `0x1234`，A.mask=`0xc0`，A.data=`0x1234000000000000`。D.data 按相同 lane 返回，桥提取数据后交给 LSU。

A.valid 被阻塞时保持所有 payload；互连须完整返回对应 D。支持 A 接受同拍返回 D。非法请求和总线错误会转成当前 LSU/完成协议中的结果，不应自行吞掉返回来解除忙状态。

## 物理窗口与缓存

`SpinorParams.regionBase/regionBytes` 指定允许的普通 RAM 窗口。默认 `0x80000000` 起 256 MiB；大小至少8字节、为2的幂，基址按大小对齐。窗口检查不等同于 MMU/PMP，也不使 CPU 缓存与 VPU 自动一致。

接入侧须提供可见的物理 RAM、地址翻译/保护方案和正确的缓存维护或一致性路径。当前不能直接访问用户虚拟地址或任意设备 MMIO；不是通用 DMA/设备寄存器执行器。多个 VPU 接入同一 fabric 时，应由互连完成 source ID 扩展/重映射和路由。

## 当前访存形式

已实现单位步长、跨步、索引、分段、整组、mask 和 fault-only-first；[ISA 覆盖表](isa-coverage.md)列出范围和验证边界。

- 普通单位步长/跨步/索引：按元素推进 vstart，恢复传原基址。
- 分段：vstart 以整段为单位；故障段可能留下字段前缀，恢复从该段字段0开始。
- 整组：忽略当前 VL/vtype，按编码 EEW 和 NREG 的 EVL 访问；store 的 EEW 固定8。
- mask：传 ceil(VL/8) 字节，vstart 按字节解释，仍尊重 vill。
- FOF：元素0错误正常报异常；后续元素错误可正常完成并缩短 VL。以最终 completion/status 为准。

原始 LSU 状态含 fault、interrupted、cause、address 和 element；它与访存 Completion 配套。CPU cause/tval 映射见[提交协议](cpu-spinor-contract.md)。

## 停止、提交和复位

当前 LSU 按元素/字段提交前缀，已发 store 不可撤销。公共顶层访存期间收到 flush 时请求延迟停止，**不向底层桥传播丢弃响应的 flush**：先排空已发布 A/D，再返回完成与 memoryStatus。宿主在此之前保留 token、PC 和错误归属。

普通算术的取消规则不能用于访存。协议排空不等于回滚内存；stopped 和 fault 的后续处理由宿主授权。复位须在总线静止时进行，或由系统协调 VPU/宿主/fabric 联合复位。

## 历史预留封装

`LishiVpuTileLinkReserved` 是早期保留的算术加外部 memoryRequest 封装，并非当前完整 LSU 顶层。它的桥级 flush 可以将请求标记为 killed、排空 D 后丢弃内部响应；不能把这一行为照搬到 `SpinorVpu` 的精确访存所有权处理。

早期协议测试及原始说明保留在[文档快照](../archive/docs-m60/source/docs/tilelink.md)。当前新接入选择 `SpinorVpu`，历史实现记录见[单位步长](m10-memory.md)、[分段](m46-segment-memory.md)和[FOF](m48-fault-only-first.md)。
