# 砺矢 · Spinor VPU

目标器件 `xczu15eg-ffvb1156-2-i`；采用 **Mill 1.1.7 / Scala 2.13.18 / Chisel 7.16.0**。
300 MHz 为基线设计目标，500 MHz 为候选目标。M31 已完成 Vivado 2025.1 独立 OOC 实现：3.333ns 下 setup +0.392ns、hold +0.009ns；实际时钟源和宿主 IO 延迟尚待约束。见 [本地报告](reports/local-m31/evaluation.md)。

**当前是含整数与部分浮点的向量原型，不是完整 RVV，尚未接入 Orbital CPU。**
尚未实现完整 V / Zvfhmin / Zvbb / Zvkt；不能向软件发布 `misa.V` 或 RVA23 合规声明。
命名为 **Valence SoC / Orbital CPU / Spinor VPU**。公开顶层类为 `SpinorVpu`，保留内部 `Lishi*` / `RamVector*` 兼容类。当前交付 **M44**：新增16种ordered/unordered索引gather/scatter，索引与数据共享RAM读口和分段地址加法器，支持合法宽窄重叠、故障恢复及停止排空；保留M43访存提速。保留四种规模预设、VLEN128/ELEN64、单lane、容量1。见 [M44说明](docs/m44-indexed-memory.md)、[规模参数](docs/m39-configurations-and-fp-transfers.md)、[完整性计划](docs/rvv-completion-plan.md)、[CPU协议](docs/cpu-spinor-contract.md)、[ISA覆盖矩阵](docs/isa-coverage.md)。尚未接入实际Orbital；ARM计算任务队列也未实现。继续使用[云端条件时序预算](docs/m13-timing.md)，不是器件STA。
仅物理普通 RAM、单事务，访存采用逐元素提交和延迟停止；不支持 MMIO/分页/PMP/一致性，尚未接入 Orbital CPU。
**访存期间 flush 必须等待 Completion/status，不能按算术指令立即丢弃 token。** 见 [M10 合同](docs/m10-memory.md)。
已加入 [M8 的 220 组性能对照](archive/m8/reports/performance.md)，并检查输出结果。
M44保留两个顶层固定100ps/段云端条件预算≤3.333ns的交付门槛，实际结果及输入散列见 [M44报告](reports/m44/evaluation.md)。完整SoC时钟/接口尚未签核。
本轮尚未经过Vivado实现，不能继承M31通过结论。最新已验证的本地结果和输入散列见 [M31 本地报告](reports/local-m31/evaluation.md)，原 [M31 云端报告](reports/m31/evaluation.md) 保留交付时的状态；[M5 实际时序与云端参考](reports/cloud-m5/evaluation.md) 保留为早期物理基线。
命名与设计方向见 [项目介绍](docs/lishi.md)。
M4 原始报告保存在 [归档](archive/m4/reports/evaluation.md)。后续本地 Vivado 的 M4 OOC 结果及其时钟限制另记录在 M5 报告中。
前一版浮点基线保存在 [M3](archive/m3/reports/evaluation.md)。
M1/M2 的原始证据保存在 [M1](archive/m1/reports/evaluation.md) / [M2](archive/m2/reports/evaluation.md)。

## 运行

在 Linux x86-64、Java 21、Python 3.12+ 环境下：

```bash
git clone https://github.com/Surplars/Spinor.git
cd Spinor
make bootstrap
python3 scripts/verify_m44.py
python3 scripts/package.py --milestone m44
```

验证入口会准备固定版本 SoftFloat 和 RapidWright；首次执行需要网络访问工具锁文件中的下载地址。
Git 保存源码、测试、报告及回归所需的冻结基线；当前生成的 `build/`、下载的 `tools/` 和发布 ZIP 不入库。
报告中的 `build/` 散列对应验证时的生成文件，需重新运行验证后在本地核对。目录与接入入口见 [仓库使用说明](docs/repository.md)。

bootstrap 下载约 714 MiB 的 OSS CAD Suite，校验 SHA-256 并解压到 `tools/`；
不安装系统包，不修改 HOME/网络/信任配置，不安装或调用 Verilator。
Mill 首次运行会下载 JDK 和 Maven 依赖，工具及缓存保留在本工程内。
首次浮点检查另外下载、校验并构建固定版本 SoftFloat；需要 GCC 和 Make。
M31 的 Windows 编排检查额外下载约 72MiB、SHA 固定的 Linux PowerShell 7.5.4；仅用于运行交付脚本测试，不作为 HDL 仿真器。
M4 另下载固定版本 RapidWright standalone（约 110 MiB）和 ZU15EG 器件数据库（约 6.5 MiB），
只做 API/数据库能力检查；不把该检查当作设计时序分析。
云端工具及浮点参考已安装。`make verify` / `make verify-m2` 保留旧阶段入口。

单项入口：

```bash
./mill Vpu.compile
./mill Vpu.runMain vpu.Generate /absolute/path/to/rtl
python3 tests/test_lane.py
python3 tests/test_vector.py
python3 tests/test_boundary.py
python3 tests/test_versioned_rf.py
python3 tests/test_ram_vector.py
python3 tests/benchmark.py --ram
make m2-synth
make m2-mapped-test
make reference-timing
make fp-bootstrap
python3 tests/test_fp_lane.py
python3 tests/test_fp_vector.py
python3 tests/test_ram_vector.py --fp
make m4-synth
make m4-mapped-test
make rapidwright-probe
```

RTL 仿真使用本独立工程的 Icarus Verilog；没有在 Valence 仓库运行其不支持的仿真流程。
Valence 接入后须遵守其 GSIM、独立差分与精确异常验收要求。
每个导出的顶层 RTL 文件自包含；按测试脚本选取顶层文件，避免把全部顶层同时编译造成模块重名。

## 已有实现

- M2 `RamVector`：VLEN128、ELEN64；m1/m2/m4/m8/mf2/mf4/mf8，覆盖全部 22 种合法 SEW/LMUL 组合。
- 真实 RVV 编码的 `vsetvli/vsetivli/vsetvl`，含 rs1=x0/rd=x0 特殊 AVL 规则。
- `vstart/vxsat/vxrm/vcsr` 读写及 `vl/vtype/vlenb` 只读 CSR；宿主负责权限与 VS/FS 状态。
- `vadd/vsub/vrsub/vand/vor/vxor/vsll/vsrl/vsra/vmin[u]/vmax[u]` 支持的 vv/vx/vi 形式。
- `vmseq/vmsne/vmslt[u]/vmsle[u]/vmsgt[u]` 掩码结果、`vmv.v.*`、`vmerge.v*m`。
- 掩码及 tail 保留，寄存器别名处理、完成背压、flush 全撤销；不复位寄存器数据阵列。
- 双版本 64×128-bit 同步 RAM，单读/单写端口、逐字节写使能；同接口 FF 对照及强制 BRAM 映射实验。
- 只用 32-bit 版本表原子提交目的寄存器组，无整组源/目的 FF 快照；flush 丢弃候选版本。
- 单元素 64-bit 执行器；M8 基础整数允许多个元素在途，但没有 8 路 INT8 SIMD。
- 32-bit/16-bit 算术切分候选；输出 FIFO 的入口信用预留，无全局数据流水停顿。
- 独立的同钟域 `ValenceBoundary`：ROB 队首资格、旧访存/FP 排空、80-bit token 和陈旧完成拒绝。
- M3 `RamVectorFp`：共享 FP32/FP64 同宽加减乘除、开方、八种融合乘加、min/max、比较、符号注入与分类。
- 五种舍入模式、NaN/subnormal、frm/fflags/fcsr；FP 结果和 flags 一起在完成接受时提交，撤销不泄漏异常标志。
- 固定版本 HardFloat 硬件；独立 SoftFloat 数值/flags 对照；含原生 DSP48E2 的映射网表也通过功能检查。
- M4：FMA 对齐、26×17 分块乘法、carry-save 求和、规格化、舍入和除法迭代分级；译码与合法性检查分级。
- FP、乘除法数值单元仍只有一个元素在途；M8 只提高基础整数数据运算的元素重叠度。
- M5：候选 RAM 写地址、字节使能、数据寄存后写入；完成等待写回排空。上下文写入保持握手当拍生效。
- M5 增加逐周期撤销扫描及上下文写入后 flush 检查，ISA 覆盖保持 M4 子集。
- M6：`vmul/vmulh/vmulhu/vmulhsu` 的 vv/vx 形式，单个 16×16 DSP 复用。
- M7：`vdivu/vdiv/vremu/vrem` 的 vv/vx 形式，分级恢复除法，不新增 DSP。
- M8：解耦基础整数元素发射与返回，按元素 tag 写回，计数排空后完成；一次仍只执行一条指令。
- M9：六种同宽转换，含 signed/unsigned、动态舍入与 RTZ；[转换说明](docs/m9-conversions.md)。
- M9：64-bit TileLink A/D 单事务预留主端；[接口和 flush/store 合同](docs/tilelink.md)。
- M10：vle/vse 8/16/32/64、78 种合法 EEW/EMUL、部分提交/vstart 恢复、load→计算→store；[物理 RAM 访存合同](docs/m10-memory.md)。
- M18：8种同宽整数归约、独立 CPU 提交边界及公开 SpinorVpu 顶层。
- M19：8种mask逻辑、整数标量读写；所有源和目的仍使用版本化RAM。
- M20：vcpop/vfirst、FP路径与monitor组合链优化；使用舍入器的运算多1周期。
- M21：8位mask专用通路，掩码逻辑绕过逐位ALU，扫描选择与计数分级；VL128逻辑1929→121周期。
- M22：vmsbf/vmsif/vmsof复用字节通路，以1个seen位跨字节传播前缀状态。
- M23：viota/vid索引生成；8位前缀计数复用已有私有暂存，目的沿用整数流水和版本化RAM。
- M24：整数slide六种编码，保留64位偏移精度、VL/VLMAX边界、mask/vstart及下移别名支持。
- M25：四种gather编码，EI16独立EMUL；scalar/immediate索引以单元素暂存广播，无整组快照。
- M26：舍入与IEEE封装分级、并行索引递增、统一执行mask/v0数据别名检查；两个顶层满足固定云端参考门槛。
- M27：RAM压紧vcompress；复用现有计数/地址阶段，组边界检查进行局部形式等价验证。
- M28：单宽 FP32/64 有序/无序求和与 min/max 归约；无新增 RAM 端口，宽化 FP 归约由M30补充。
- M29：宽化整数归约复用RAM/累加器/整数流水，区分源SEW与标量2×SEW，并检查不同EEW的seed/data源别名。
- M30：FP32→FP64宽化求和归约；复用精确FP32 recode与FP64累加流水；边界比较使用成对布尔树并作局部SAT等价证明。

命令顺序执行，只有一条向量指令在途。M2 源读已提交 RAM，目的写候选 RAM，
只有宿主接受完成才翻转版本表或更新配置；RAM 内的候选数据在撤销后无需清零。
M2 的 LMUL1 依赖 vadd 比 M1 慢：当前优先验证 RAM 和提交机制，周期比较见报告。
旧的 `VectorPrototype` 保留 M1 快照及多元素在途方案，便于比较。

## 尚未完成

FP16数据格式/Zvfhmin及其他目标扩展的完整审计；
完整向量LSU：分段、FOF、整组与mask访存，以及MMIO、译址/PMP/一致性和核级精确异常；
OS上下文、Valence整核接入、编译器程序闭环及完整架构验证。
开发清单和边界见 [架构合同](docs/architecture.md)。
独立原型的 FCSR 仍需与 Valence 标量 FP 状态统一，不能在整核中并存两份架构 FCSR。

## 评估含义

Yosys `synth_xilinx -family xcup` 输出映射单元数量；不等于 Vivado 最终 slice 占用。
逻辑 LUT、LUTRAM、FF、进位单元、BRAM 分开统计。LUTRAM 同样占用 FPGA LUT 资源。
原生 carry 打包、布局、连线、时钟偏差、setup/hold 均未签核。
`path_depth.py` 只测映射后的逻辑图路径，不输出未经证实的 ns / MHz / WNS。
Yosys 自带某些 Xilinx 时序模型源自其他器件，不能拿来当 ZU15EG-2 时序库。

Icarus 对整数 lane 的映射网表另跑事件驱动参考延迟仿真，包含零延迟对照、
setup/hold 检查器故意违规对照，以及两组明确声明的假设延迟。
这部分只覆盖整数 lane，未校准器件，不包含布局布线/PVT/时钟树，也不是 AMD SDF。
资源更省、路径更短或假设延迟仿真通过，都不能据此宣称真实器件达到相应频率。
M4 浮点完成 RTL/映射网表功能仿真和无时间的路径分析；整数参考延迟结果不适用于 FP。
原有后处理长链已经切分，仍需真实器件时序验证。
用户已用 Vivado 2025.1 实现 M4：OOC setup +0.346 ns、hold +0.042 ns；但 HD.CLK_SRC 未指定，宿主 IO 延迟未约束。
RapidWright 已读取这份 DCP/EDIF、解析 6 个 DSP 的 546 条边界延迟，并构建参考时序图。
M5 的本地 OOC 结果为 setup +0.477 ns、hold +0.036 ns；云端完成 M4/M5 各 20 条关键路径的参考图对照。
这些结果均不能继承为 M8 的实现结果，详见 [M5 核对](reports/cloud-m5/evaluation.md) 及 [使用边界](docs/rapidwright.md)。

最终 `.bit` 生成和 ZU15EG-2 的实际时序仍需要支持该器件的 AMD 实现工具。
此工程不生成假的 bitstream，也不把开源映射结果当作 300/500 MHz 已通过。

- M31：整数零/符号扩展，独立源 EEW 与 EMUL 重叠检查；当前 Windows XSim + 300MHz OOC 验证包见 [本地步骤](docs/m31-integer-extensions.md)。

- M32：vnsrl/vnsra窄化整数移位；宽源与窄移位向量独立寻址、合法低位重叠与不同EEW源别名检查，保持原流水和RAM资源。

- M33：16种宽化整数加减，双宽候选目的组、独立源几何和最高部分重叠检查；仍为单指令流水。

- M34：6种完整双宽整数乘法，复用原乘法器和RAM，含混合符号与串行返回目的偏移检查。
- M35：8种单宽整数乘加，复用原乘法器与流水ALU；LSU块地址提前寄存，保持访存周期。
- M36：7种宽化整数乘加、6种反减/大于比较、4种整组寄存器搬运；宽化旧目的操作数独立寻址，整组搬运忽略VL/LMUL/vill并支持vstart。

- M43：8种跨步访存编码；无掩码访存及64位load减少RF读取；算术回归按精确输入/证据SHA安全复用，缺失缓存则完整执行。

- M44：16种索引load/store编码，零扩展字节偏移、ordered访问、合法宽窄别名，共享RAM端口和分段加法器。
