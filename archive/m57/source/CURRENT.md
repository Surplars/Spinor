# Spinor 当前进度：M57

ISA目录已独立核对：375条基础V+16条Zvbb，名称及match/mask逐项一致。
310种访存形式全部有合法成功样本，补齐此前12种跨步分段形式的缺样本。
没有发现目录漏指令；完整ISA语义与架构测试验收仍未关闭，不能宣布完整V/RVA23/Zvkt。

- [ISA实现与未关闭验收项](docs/m57-isa-audit.md)
- [逐编码目录](reports/m57/isa-catalog.csv)、[访存NF展开](reports/m57/memory-forms.csv)
- [M57验证报告](reports/m57/evaluation.md)
- [M56宿主FCSR接口](docs/m56-host-fcsr.md)、[CPU接入契约](docs/cpu-spinor-contract.md)
- [M53实际Vivado时序](reports/local-m53-resume/evaluation.md)：仅适用旧RTL

本轮54个Scala源文件不变。标准/Deep实际重新执行175,556条Spike差分命令和
2,024条独立策略命令；原始编码扫描使用VL0，仅验证解码/状态边界。
整数/宿主预设沿用已有证据；Orbital/Valence未修改或联编。

Mill/Chisel7.16.0、VLEN128/ELEN64、RAM配置保持。沿用M56宿主公共/计算顶层
3.300ns条件预算，没有新综合或实际300MHz器件签核。
入口 `python3 scripts/verify_m57.py`；旧文档与旧receipt按版本保留。
