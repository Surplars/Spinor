# M54：FP16 最小转换已实现

新增 SEW16 的 vfwcvt.f.f.v / vfncvt.f.f.w，对应 Zvfhmin 的 FP16↔FP32 转换定义。
复用原 RAM、调度和扩缩宽状态机，新增半精度解码/舍入路径；单 lane、单指令在途。
monitor 实现号 0x5401，ABI1、能力位布局及 576 字节上下文格式保持。Orbital 未修改。
具体 ISA 支持/缺口、规范来源和运行条件见 [设计说明](../../docs/m54-half-conversions.md)。

## 新功能的独立证据

- SoftFloat RTL：86,136 个向量，穷举全部 65,536 个 FP16 编码扩宽；
  FP32→FP16 覆盖 5 个舍入模式、边界/特殊值及随机数，另检查非法模式和 44 个 flush 时点。
- 真实综合网表：1,930 个代表数值样本和 44 个 flush 时点。是有界子集，
  不称为全部 half 编码的网表覆盖。一次重复的完整网表数值矩阵因运行预算主动停止，
  不计入通过；改以完整 RTL 穷举及代表网表验证收尾，attempt 记录保留。
- 新 half rounder 对 pinned HardFloat 的 10 步 SAT 等价：任意 held raw bits、所有模式/
  特殊标志与 done 非空见证；局部证明，不是整个 VPU 的证明。
- Standard / Deep 真实公共顶层分别完成 4,611 条新增几何/模式/重叠/非法边界命令，
  对照未修改上游 Spike，ISA 明确启用 Zvfhmin。没有把完整 Zvfh 或 SEW16 round-to-odd 放开。
- 独立 SV/SoftFloat 的完整宽度转换回归：11,372 条命令；
  Deep 代表矩阵 141 条，包含半精度非零 vstart、掩码及 flush。

## 当前硬件回归

四预设的基础算术/访存/扩展访存边界全部在 M54 公共 GSim 顶层重跑；Deep 的基础
算术/访存采用已界定 compact 矩阵。加上半精度矩阵，共 **73,152 条 Spike 差分命令**。
完整 RF/CSR 检查，访存还比较 8KiB RAM、故障/重试和 TL 事务。375 种原有基础编码均有
成功执行点，见 [逐项目录](canonical-coverage.csv)；新增的是两条已有编码的 SEW16 定义，
不是把编码数加二，也不是合规百分比。

保留混合 EEW store 独立拒绝策略每预设 72 场景/216 命令，明确不标为 Spike 一致性。
两个整数预设各检查 320 个浮点/CSR 拒绝点；四预设读取 monitor ID 0x5401 并检查反压。
上下文回归共 **2,212 场景、1,104 个前/后效果失败注入**，加损坏镜像
及 ASan/UBSan 校验，原 C ABI 在新硬件保持可用。上述矩阵共 **86 次比较器错误注入**
均检出，包括 token、RF、CSR、RAM、访存故障地址和上下文恢复/所有权。

LLVM19 为真实 FP16↔FP32 strip-mining intrinsic 示例生成目标转换和向量 load/store。
本轮是编译检查，尚未在真实 Orbital/Linux 执行该示例。

## 资源与时序

默认公共顶层 Yosys xcup：**23,227 逻辑 LUT、13,359 FF、9 DSP**；较 M53 同工具
基线 +21 LUT/+155 FF，RAM64M8×32、RAM32M16×6 不变，没有新增 RF 快照或 DSP。
固定 M25 权重和 100ps/link 门槛重跑：公共顶层 **3.300ns**，计算/访存顶层
**3.232ns**，均≤3.333ns。

该模型仍排除 DSP 影响端点、未布局布线/按 ZU15EG-2 校准，不是 STA/SDF。M53 的
实际 Vivado +0.090/+0.042ns 结果仅适用旧 RTL；M54 的器件 300/500MHz 仍未知。
本轮没有要求再跑本地 Vivado。实际 DSP 表不能移用于当前无内部寄存器的 Yosys DSP。

基础 V 的操作数/异常审计、真实退休、VS/FS/FCSR、地址保护/翻译、一致性和驱动
仍有系统工作。Zvbb 尚未实现，Zvkt 尚未完成专门审计；不能声明完整 V/RVA23。

## 基线和复现

变更前 M53 全部证据已验证，48 个 Scala 文件冻结到 archive/m53/source。变更的
4 个历史文件按旧副本核验，其余历史源码/工具/产物严格原散列；新硬件全部产物位于
build/m54，旧 RTL/网表和本地报告保持版本。历史检查通过不计作 M54 硬件回归通过。

在已有 M53 工具及产物的环境运行：

```bash
python3 scripts/verify_m54.py
python3 scripts/verify_m54.py --check-only
```

receipt 绑定源码、独立模型、原始语料、生成 RTL/网表、运行日志、局部证明和条件预算。
没有部署、bitstream、板上运行、整核 difftest 或实际 Linux 上下文切换声明。
