# 砺矢 TileLink 预留边界

M9 增加 `TileLinkReservation` 单事务 A/D 主端，以及 `LishiVpuTileLinkReserved` 顶层封装。算术顶层 `RamVectorFp` 的接口保持原样；封装的 `io.core.*` 转接原算术端口，另暴露 `memoryRequest`、`memoryResponse`、`memoryBusy` 和 `tl.a/d`。

**目前 memoryRequest 由接入侧驱动，尚未连接向量 LSU。没有实现向量 load/store、地址翻译、PMP、精确访存故障、分段/索引访问或缓存一致性。** 这些接口是已实现并测试的协议预留，不是完整访存能力。

## 总线参数

默认：地址 64 位、数据 64 位、source 4 位、sink 1 位、size 3 位。地址/source/sink/size 位数可配置，数据宽度当前限定 64 位。仅 A/D；不发 Acquire，不持有一致性权限，不提供 B/C/E。

已核对本地 Valence 的 `soc.bus.tilelink.TLBundleA/TLBundleD` 字段和 opcode 编码。参考源码提交 `6c8977f684830137fae088d4679f9d84e5ce4a11`，文件 `src/main/scala/bus/tilelink/TileLink.scala` SHA256 为 `22d024123aae4bbbfe42142a653f73e23335211d2535f0041880388b3ab93a18`。本项目不直接依赖该 Scala 包，也未修改或接入 Valence；连接时需要字段转接及系统级参数/协议检查。

| A/D 字段 | 位数 / 行为 |
|---|---|
| A opcode | Get=4，PutFullData=0，PutPartialData=1 |
| A param / corrupt | 0 / false |
| A size | log2(字节数)，只接受 0..3，即 1/2/4/8 字节 |
| A source | 固定 0；一个事务在途，收到 D 前不复用 |
| A address | 自然对齐的物理字节地址 |
| A mask / data | 请求内低位字节掩码/数据按 address[2:0] 放入总线字节 lane |
| D | 接受 AccessAck / AccessAckData，核对 opcode、param、size、source；报告 denied/corrupt |

内部请求数据与 mask **右对齐**。例如地址 `0x...06`、size=1（2 字节）、mask=3、data=0x1234，A mask=0xc0、A data=0x1234000000000000。读返回从对应 lane 提取并零扩展，符号扩展留给未来 LSU。写返回 data=0。非法 size、未对齐、零/越界写 mask、未授权写在本地返回 localError，不发送 A。

不支持跨 beat、burst、多 source、原子操作或 coherent TL-C。未来 LSU 必须拆分/排序访问，并解决翻译、权限、一致性和故障恢复。首选与宿主 LSU/共享缓存路径协调，不能把独立物理 A/D 接口视为与 CPU 缓存天然一致。

## flush、背压与不可撤销写

- 接受内部请求后，A payload 寄存；A.valid 在背压下保持，flush 也不撤回已发布的 A。
- flush 将该事务标记为 killed；A/D 继续完成协议，D 被排空，旧 token 的内部响应被丢弃，之后才允许复用 source。支持 A 接受同拍收到 D。
- response 在背压下保留数据和 token；flush 可丢弃尚未接受的内部响应。
- store 必须携带 irrevocable=true，否则本地拒绝。该标志由宿主在确认架构上允许产生副作用后提供；桥无法回滚已发送的 store。
- 协议层的排空不等于精确异常/架构撤销：宿主不得在已授权 store 未完成时丢失其副作用或错误归属。最终 LSU 必须为 store 完成、错误及中断制定退休规则。
- reset 要求与 fabric 联合复位或接口已静止；单独复位本模块不会替旧事务排空 D。

## 验证

`tests/test_tilelink.py`：600 组事务，含 36 个本地拒绝、112 个同拍 A/D、459 个实际 flush 场景、41 个畸形 D 返回检查；564 个已发布 A 均排空了 D。RTL、Yosys 映射网表以及预留封装的总线接口均执行相同用例。封装用例保持算术命令端静止，算术功能另由整机回归验证，不声称已验证 LSU/总线联合执行或完整 TileLink 合规。

## M10 后续实现

`LishiVpuMemory` 已把最小连续地址 LSU 接到 A/D 桥；它不使用本页预留封装的外部 memoryRequest 口。访存期间桥不接 flush，采用排空请求、保留错误、在元素边界完成停止的新合同，见 `docs/m10-memory.md`。旧预留封装及其原始协议测试仍保留。
