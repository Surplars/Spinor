# Spinor VPU

Spinor（砺矢）是使用 Chisel 和 Mill 开发的 RISC-V 向量协处理器，面向 FPGA，优先使用 RAM 保存向量寄存器和候选结果。当前按 `xczu15eg-ffvb1156-2-i`、300 MHz 目标设计。

提供原始指令命令接口、TileLink A/D 数据访存端口、上下文访问端口和独立的 MMIO monitor。可作为原生 RISC-V 向量执行单元接入，也可用于构建由其他处理器管理的加速器。

## 当前能力

| 项目 | 当前配置 |
|---|---|
| 向量规模 | VLEN 128、ELEN 64，32 个架构向量寄存器，共 512 字节 |
| 执行结构 | 单 lane、单指令在途；部分整数操作支持元素间流水重叠 |
| 运算 | 整数、定点、掩码、置换、归约、FP32/FP64、Zvfhmin 最小转换、Zvbb |
| 访存 | 单位步长、跨步、索引、分段、整组、mask 和 fault-only-first；物理普通 RAM |
| 接口 | 80 位命令身份、完成握手、64 位 TileLink A/D、4 KiB monitor |
| 工具链 | Mill 1.1.7、Scala 2.13.18、Chisel 7.16.0 |

当前功能与验证状态见[进度说明](CURRENT.md)和[ISA 覆盖表](docs/isa-coverage.md)。尚未声明完整 V/RVA23/Zvkt 合规，也尚未完成实际 CPU/Linux 集成。地址翻译、PMP 和缓存一致性需要系统侧接入；monitor 提供观测功能，计算作业队列和专用 Linux 驱动仍待实现。

## 快速生成

开发环境：Linux x86-64、JDK 21、Python 3.12+、GCC 和 Make。Windows 建议在 WSL2 中进行 Chisel 构建，再将生成文件交给 Windows Vivado。

```bash
git clone https://github.com/Surplars/Spinor.git
cd Spinor
make bootstrap
./mill Vpu.runMain vpu.GenerateConfigured --out build/configured --name SpinorVpu --preset standard
```

输出包含 `SpinorVpu.sv`、配置清单 `SpinorVpu.json` 和生成器拆分出的辅助文件。将输出目录中的相关 SV 文件一并加入工程。首次准备工具需要网络和磁盘空间，版本及下载散列见 [tools.lock.json](tools.lock.json)。

| 预设 | 浮点 | 整数分段位宽 |
|---|---|---:|
| `standard` | 开启 | 32 |
| `deep` | 开启 | 16 |
| `integer` | 关闭 | 32 |
| `integer-deep` | 关闭 | 16 |

预设不改变 VLEN/ELEN、lane 数或指令在途容量。原生 CPU 与标量 FPU 共享 FCSR 时使用 `--fcsr-owner host`，详见[接入指南](docs/integration.md)。

## 接入与使用

- [接入指南](docs/integration.md)：选择配置、连接端口、提交/取消、浮点状态、上下文及首次联调。
- [CPU 提交协议](docs/cpu-spinor-contract.md)：指令所有权、完成授权和异常映射。
- [TileLink 与访存](docs/tilelink.md)：总线参数、物理窗口、错误和停止规则。
- [MMIO monitor](docs/monitor-soc.md)：寄存器、快照、Linux UIO 工具和多宿主访问。
- [构建与仓库](docs/repository.md)、[验证与时序](docs/validation.md)、[全部文档](docs/README.md)。

## 验证与时序

最新功能验证为 M60：标准/Deep 合计 726,000 条命令通过，覆盖全部 330 种算术编码的重启分类。[报告](reports/m60/evaluation.md)保留参考方法、错误注入和覆盖边界；[ACT4 接入清单](docs/act4-intake.md)记录官方架构测试的后续工作。

云端宿主配置沿用 **3.300 ns 条件估计**。该模型不含器件布局布线和真实时钟，排除 DSP 影响端点，不能作为实际 300 MHz 时序签核。当前 RTL 仍需 Vivado 综合、实现和完整约束验证；旧版本的本地通过结果仅作历史参考。

构建工具和完整测试产物不随 Git 保存，复现条件、文档检查和证据核对方式见[验证说明](docs/validation.md)。
