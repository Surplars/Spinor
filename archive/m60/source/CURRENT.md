# 当前进度

硬件与功能验证版本为 **M60**。本次更新整理项目入口、接入指南和文档导航，没有改RTL或增加功能验证轮次。

- [接入指南](docs/integration.md)：配置、公共端口、提交/停止、FCSR、上下文和首次联调。
- [文档导航](docs/README.md)、[构建说明](docs/repository.md)、[验证与时序](docs/validation.md)。
- [M60报告](reports/m60/evaluation.md)、[逐编码重启覆盖](reports/m60/restart-coverage.csv)。
- [ISA覆盖](docs/isa-coverage.md)、[RVV验收计划](docs/rvv-completion-plan.md)、[ACT4接入条件](docs/act4-intake.md)。

M60标准/Deep合计726,000条分类参考命令通过。330种算术编码均有合法样本，307种有非零起点可见结果，23种按限制拒绝；每预设72,600个目标中50,914合法、21,686拒绝。普通执行mask变换与carry/merge、whole/scalar例外分开处理，非直接非零Spike差分。完整范围以报告为准。

54个Scala硬件源文件保持；VLEN128/ELEN64、单lane、单指令在途、版本化RAM。尚未声明完整V/RVA23/Zvkt，ACT4 ELF生成和执行均为0，真实CPU/Linux接入待验收。当前云端3.300ns为条件估计，实际300MHz仍需当前RTL的Vivado器件结果。

后续重点为独立ELF测试宿主桥接、官方架构测试、访存恢复条款及SoC接入。整理前的M60入口文档保存在[精确快照](archive/docs-m60/source/README.md)，历史报告不改写。
