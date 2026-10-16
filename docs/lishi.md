# 砺矢 · Spinor VPU

项目中文名称为 **砺矢**，英文名称为 **Spinor VPU**，公开 Chisel 类名为 `SpinorVpu`。SoC 名称为 Valence，CPU 核名称为 Orbital。

“砺”表示持续打磨实现，“矢”对应向量与明确方向；Spinor（旋量）与 Orbital 呼应。M18 起发布包使用 `spinor-vpu` 标识。旧版 `LishiVpu*`、`RamVectorFp` 等内部类名及历史发布包保留，便于核对既有报告。

目标是为 ZU15EG-2 上 Valence SoC 中的 Orbital RV64 核提供向量协处理能力。优先 RAM 友好的寄存器文件、可验证的状态提交和可切分的算术路径，以 300 MHz 为基线设计目标。当前为 VLEN128/ELEN64、单指令顺序执行的部分 RVV 原型，容量与吞吐取决于具体执行单元。

M18 新增八种同宽整数归约和独立 CPU 提交边界模块；M19 新增八种掩码逻辑与两种整数标量搬运，M20 增加掩码扫描并优化 FP/monitor 路径，M21增加字节并行mask通路，详情见 [M21 说明](m21-byte-mask.md)、[CPU 接口合同](cpu-spinor-contract.md) 和 [指令覆盖表](isa-coverage.md)。尚无完整 RVV 或实际 Orbital 核接入，不能发布完整 V/RVA23 合规声明。下文保留各里程碑的实现记录与当时的复现命令；当前版本使用 `make verify-m21` 和 `make package-m21`。

## M7 除法结构

共享容量为 1 的恢复除法器。先将有符号操作数变为幅值，每个商位按“移位、低 32 位试减、高 33 位试减、选择”四个周期执行，最后分别修正商/余数符号。幅值转换和结果符号修正均按低/高 32 位切分。没有使用组合 `/` 或 `%` 运算符，没有新增 DSP。

除零遵循 RISC-V 语义：商为 SEW 个 1，余数等于原被除数；有符号最小负数除以 -1 返回原最小负数，余数 0。商向零截断，非零余数符号与被除数相同。不产生整数除法异常，也不修改 fflags/frm/vxsat。

flush 取消控制所有权，禁止同拍握手，不清除数据 RAM；未确认指令的候选结果不能成为已提交状态。响应可背压且保持稳定。逐周期实现降低吞吐，不能据此宣称 300/500 MHz 已达标。

## 云端复现

```bash
make verify-m7
make package-m7
```

这会生成 RTL，执行新除法单元的数值/flush 检查、整机乘除法与 CSR/掩码/LMUL 回归、FP 交错测试、Yosys 资源/组合链检查和映射后功能验证。完整 FP 数值单元与乘法单元的 RTL 若与 M6 SHA 一致，可明确复用其独立单元验证；当前整机接入仍重新测试。

针对旧的真实布线结果，可用 `scripts/cloud_timing_screen.py` 建立参考图并对照 Vivado；旧 DCP 不提供新 M7 RTL 的布局布线。当前 M5 的物理结果保留在 `reports/cloud-m5`，M7 的时序通过状态仍未知。本轮不要求本地重复实现。

## M8 元素重叠与性能测量

M8 不新增 ISA。基础整数非掩码结果运算解耦发射和退休：发射时递增元素索引，以 lane 的元素 tag 重建返回结果的目的行、字节使能和位偏移，用在途计数等待全部结果排空。跳过被屏蔽元素不占执行名额。比较产生掩码仍走串行读改写，FP/乘除法也保持容量 1。

所有源读已提交版本，所有结果写候选版本；即使 vd=vs2/vs1，也不会因先写结果覆盖后续源。完成必须等在途计数和写回阶段排空，flush 同时取消 lane 有效位及指令所有权。没有跨指令发射或乱序提交。

`make performance` 对冻结 M7 与当前 RTL 跑相同 220 组结果校验与周期测试，输出报告及 CSV。`make verify-m8` 包含功能、结构、并发/撤销与映射后检查，`make package-m8` 输出发布包。细节见 `reports/m8/performance.md`；此版本尚无新的器件时序结论。

## M9 转换与 TileLink 预留

新增六种同宽转换，详见 `docs/m9-conversions.md`；增加可独立验证的单事务 TileLink A/D 主端和 `LishiVpuTileLinkReserved` 封装，详见 `docs/tilelink.md`。物理请求口暂由接入侧驱动，不代表已经实现向量访存。

`make verify-m9`、`make package-m9` 生成当前验证报告与源码包；M8 性能数据作为历史对照保留，不把 M9 新转换算作已测试的 M8 算术吞吐。

## M10 最小访存闭环

新顶层 `LishiVpuMemory` 实现连续地址 vle/vse，经 TileLink 读写普通物理 RAM，支持元素前缀提交、故障 vstart 恢复和延迟停止。host 必须在 flush 后保留不可撤销访存指令，等待完成状态；具体合同见 `docs/m10-memory.md`。验证与周期参考见 `reports/m10`，`make verify-m10`、`make package-m10` 复现。没有实际 CPU 接入或板级频率结论。

## M11 访存进度提交优化

专用 vstart 提交替代逐元素 CSR 指令往返；未增加指令种类或多请求窗口。M10 故障前缀与延迟停止规则保留。见 `docs/m11-memory-commit.md` 和 `reports/m11`。

## M12 单块寄存器缓存

复用 LSU 原有 64 位数据寄存器，增加标签和有效位；load 写回同步更新缓存，仍逐元素提交。见 `docs/m12-chunk-cache.md`、`reports/m12`。

## M13 浮点输入路径切分与条件时序预算

拆分 FP32 输入规格化和指数扩展，合法 FP lane 请求增加一个周期。新增基于固定 RapidWright 家族表和显式连线假设的云端预算，排除未覆盖 DSP 的端点，不发布 Fmax。见 `docs/m13-timing.md`、`reports/m13`。请求队列尚未加入。

## M14 乘法与重编码时序优化

整数乘法用固定位置循环字组取代动态读写选择，保持原有周期；FP64利用现有recodeFinish边界，浮点转整数单独增加前导零计数阶段。新精确编码辅助函数对固定HardFloat编码器通过全部64位输入SAT等价证明。见 `docs/m14-timing.md`、`reports/m14`。

## M15 分段进位与除法取反

除法条件取反改为两个并行16位增量段；乘法、试减、浮点累加和转换输入使用16位边界carry-select。周期数不变，增加部分组合逻辑和专用进位资源；全输入SAT证明及云端同模型预算见 `docs/m15-carry-select.md`、`reports/m15`。

## M16 地址、前缀增量与配置译码

LSU低字复用carry-select，高字用逐位前缀递增；FP后处理增量改为逐位前缀，配置长度选择使用高位归约与8位比较。无新流水级。新增32组地址边界用例和全输入公式等价证明。条件预算仅中高连线假设略降，见 `docs/m16-prefix-address.md`、`reports/m16`。
