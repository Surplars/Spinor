# M10 最小连续地址向量访存

新增顶层 `LishiVpuMemory`。旧的 `RamVectorFp` 算术顶层及 `LishiVpuTileLinkReserved` 预留封装继续保留，其 RTL 与 M9 相同。

## 指令与地址范围

实现非分段、非 FOF、unit-stride `vle8/16/32/64.v` 和 `vse8/16/32/64.v`。EEW 可不同于 vtype.SEW，按 `EMUL=LMUL×EEW/SEW` 检查范围 1/8..8、寄存器组对齐及边界；完整测试覆盖 78 种合法 EEW/EMUL 组合。掩码、prestart 和尾部元素保留；masked load 的 vd=v0 拒绝，store 可以从 v0 取数据。

指令中的 rs1 值由 `command.scalar` 提供，地址为 RV64 模 2^64 的 base+index×元素字节数。低/高 32 位分别生成地址。跨 beat 的不自然对齐元素暂不拆分，报告 load/store address misaligned（4/6）。没有分段、索引/步长、whole-register、FOF、MMIO、分页、PMP 或缓存一致性支持。

只允许自然对齐的普通、幂等 RAM。默认窗口为 `[0x80000000,0x90000000)`，通过 `LishiVpuMemory(regionBase,regionBytes)` 构造参数配置；regionBytes 必须是至少 8 字节的 2 次幂，base 同尺寸对齐。这是原型窗口，不是对用户板卡地址图的声明。宿主仍负责地址翻译、权限、缓存一致性与副作用属性；简单窗口检查不是完整 PMP。

## 顶层接口

`io.core.*` 仍提供 Command、Completion、ContextAccess、向量 CSR 输出及 flush；新增 `io.tl.a/d` 已真正接入 VectorMemoryEngine 和单事务 TileLink 桥，不再要求外部生成 memoryRequest。

`io.memoryStatus` 与访存 Completion 同时有效并保持至接受，字段为：

| 字段 | 意义 |
|---|---|
| fault | 访问异常；主 Completion.illegal 另表示非法编码/配置 |
| interrupted | 在安全元素边界响应了 stop/flush，请按原指令和 vstart 恢复 |
| cause | load/store misaligned=4/6，access fault=5/7；TL denied/corrupt/协议错误均映射访问异常 |
| address | 出错元素的物理有效地址；正常/停止时为 0 |
| element | 出错或停止的元素索引；正常完成为 0 |

本模块不写 CPU 的 mcause/mtval，不自动跳入异常入口。token/指令保持在 Completion，CPU 适配层必须按 memoryStatus 实现陷阱、退休、VS dirty 与中断接线。实际 Valence 核尚未接入。

## 逐元素提交与停止合同

算术仍采用候选版本、整条完成后原子提交。**访存采用另一套规则**：load 每个成功元素直接更新已提交 RAM，store 的已发送数据不可撤销。故障前完成的元素保留，失败和后续元素保持原值；vstart 指向故障元素，重试跳过已完成前缀。TileLink 对错误 store 是否已经产生部分副作用由目标决定，本测试内存采用错误 store 无写入的模型，不提供通用 store 回滚保证。

当前实现通过核心的 context 端口完成 RAM 读/改/写，并在每个元素后通过内部 CSR 命令更新 vstart。引擎独占这些端口，外部上下文访问及下一条指令在此期间背压；v0 掩码先缓存。

访存命令只能由不可撤销 ROB 队首发射，且旧标量访存已排空。

- 算术期间 flush 沿用原来的撤销规则。
- **访存期间 flush 是停止请求，不是立即撤销。** 主机必须继续保留本条指令和 token，等待并接受 Completion/status，不能因 flush 直接丢弃它。
- 一旦请求发布，必须保持到接受并排空 D；不复位/取消 TileLink 桥。已发布 store 成功后先完成 vstart 更新，再在元素边界停止。
- 对正常幂等 RAM，尚未写入寄存器的 load 返回可以丢弃，vstart 指向该元素。已写入寄存器的 load 必须完成对应 vstart 更新后才能停止。
- 停止期间收到的存储错误仍作为 fault 返回，不吞掉错误。若停止时全部元素已经完成，返回正常完成并令 vstart=0。
- mask-off 不发送事务；VL=0 或 vstart>=VL 不访存并将 vstart 清零。正常完成也清零。
- reset 仍要求 fabric 联合复位或总线静止，不保证单独复位能排空旧事务。

该合同尚不等价于完整 CPU 中断/精确异常集成。它解决的是本地元素前缀和总线所有权，集成方必须实现上述延迟停止协议。

## 实现和验证

引擎容量为 1，复用 64×128-bit 双版本 RAM，没有全组 FF 快照。TL 单 source=0、1/2/4/8-byte 单 beat。现阶段每个元素更新 CSR，吞吐较低，优先建立可验证的故障恢复基线。

`tests/test_vector_memory.py` 使用独立 Python 向量/字节内存 oracle，SV 内存模型提供 A 背压、可变响应等待、denied/corrupt/畸形 D。检查地址序列、load/store 数据、masked/tail/prestart、非法编码/EMUL、v0、地址进位、故障前缀及重启；另跑 load→整数加法→store 和 load→FP加法→store，保持 FCSR/vcsr。RTL 附加引擎和算术核心的 Chisel 断言。

完整 RTL 覆盖 222 个常规用例、77 个停止用例、78 种合法 EEW/EMUL；代表性映射后用例为 62+9，使用真实 TileLink 路径及固定版本 DSP 功能模型。映射功能模型不提供器件时序。

性能周期、有效字节/周期及明确标注的假设频率换算见 `reports/m10/memory-performance.md`，没有真实 DDR 带宽或 M10 Vivado WNS。复现：`make verify-m10`、`make package-m10`。
