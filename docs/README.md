# 文档导航

首次使用从[接入指南](integration.md)开始；查看项目能力和生成命令见[项目首页](../README.md)。

## 构建与接入

| 文档 | 内容 |
|---|---|
| [源码导航](../src/README.md)与[开发规范](development.md) | 功能目录、阅读顺序、注释与评审规则 |
| [工具导航](../scripts/README.md)与[测试导航](../tests/README.md) | 当前入口、参考模型和历史脚本范围 |
| [构建与仓库](repository.md) | 工具、输出目录、新环境与历史验证产物 |
| [接入指南](integration.md) | 配置、端口、CPU/作业执行器接入和首次联调 |
| [寄存隔离顶层](m61-isolation.md) | 新工程的寄存边界、preview/grant/done和时序隔离证据 |
| [CPU 提交协议](cpu-spinor-contract.md) | 所有权、完成授权、取消与异常映射 |
| [TileLink 与访存](tilelink.md) | 数据主端、物理窗口、错误、停止和恢复单位 |
| [MMIO monitor](monitor-soc.md) | 地址、寄存器、快照和 Linux UIO 使用 |
| [上下文 helper](../software/context/README.md) | 576 字节镜像、保存恢复和回调所有权 |
| [架构概览](architecture.md) | RAM 结构、指令/元素流水与宿主职责 |
| [验证与时序](validation.md) | 当前证据、复现条件和器件时序边界 |

## 当前功能与验收

- [当前进度](../CURRENT.md)、[ISA 覆盖](isa-coverage.md)、[RVV 验收计划](rvv-completion-plan.md)。
- [源码整理验收](../reports/repository-layout/evaluation.md)：token对照、8个顶层RTL逐字节相同及历史证据审计。
- [M61隔离顶层](m61-isolation.md)与[报告](../reports/m61/evaluation.md)。
- [M60 重启分类](m60-classified-restart.md)与[报告](../reports/m60/evaluation.md)。
- [M59 类型重叠](m59-overlap-restart.md)、[M58 策略与恢复](m58-semantics.md)。
- [宿主 FCSR](m56-host-fcsr.md)、[Zvbb](m55-zvbb.md)、[最小 FP16 转换](m54-half-conversions.md)。
- [ACT4 接入条件](act4-intake.md)：已固定来源，尚未生成或运行官方 ELF。

## 历史设计记录

`m*.md`、`reports/m*/` 和 `archive/` 按当时版本解释。某些旧记录描述未实现的功能、旧 ID 或实验接口，当前接入以本页上方指南、生成清单和对应源码为准。

| 主题 | 记录入口 |
|---|---|
| 规模预设 | [M39](m39-configurations-and-fp-transfers.md) |
| 访存演进 | [单位步长](m10-memory.md)、[跨步](m43-strided-memory.md)、[索引](m44-indexed-memory.md)、[分段](m46-segment-memory.md)、[FOF](m48-fault-only-first.md) |
| 浮点与宽窄运算 | [FP reductions](m28-fp-reductions.md)、[宽化浮点](m40-wide-floating-point.md)、[转换](m41-width-conversions.md) |
| 编译器程序测试 | [M49](m49-compiled-programs.md) |
| 时序工具 | [RapidWright](rapidwright.md)、[M53 本地结果](../reports/local-m53-resume/evaluation.md) |
| 实验功能 | [乱序窗口](ooo-window.md)，未集成到当前公共顶层 |

本次文档整理前的入口文档保存在[文档快照](../archive/docs-m60/source/README.md)，不修改历史报告来更新项目介绍。
