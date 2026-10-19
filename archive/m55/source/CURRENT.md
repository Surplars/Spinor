# Spinor 当前进度：M55

M55 增加 Zvbb 的 10 类操作/16 种编码，monitor 实现号 0x5501；继续使用 Mill、
Chisel 7.16.0、VLEN128/ELEN64 和 RAM 寄存器文件。Orbital/Valence 未修改。

- [当前功能、接口与 ISA 边界](docs/m55-zvbb.md)
- [M55 验证、资源、条件时序与复现](reports/m55/evaluation.md)
- [M53 的真实本地 Vivado 时序](reports/local-m53-resume/evaluation.md)：适用旧 RTL
- [实际 DSP 参考数据与配置不兼容说明](reports/dsp-m53/evaluation.md)

默认公共顶层云端条件预算 3.292ns，计算/访存顶层 3.232ns，均过 300MHz 条件
门槛；仍无 M55 的器件布局布线签核。不能声明完整 V/RVA23 或 Zvkt。
当前入口 `python3 scripts/verify_m55.py`；历史源码/证据分版本保留。
