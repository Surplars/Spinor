# Spinor 当前进度：M59

标准/Deep新增457,600条独立参考命令，验证26种代表操作的寄存器重叠与非零vstart。
每预设45,760个目标含16,635合法、29,125拒绝；12,780个合法目标起点非零，
5,878个在起点之后有计算范围。逐条比较完整RF/CSR/Completion。
其中5,847个有活动元素，31个全mask关闭。

- [M59重叠/重启语义与边界](docs/m59-overlap-restart.md)
- [M59报告](reports/m59/evaluation.md)、[逐操作覆盖](reports/m59/operation-coverage.csv)
- [规范引文与重叠锚点](reports/m59/semantic-clauses.json)
- [M58尾部/掩码与分段恢复](docs/m58-semantics.md)
- [ISA目录及验收清单](docs/m57-isa-audit.md)、[CPU接入契约](docs/cpu-spinor-contract.md)

非零vstart使用独立Python/SoftFloat参考；固定未修改Spike拒绝这类算术起点，
仅在vstart=0用16,298场景交叉核对模型。维护规范混合源EEW保留策略单独处理。
23个重叠合法/拒绝锚点、24次运行错误注入、2次条款负控制通过。
本轮不是全部算术编码的非零起点穷举，未声称真实CPU中断恢复。

375基础V+16Zvbb目录与310种访存形式的历史样本保持；完整V/RVA23/Zvkt尚未声明。
其余语义条款、架构套件、Zvkt验收和实际SoC接入继续推进。
54个Scala文件精确不变，没有新增指令/资源；Mill/Chisel7.16.0、VLEN128/ELEN64、RAM保持。
沿用3.300ns云端条件预算，当前RTL实际300MHz仍需Vivado器件结果。
整数/宿主预设沿用历史证据，Orbital/Valence未修改或联编。
入口 `python3 scripts/verify_m59.py`，`--check-only`核对当前精确证据。
