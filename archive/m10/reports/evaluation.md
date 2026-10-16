# 砺矢（Lishi VPU）M10：最小连续地址访存闭环

新增 `LishiVpuMemory` 顶层，将 `VectorMemoryEngine`、M9 算术核心和单事务 TileLink 主端接在一起。实现 `vle8/16/32/64.v`、`vse8/16/32/64.v` 的普通物理 RAM 访问。支持 EEW 不同于 SEW，检查 EMUL 1/8..8 和寄存器组合法性；不支持分段、索引/步长、FOF、MMIO、分页/PMP、一致性或完整 CPU 异常接入。

## 提交、错误和停止

load 每个成功元素直接写入已提交向量 RAM，store 已发出的数据不可撤销。每个元素完成后更新 vstart；错误时保留已完成前缀并返回故障元素、地址及 cause，重试从 vstart 开始。非法指令不访存，不修改 vstart。

**访存期间 flush 是延迟停止请求，不能立即丢弃指令/token。** 已发布请求保持并排空返回；已写入的 load 或已成功 store 必须完成对应 vstart 更新。停止期间收到的错误仍返回 fault；宿主须接收 Completion/status，并据此处理中断、陷阱和退休。算术顶层的既有撤销语义保持不变。

仅允许可配置的普通幂等 RAM 窗口，默认 `[0x80000000,0x90000000)`，不代表实际板卡地址图。自然对齐错误产生 cause4/6；窗口/TL denied/corrupt/协议错误产生 cause5/7。测试内存让错误 store 不写数据；这不提供通用目标的 store 回滚保证。完整接口和集成合同见 [M10 文档](../../docs/m10-memory.md)。

## 验证范围

- 完整 RTL：78 种合法 EEW/EMUL，222 个常规用例和 77 个停止/错误组合，3716 个请求均收到返回；输出寄存器、内存字节和地址序列由独立 Python oracle 检查。
- 覆盖掩码、尾部、prestart、VL0、vstart>=VL、vd/vs3=v0、非法编码/组对齐/EMUL、地址进位、自然对齐、窗口拒绝、denied/corrupt/畸形 D、故障前缀与重启、响应背压、stop 等待排空及错误保留。
- 闭环：load→整数加法→store，load→FP加法→store；实际翻转算术版本表后再访存，检查 context 端口访问的是当前已提交版本。FCSR/vcsr 保持正确。
- RTL 附加了 VectorMemoryEngine 和 RamVectorFp 的 Chisel 断言，检查内部 vstart CSR 未拒绝、候选写入排空及算术在途所有权。
- 代表性 RTL/映射后：同样 62 个常规用例、9 个停止场景、6 种 EEW/EMUL 配置，781 个请求/返回、17607 个周期，两者结果与周期一致。映射后不附加优化前内部层级断言。
- 算术核心、FP、乘除法、转换器和独立 TL 桥的生成 RTL 与 M9 SHA 一致，因此明确复用已有独立数值验证；新顶层的仲裁和内存-计算闭环重新验证。

测试不是完整 RVV/TileLink 合规套件，也不验证实际 CPU 页表、缓存一致性、异常 CSR 或操作系统。

## 资源和结构参考

| Yosys xcup 自动映射 | M9 算术顶层 | M10 访存完整顶层 |
|---|---:|---:|
| 逻辑 LUT | 12784 | 14069 |
| FF | 9002 | 9998 |
| DSP48E2 | 9 | 9 |
| RAM64M8 / RAM32M16 | 32 / 6 | 32 / 6 |
| 最长数据单元跳数 | 16 | 16 |

M10 表包含仲裁、引擎和 TL 桥，增加 1285 逻辑 LUT、996 FF。独立引擎映射为 769 LUT、625 FF、0 DSP，最长数据链 12 个映射单元。VRF 继续使用 RAM，无全组 FF 快照。跨模块优化使独立模块之和不等于完整顶层增量。

单元跳数不是实际 ns/MHz，M10 没有 Vivado 实现、SDF、bitstream 或板级频率确认，300/500 MHz 状态仍未知。M5 的物理时序结论不继承到 M10。本轮不要求用户再次跑本地 Vivado。

## 性能基线与后续

[24 组访存周期参考](memory-performance.md) 和 [CSV](memory-performance.csv) 测量有效字节/周期。模型包含可配置服务等待与 A 背压，不是 DDR。无额外等待、LMUL8、128-byte 全向量时：8-bit 元素 load/store 为 2119/1927 周期，64-bit 为 270/247。

当前单事务、逐元素 context 操作和 vstart CSR 更新牺牲吞吐，先证明前缀和恢复规则。下一步可做向量块缓存和专用元素提交接口，随后再引入多个 source 并发，必须保留错误排序及 store 副作用边界。

复现：`make verify-m10`，再运行 `make package-m10`。receipt.json 记录当前源码、RTL/网表、测试输入及结果 SHA；M9 验证证据保存在归档。
