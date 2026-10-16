# 砺矢（Lishi VPU）M9：同宽转换与 TileLink 预留

本轮新增六种 FP32/FP64 同宽整数↔浮点转换，及已实现、独立测试的 TileLink A/D 单事务边界。TileLink 尚未接向量 LSU，没有新增向量访存指令或完成 Valence 接入。

## 转换与回归

- `vfcvt.xu.f.v / vfcvt.x.f.v / vfcvt.f.xu.v / vfcvt.f.x.v / vfcvt.rtz.xu.f.v / vfcvt.rtz.x.f.v`，SEW32/64，同宽 signed/unsigned、五种合法 frm 和固定 RTZ。
- 普通转换遇保留 frm 拒绝执行；RTZ 不依赖 frm，保留 frm 下仍可执行。保留 mask/prestart/tail、别名、版本原子提交和 fflags 延迟提交。
- 独立转换单元 RTL：5021 组 SoftFloat 对照，14 个额外手工锚点，492 个 flush/reset；嵌入 FP lane 后另测 5019 组及 492 个撤销/复位场景。
- 转换单元映射后：5021 组、60 个代表性 flush/reset，必须通过后才能生成本报告的最终收据。映射后的测试范围不等同于完整 VPU 的全部指令网表回归。
- 原有 FP 数值回归重新执行：6811 组、205 个 flush/reset，52 个原有常量锚点，检查结果损坏时 oracle 会拒绝。
- 整机转换/FP/乘除法混合回归：2157 条命令、9512 次读取、196 个指令撤销、2 个上下文写后撤销，含 9 种 FP 合法 SEW/LMUL 组合和 270 个常规转换测试；另含保留 frm/子码检查。分级写回与在途排空断言启用。
- 既有整数整机回归：1673 条命令、5126 次读取；整数多元素在途专项继续通过，观察到 2 个元素在途和 15198 次物理行安全的读写重叠。

独立 SoftFloat 默认整数 invalid 饱和值特化与 RISC-V 不同，测试包装器仅在 NV 时按 ISA 修正结果，舍入和标志仍由 SoftFloat 计算；未修改其源文件。HardFloat 派生转换器保留完整许可证。说明见 [转换文档](../../docs/m9-conversions.md)。

## TileLink 预留

`TileLinkReservation` 默认 64-bit 地址/数据、source4、sink1、size3，仅 A/D，支持自然对齐的 1/2/4/8-byte Get、PutFullData、PutPartialData，一个 source=0 事务在途。

`LishiVpuTileLinkReserved` 转接原算术端口，并预留外部驱动的 memoryRequest/memoryResponse 和 TL A/D。数据与 mask 在内部右对齐，桥负责总线 lane 放置。接口字段已与本地 Valence 源码核对，没有直接引入或修改其仓库。

RTL、映射后桥、完整预留封装的总线侧各执行同样 600 组测试：36 个本地拒绝、112 个同拍 A/D、459 个实际 flush 场景、41 个畸形返回检测，564 个已发布 A 均排空了 D。封装测试保持算术命令静止，不代表 LSU 与总线联合验证。

A 在背压时跨 flush 保持，已发布事务排空后才复用 source；store 必须预先获得 irrevocable 授权。桥不能回滚 store，也不实现翻译、PMP、缓存一致性或精确存储故障。完整合同见 [TileLink 文档](../../docs/tilelink.md)。

## 云端时序筛选与资源

云端曾发现转换路径把 IEEE 重编码、对齐和判断串成 22 个映射单元跳数。增加重编码寄存边界，并将易被 ABC 合成长链的逐位增量结构改为局部 16 位进位组后，最终转换单元为 15，整机为 16。切分前快照保存在 screening-before-recode-cut，仅作调试证据。

| Yosys xcup 自动映射 | M8 算术顶层 | M9 算术顶层 |
|---|---:|---:|
| 逻辑 LUT | 11054 | 12784 |
| FF | 8093 | 9002 |
| DSP48E2 | 9 | 9 |
| RAM64M8 / RAM32M16 | 32 / 6 | 32 / 6 |
| 最长数据单元跳数 | 16 | 16 |

算术顶层增加 1730 个逻辑 LUT、909 FF；DSP 与存储映射不变。独立转换器为 1864 LUT、917 FF；独立 TileLink 桥为 395 LUT、373 FF、0 DSP。桥资源不包含在上述 RamVectorFp 表中，不能把两个独立模块之和当成封装完成布局布线后的资源结果。

RAM 写入锥审计继续通过。单元跳数包含 LUT、CARRY 和其他映射单元，不是延迟，不提供 Fmax。M9 没有 Vivado 实现、SDF 或板级时序确认；300/500 MHz 状态仍未知，不继承 M5 的 WNS。本轮不要求用户再次运行本地 Vivado。

M8 性能报告保留为历史周期对照。M9 普通 FP/整数回归周期未回退，但本轮没有重新执行完整 220 组性能矩阵；新转换保持容量 1，不计入 M8 的加法吞吐。

复现：`make verify-m9`，然后 `make package-m9`。输入散列、每项测试范围与最终工具结果见 receipt.json。
