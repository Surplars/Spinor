# Spinor 当前进度：M60

标准/Deep新增726,000条分类独立参考命令，覆盖全部330种算术编码。
每预设72,600个目标含50,914合法、21,686拒绝；40,072个非零起点合法。
307种编码在非零起点有可见RF/标量结果，23种按限制拒绝非零起点。
逐条比较完整RF/CSR/Completion；不是所有布局/数据的穷举。

- [M60重启分类与边界](docs/m60-classified-restart.md)
- [M60报告](reports/m60/evaluation.md)、[逐编码分类/覆盖](reports/m60/restart-coverage.csv)
- [规范引文与负控制](reports/m60/semantic-clauses.json)、[ACT4接入条件](docs/act4-intake.md)
- [M59类型重叠](docs/m59-overlap-restart.md)
- [M58尾部/掩码与分段恢复](docs/m58-semantics.md)
- [ISA目录及验收清单](docs/m57-isa-audit.md)、[CPU接入契约](docs/cpu-spinor-contract.md)

固定Spike始终从零执行，普通执行掩码变换与carry/merge、whole/scalar例外分开处理；
没有修改参考语义或称为直接非零Spike差分。5,720场景与M59数学/SoftFloat模型再次校准。
24次运行错误注入、5次条款负控制通过；whole-VL0、scalar read/insert例外单独验证。
官方ACT4仓库已固定版本并清点接入条件；ACT4 ELF生成0个、执行0个。

375基础V+16Zvbb目录与310种访存形式的历史样本保持；完整V/RVA23/Zvkt尚未声明。
其余语义条款、架构套件、Zvkt验收和实际SoC接入继续推进。
54个Scala文件精确不变，没有新增指令/资源；Mill/Chisel7.16.0、VLEN128/ELEN64、RAM保持。
沿用3.300ns云端条件预算，当前RTL实际300MHz仍需Vivado器件结果。
整数/宿主预设沿用历史证据，Orbital/Valence未修改或联编。
入口 `python3 scripts/verify_m60.py`，`--check-only`核对当前精确证据。
