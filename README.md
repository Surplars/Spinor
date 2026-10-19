# 砺矢 · Spinor VPU

Valence SoC / Orbital CPU / Spinor VPU。目标器件 `xczu15eg-ffvb1156-2-i`，
采用 **Mill 1.1.7 / Scala 2.13.18 / Chisel 7.16.0**，按 300 MHz 设计。

**当前 M57：ISA 目录清账与分段访存覆盖补齐。** 官方375条基础V、16条Zvbb
目录逐项对应，未发现目录漏项；310种访存形式均有成功样本。完整ISA语义验收
仍未关闭。硬件保持M56：VLEN128/ELEN64、单lane、单指令在途、版本化RAM。
CPU持有宿主FCSR，VPU锁存frm并返回逐指令flags；宿主/独立monitor ID保持0x5602/0x5501。

- [当前进度](CURRENT.md)、[ISA 实现与验收清单](docs/m57-isa-audit.md)
- [M57 验证](reports/m57/evaluation.md)、[M56 接口与边界](docs/m56-host-fcsr.md)
- [M56 验证/资源/时序](reports/m56/evaluation.md)、[M55 Zvbb 集合](docs/m55-zvbb.md)
- [规模参数](docs/m39-configurations-and-fp-transfers.md)、[CPU 接入契约](docs/cpu-spinor-contract.md)
- [独立上下文镜像](software/context/spinor_context.h)、[FP16 最小转换](docs/m54-half-conversions.md)

基础整数、定点、掩码、置换、归约、FP32/64、两种最小 FP16 转换和向量访存已有
实现及独立验证。**尚未声明完整 V/RVA23/Zvkt，尚未接入实际 Orbital/Linux。**
完整 Zvfh、BF16、向量 crypto、多 lane/更大 VLEN 不在当前范围。规模预设调节
FP 开关和整数分段宽度，不能任意修改尚未改造的 VLEN/ELEN/lane。

访存接口预留 TileLink，当前仅物理普通 RAM、单事务、逐元素提交；地址保护/
翻译、MMIO 语义和缓存一致性待宿主接入。**访存期间 flush 必须等待 Completion/
status，不能按算术指令立即丢弃 token。** 见 [访存契约](docs/m10-memory.md)。
监控 MMIO 提供容量、忙闲/计数等状态；ARM 作业队列和 Linux 驱动仍待实现。

## 生成硬件

Linux x86-64、Java21、Python3.12+：

```bash
git clone https://github.com/Surplars/Spinor.git
cd Spinor
make bootstrap
./mill Vpu.runMain vpu.GenerateConfigured --out build/configured --name SpinorVpu --preset standard
```

预设为 `standard`、`deep`、`integer`、`integer-deep`。输出 SV 和配置 JSON，
原生 Orbital 共享 FCSR 时加 `--fcsr-owner host`，FCSR CSR 留在 CPU；默认
`standalone` 继续用于独立验证。JSON 明确列出 FCSR 所有者、FP、Zvbb、规模及 `device_timing_verified:false`。
工具首次下载需要网络，下载地址和版本由仓库锁文件约束。

## 当前验证与时序

M57标准/Deep预设新增175,556条Spike差分命令和2,024条独立保留策略命令，
包含原始解码、vtype/CSR及全部310种访存形式；补齐此前12种分段形式的成功样本。
原始解码扫描在VL0进行，不冒充算术数值测试。本轮硬件不变，整数/宿主预设沿用
历史证据。M56两宿主预设各43,560个延迟抽样仍不构成完整Zvkt合规证明。

默认宿主 Yosys xcup：**24,247 逻辑 LUT、13,882 FF、9 DSP**，RAM 数量保持。
公共/计算顶层固定云端条件预算均 **3.300ns**，≤3.333ns。模型排除 DSP 影响端点
和主输入/输出，不含器件布局布线/真实时钟，未按 -2 校准，不能作为 STA。
本轮沿用M56条件预算，实际300/500MHz仍未知，宿主侧带还需SoC时序约束。

最新本地证据是 [M53 Vivado 报告](reports/local-m53-resume/evaluation.md)：旧 RTL
300MHz OOC setup +0.090ns、hold +0.042ns，不自动适用当前RTL。宿主 IO 和实际时钟源
还需 SoC 约束。[实际 DSP 表及配置限制](reports/dsp-m53/evaluation.md) 单独保留。

在**已有 M55/M56 固定工具及参考产物的云端工作区**，当前验收入口：

```bash
python3 scripts/verify_m57.py
python3 scripts/verify_m57.py --check-only
```

`--check-only` 对验收时的精确源码/产物散列进行审计。Git 保存源码、报告、冻结
历史源码；`build/`、`tools/` 和发布 ZIP 不入库，单独 clone 不具备工作区内全部
历史验收产物，不能直接核对这些现成散列。新机器可先生成硬件，工具/历史产物准备
和完整验收步骤见各里程碑报告及 [仓库说明](docs/repository.md)。

[位特征/扩宽移位汇编示例](software/programs/bit-features.S) 已通过 Clang19 汇编
及真实机器字检查；[C 接口](software/programs/bit-features.h)。这是编译检查，
没有声称已在真实 Orbital/Linux 运行。

历史里程碑报告与本地原始证据保留原版本，不将历史通过计为新硬件通过。
