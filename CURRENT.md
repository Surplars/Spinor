# Spinor 当前进度：M58

330种算术编码×22种SEW/LMUL配置×4种vta/vma策略，标准/Deep数值矩阵通过。
每预设另有404个分段字段故障/FOF后算术、CSR读VL及重试场景。
本轮共235,088条独立Spike参考命令，逐条比较完整RF/CSR；访存还比较8KiB RAM。

- [M58语义、条款与边界](docs/m58-semantics.md)
- [M58验证报告](reports/m58/evaluation.md)、[机器可读条款](reports/m58/semantic-clauses.json)
- [编码/策略覆盖](reports/m58/policy-coverage.csv)、[恢复场景](reports/m58/recovery-cases.csv)
- [ISA目录及验收清单](docs/m57-isa-audit.md)
- [CPU接入契约](docs/cpu-spinor-contract.md)

本轮建立5项条款有界证据。固定算术寄存器布局、vstart=0；通用重叠、
非零算术vstart、更广架构套件、Zvkt全面验收和实际SoC接入仍待推进。
375基础V+16Zvbb目录没有发现漏项，310种访存形式有样本；仍不声明完整V/RVA23/Zvkt。

54个Scala源文件不变，Mill/Chisel7.16.0、VLEN128/ELEN64、RAM保持。
沿用宿主公共/计算顶层3.300ns条件预算，无当前RTL的实际300MHz器件签核。
整数/宿主预设沿用历史证据；Orbital/Valence未修改或联编。
入口 `python3 scripts/verify_m58.py`，`--check-only`核对当前精确证据。
