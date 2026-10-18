# Spinor 仓库使用说明

本仓库由 M18 源码包初始化，公开顶层为 `vpu.SpinorVpu`。Valence 是 SoC，Orbital 是 CPU，Spinor 是 VPU；中文名称保留“砺矢”。

## 目录

| 路径 | 内容 |
|---|---|
| `src/main/scala/vpu/` | Chisel 硬件和 RTL 生成入口 |
| `tests/` | 独立参考模型、RTL 和映射后功能测试 |
| `scripts/` | 工具准备、综合、条件时序预算、报告与打包 |
| `software/monitor/` | Linux UIO monitor 用户态工具及寄存器定义 |
| `docs/` | 指令覆盖、CPU/TileLink 协议和设计记录 |
| `reports/m42/` | 当前 M42 评估及源码/证据 SHA-256 清单 |
| `archive/` | 冻结的历史报告、RTL 与回归输入 |
| `third_party/` | 固定版本硬件依赖、仿真模型及许可证 |

M42保留两份冻结时序输入：`archive/m25/synth-SpinorVpu/mapped.json.gz` 固定参考权重与预算模型的基线，`archive/m40/synth-SpinorVpu/mapped.json.gz` 用于和前一版M40比较。验证入口分别通过 `prepare_m26_baseline.py` 和 `prepare_m42_baseline.py` 恢复，并核对原始网表SHA；M40的冻结RTL另用于旧性能对照。不能重新映射当前源码来替代历史输入，也不能通过修改固定权重放宽300MHz条件门槛。

历史 `archive/m21/synth-SpinorVpu/mapped.json.gz` 是M22预算对照所需的冻结输入；M17/M19/M20等历史对照继续保留。旧报告保留当时的路径和名称，不代表所有旧验证命令都支持当前源码。

## 构建与验证

需要 Linux x86-64、JDK 21、Python 3.12+、GCC、Make，以及访问 `tools.lock.json` 中固定下载地址的网络。版本由 Mill 构建文件和工具锁文件指定。

```bash
make bootstrap
./mill Vpu.compile
make rtl
```

完整M42验证会自动准备SoftFloat和RapidWright，然后执行RTL、定向映射后功能回归、局部证明、资源评估与固定条件时序预算。当前映射后覆盖范围和输入散列以[M42报告](../reports/m42/evaluation.md)为准，不等同于完整ISA矩阵：

```bash
python3 scripts/verify_m42.py
python3 scripts/package.py --milestone m42
```

四个预设的验证层隔离保存在`build/profiles/rtl/<Top>/`，顶层SV/manifest在`build/rtl/`保留兼容副本。`check_regeneration.py`对默认生成入口的硬件及验证层做重生成逐字节检查。

生成工具与缓存写入 `tools/`，RTL、测试台、日志和网表写入 `build/`，发布包 `spinor-vpu-m42.zip` 写入仓库根目录。这些生成文件不进入Git。完整验证会重新生成 `reports/m42/receipt.json`；其中源码SHA可以直接核对，`build/` 证据SHA需要相应生成文件。打包前检查源码和证据散列，包内保留复现所需的冻结基线。

初始导入的功能证据来自已经完成的 M18 验证。导入仓库时补上了验证入口中 SoftFloat 和 RapidWright 的准备步骤，并修正文档，硬件源码保持与 M18 源码包一致。仓库内没有安装后的工具、凭据、Vivado DCP 或 bitstream。

## SoC 接入

先阅读 [CPU 接入合同](cpu-spinor-contract.md)、[monitor MMIO](monitor-soc.md) 和 [ISA 覆盖表](isa-coverage.md)。`VpuHostBoundary` 是独立配套模块，尚未接入实际 Orbital。当前单条指令在途，支持部分 RVV；尚不能对软件声明完整 V/RVA23。

300MHz是设计目标。云端RapidWright/Yosys结果是未布局、未按-2速度档校准的条件预算。M42没有器件布局布线时序结论；[M31本地OOC结果](../reports/local-m31/evaluation.md)属于历史输入，不能继承为M42或完整SoC时序通过证明。

M42另冻结`archive/m41/rtl/FloatingPointConvertResize.sv`，用于11340组逐输入周期/数值对照；该基线由M41原receipt散列校验，不能用当前生成RTL替代。

M42复现入口优先调度新增估算、转换和公共接口测试，保持每个测试族内的完整/精简变体顺序；每个已完成族的账本原子落盘。已有账本可通过`regress_m42.py --only <逗号分隔的族名>`替换指定族，网表阶段加`--mapped`；最终报告仍强制134项RTL和31项定向网表全部成功，不能用部分账本交付。
