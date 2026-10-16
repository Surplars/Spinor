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
| `reports/m21/` | 当前 M21 评估及源码/证据 SHA-256 清单 |
| `archive/` | 冻结的历史报告、RTL 与回归输入 |
| `third_party/` | 固定版本硬件依赖、仿真模型及许可证 |

`archive/m20/synth-SpinorVpu/mapped.json` 是 M21 云端预算对照所需的历史网表，属于冻结回归输入；M17/M19 对照也继续保留。其余历史报告保留当时的路径和名称，不代表所有旧验证命令都支持当前源码。

## 构建与验证

需要 Linux x86-64、JDK 21、Python 3.12+、GCC、Make，以及访问 `tools.lock.json` 中固定下载地址的网络。版本由 Mill 构建文件和工具锁文件指定。

```bash
make bootstrap
./mill Vpu.compile
make rtl
```

完整 M21 验证会自动准备 SoftFloat 和 RapidWright，然后执行 RTL、映射后功能回归、资源评估与条件时序预算：

```bash
python3 scripts/verify_m21.py
python3 scripts/package.py --milestone m21
```

生成工具与缓存写入 `tools/`，RTL、测试台、日志和网表写入 `build/`，发布 ZIP 写入仓库根目录。这些生成文件不进入 Git。完整验证会重新生成 `reports/m21/receipt.json`；其中源码 SHA 可以直接核对，`build/` 证据 SHA 需要相应生成文件。

初始导入的功能证据来自已经完成的 M18 验证。导入仓库时补上了验证入口中 SoftFloat 和 RapidWright 的准备步骤，并修正文档，硬件源码保持与 M18 源码包一致。仓库内没有安装后的工具、凭据、Vivado DCP 或 bitstream。

## SoC 接入

先阅读 [CPU 接入合同](cpu-spinor-contract.md)、[monitor MMIO](monitor-soc.md) 和 [ISA 覆盖表](isa-coverage.md)。`VpuHostBoundary` 是独立配套模块，尚未接入实际 Orbital。当前单条指令在途，支持部分 RVV；尚不能对软件声明完整 V/RVA23。

300 MHz 是设计目标。云端 RapidWright/Yosys 结果是条件预算，当前 M21 没有器件布局布线时序结论。
