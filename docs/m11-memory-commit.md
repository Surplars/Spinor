# M11 专用访存进度提交

LSU 继续采用 M10 的逐元素前缀提交、单事务和延迟停止合同。新增 `RamVector(enableMemoryCommit=true)` 的独立 `memoryCommit` ready/valid 端口，只提交 7 位 vstart；内核模块名为 `RamVectorFpMemory`。默认算术核和公开 `io.core` 接口不变。此端口由内部 LSU 独占，不暴露给 CPU。

访存合法性检查增加独立 validate 阶段，每条指令固定增加一个周期，避免复杂译码直接接入进度控制。

原先每次进度更新要发出内部 csrrw 并等待 Completion；现在 LSU 的 writeStart 状态直接握手并进入下一元素或完成。load 仍先用 context 写回寄存器，再等待 contextResult，最后提交 vstart；这不是数据与 vstart 同周期提交。stop 在这两个阶段之间到达，也必须完成 vstart 提交，才能停在下一元素。store 的 D 错误优先于停止，成功 store 必须提交进度，已发布的 TileLink A 和返回 D 仍须排空。

核心只在 idle、无候选写、无 context 请求、无算术命令且无 flush 时接受提交。集成顶层在访存 busy 时阻断外部算术命令和上下文访问，并将核心 flush 屏蔽为延迟停止。断言检查进度提交不会与上下文返回重叠。新提交端口不是任意时刻可写 CSR 的调试接口。

范围仍限非分段、非 FOF、连续地址物理普通 RAM；没有实际 Valence、分页、PMP、一致性或 CPU 精确异常接入。没有新增指令种类。本轮为吞吐优化，不改变可发布的 ISA 合规范围。

复现：`make verify-m11`，`make package-m11`。周期对照使用冻结 M10 的相同 24 组模型；RTL 和映射后用例核对数据、地址序列、故障和停止后的已提交前缀。资源和组合单元跳数仅用于筛选，不能据此证明 ZU15EG-2 的 300/500 MHz。
