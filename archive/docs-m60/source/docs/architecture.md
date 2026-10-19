# 砺矢（Lishi VPU）：开发合同与接入边界

## 需求和当前阶段

最终目标：为 PL 中的 Valence RV64 核提供 RVA23 所需的向量能力，运行于
`xczu15eg-ffvb1156-2-i`。优先小规模和 RAM 友好结构；300 MHz 基线，500 MHz 候选。
当前交付M22：在字节并行mask通路上增加vmsbf/vmsif/vmsof前缀操作，保留M20的FP/monitor时序优化及先前RAM优先架构。ISA覆盖、周期和时序边界见 [M22说明](m22-prefix-mask.md) 与 [评估](../reports/m22/evaluation.md)。仍为单条指令在途的部分RVV，实际Orbital与Linux计算驱动尚未接入；访存逐元素提交和延迟停止，不继承M5的真实时序结论。
完整 V 必须包含 FP32/FP64，并不因为 VLEN128 就允许省略浮点、复杂访存或 LMUL。

来源：[RVV 1.0](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)、
[RVA23 v1.0](https://docs.riscv.org/reference/rva23/v1.0/rva23-profiles.html)。

## 不变量

1. 宿主仅向不可撤销的 ROB 队首发射，旧标量访存和浮点操作已经排空。
2. M2 源始终读已提交版本，目的始终写候选版本；先复制旧目的保留 mask/tail/prestart，缓存 v0。
   源/目的别名不会破坏后续元素。M1 则使用 FF 快照。
3. 算术 M2 仅在 `completion.fire` 原子翻转全部目的版本；M1 同一时点写回 shadow。
   M10 访存按元素更新已提交值和 vstart，故障/停止保留前缀，不采用算术整条原子提交。
4. 算术 flush 同拍禁止相关接口 fire，并丢弃有效位；RAM 数据不清零。
   M10 访存 flush 请求边界停止，必须排空已发请求，且保留 Completion/status 直到接受。
5. 向量寄存器 v0 是普通可写向量寄存器，不能按标量 x0 实现为零。
6. 不能重用未返回请求的 ROB 身份；当前 80-bit token 覆盖 Valence 的 tag64 + index5。
7. 信用计数包含流水中和结果 FIFO 中的所有请求；每个已接收请求都预留结果空间。
8. 仅一个读地址和一个写地址；端口调度禁止同一物理行的读写碰撞。
   版本提交与上下文访问互斥，不依赖特定 RAM 的碰撞行为。

## 性能合同

| 模块 | 无停顿延迟 | 接收间隔 | 容量/背压 |
|---|---:|---:|---|
| IntegerLaneBaseline | 2 拍 | 1 拍 | 2 条，输出阻塞冻结流水 |
| IntegerLaneSplit (32-bit 切分) | 7 拍，含结果 FIFO | 1 拍 | 8 条预留信用，满时入口阻塞 |
| IntegerLaneSplit16 | 8 拍，含结果 FIFO | 1 拍 | 9 条预留信用，满时入口阻塞 |
| VectorRegisterFile | 1 拍同步读 | 1 拍 | 共享单读地址，单写地址/两 bank 写使能 |
| VectorPrototype | 依指令长度 | 指令串行；元素最小 2 拍 | 单指令，多元素在途，完成可任意阻塞 |
| VersionedRegisterFile | 1 拍同步读 | 1 拍 | 64×128-bit，字节写使能，32-bit 版本表 |
| RamVector / RamVector16 | 依指令长度 | 指令串行；基础整数数据运算多元素在途，其他单元串行 | 目的最多 8 个寄存器同时原子提交 |
| RamVectorFp | 依指令与迭代长度 | 单元素在途，共享 FP32/FP64 数值硬件 | 数据及 FP flags 共同提交 |
| ValenceBoundary | 资格/转发为组合 | 单指令在途 | 保留完整 owner，陈旧完成消耗后丢弃 |

未实现同一拍提交并接受下一条指令的旁路。VLEN128 短向量会受快照/启动开销影响。
`tests/benchmark.py` 及其 `--ram` 选项对相同指令流记录真实仿真周期；
M2 新增 LMUL 能力且取消整组 FF 快照，目前逐元素访问更慢，不能只按 LUT 降幅宣传性能。
下一步应在保持同一提交协议的前提下重叠读 RAM、执行和候选写回，再加入乘除、LSU 和浮点。

## M2 双版本 RAM

物理行地址为 `{committed[reg] XOR candidate, reg[4:0]}`。
32 个架构寄存器各有两个 128-bit 物理版本，总数据容量 8192 bit。
目的组复制到候选版本后，结果按字节更新；掩码比较结果对候选字节逐位读改写。M21显式掩码逻辑每次计算8位，对边界字节按有效位读改写；扫描分级处理8位。
源从已提交版本读取，故即使 vd 与 vs1/vs2 重叠也不会读到本条指令的部分结果。
完成被接受时版本表 XOR 目的掩码，最多 8 个寄存器同拍可见；撤销时版本表不变。
再次使用被撤销的候选行前总会重新复制旧目的，因此不依赖 RAM 初值。

仅适用于当前不会发生元素故障的算术指令。未来向量 LSU 的部分提交、vstart 恢复
和 MMIO 副作用需要重新设计，不能用整条原子翻转替代精确访存语义。
CSR 功能不含 privilege/VS/FS 权限检查；宿主适配层仍须负责这些检查。

M5 的 RamVectorFp 在候选写入到 RAM 之间加入一个可每拍接收请求的寄存器级，
保存 5-bit 逻辑地址、16-bit 字节使能和 128-bit 数据。候选写入为固定 candidate 版本。
提交、上下文访问和下一条指令都等待该级排空；flush 同拍禁止落入 RAM，并清除待写有效位。
上下文写入直接旁路该级，保持 context.fire 当拍修改已提交数据的原语义，后续 flush 不撤回已经接受的上下文写入。
这不是源/目的整组 FF 快照；向量数据阵列仍在 RAM 中。纯整数顶层保持原写回协议。

## NaxRiscv 学习结论

阅读的固定版本记录在 `tools.lock.json`，重点文件：

- [RegFilePlugin.scala](https://github.com/SpinalHDL/NaxRiscv/blob/9f452d50560d02fb391bc8039f5453c54e0911af/src/main/scala/naxriscv/misc/RegFilePlugin.scala)
- [MultiportRam.scala](https://github.com/SpinalHDL/NaxRiscv/blob/9f452d50560d02fb391bc8039f5453c54e0911af/src/main/scala/naxriscv/compatibility/MultiportRam.scala)

源码主要寄存器堆是 `RegFileAsync`，利用分布式 RAM；多写端口的处理和写端口共享、
读复制、LVT/XOR 等变换有成本。不能声称其默认实现全部是同步 BRAM。
`bankCount` 在该实现中也不能直接当成可自由扩展的端口方案。
本工程采用独立编写的 Chisel 同步 RAM 和共享端口，不复制 NaxRiscv 源码。
选择同步读是为建立清晰的时序边界；VPU 小容量时 LUTRAM 可能比 BRAM 更合适。
LUTRAM 的有效容量还受独立读写端口和字节写使能打包限制；例如当前 8192-bit
双版本阵列映射为 32 个 RAM64M8，不能只用逻辑 bit 数除以每 LUT 容量估算占用。
资源报告按完整映射单元统计存储 LUT，并分别列出逻辑 LUT，避免遗漏这部分成本。

自动 RAM 和 FF 候选使用相同接口、端口周期和功能测试，隔离存储实现的资源差异。
BRAM 实验只给 VRF 存储模块设置 `ram_style=block`，没有把所有队列强制改成 BRAM。
BRAM 映射的功能等价性没有运行原生器件模型验证；它只是资源实验。

## Valence 集成

Valence 仍在演进，目前没有接好标准向量发射端口；不修改其标量流水作为本轮前提。
`ValenceBoundary` 是可独立测试的候选边界，不是完成接入的证据。
初期在 ROB 队首串行执行，避免为向量状态引入推测重命名。
宿主须保留 owner 直至回复被接受，提供 vector CSRs、VS/FS 状态管理、标量寄存器写回和异常提交。
M2 自行解码 `vset*` 的 rs1=x0 / rd=x0 规则；非零 rs1 的 AVL 仍由宿主读取并传入。
M1 旧接口则依赖宿主预先处理 AVL 规则。

M3 的 vf 形式通过 command.scalar 接收 FLEN64 的浮点寄存器值，vx 形式同一数据字段传整数寄存器值。
FP32 标量值须正确 NaN-boxing；向量寄存器里的 FP32 元素不做 boxing。
当前独立原型支持 frm/fflags/fcsr 及相应 CSR 指令；核级集成必须统一 Valence 标量 FP
与向量 FP 的架构 FCSR，确保舍入模式快照、标量/向量 flags OR、CSR 访问和退休顺序一致。
不能把此独立原型的局部 CSR 状态直接接成第二份 CPU FCSR。宿主 VS/FS/dirty/权限接线尚未实现。

涉及访存时需重新定义可重启的逐元素提交、`vstart`、中断及 FOF；当前整条原子提交
只适用于已经实现的非故障整数运算，不可直接套到所有向量 load/store。

独立 VPU 300/500 MHz 不代表当前 100 MHz 板级 Valence 自动提速。
若采用独立时钟，必须增加正式 CDC 协议和独立边沿验证；本轮边界为同钟域，未实现 CDC。

## 后续验收关卡

1. 寄存器组、vstart/CSRs 的 M2 子集已验证；接下来重叠 RAM 访问，扩展整数全功能及 Zvbb。
2. M3 已接入同宽 FP32/FP64、舍入和异常标志，并通过独立 SoftFloat 差分；
   M9 已补同宽转换并切分长链；后续补宽化/窄化/归约/估算及 Zvfhmin。
3. 接宿主译址/权限/一致性访问，验证精确故障、FOF、访问顺序和上下文。
4. 在 Valence 的 GSIM/NEMU 流程中进行核级独立验收，随后运行实际器件实现。
5. 只有完整 ISA 验收、物理时序和板测均有证据，才发布对应的 ISA/频率/bitstream 声明。

这些是未完成事项，不是通过配置开关即可获得的功能。

## LSU 结构选择

LSU 指 Load/Store Unit。计划采用独立的向量 LSU 前端，负责元素地址、mask、
请求拆分、分段/索引遍历和故障元素定位；通过宿主访存适配接口共用 CPU 的
地址翻译/权限、缓存与总线，并协调标量/向量请求顺序。
宿主访存适配接口须保持标量/向量共享内存的一致性与顺序。
原型可先在 ROB 队首串行访存，但仍需正确处理逐元素故障、副作用、vstart 和 FOF。
M10 已实现物理普通 RAM 的连续地址、单事务、逐元素提交和边界停止原型，见 `docs/m10-memory.md`。
宿主共享翻译/缓存、一致性、精确 CPU 陷阱及 FOF 等尚未实现；当前独立 A/D 路径不能直接视为与 CPU 缓存一致。
