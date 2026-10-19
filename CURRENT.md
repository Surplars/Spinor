# Spinor 当前进度：M54

M54 增加 FP16↔FP32 的最小向量转换，monitor 实现号 0x5401；继续使用 Mill、
Chisel 7.16.0、VLEN128/ELEN64 和 RAM 寄存器文件。Orbital/Valence 未修改。

- [当前 ISA 支持与限制](docs/m54-half-conversions.md)
- [M54 验证、资源、条件时序与复现](reports/m54/evaluation.md)
- [M53 的真实本地 Vivado 时序](reports/local-m53-resume/evaluation.md)：适用旧 RTL
- [实际 DSP 参考数据与配置不兼容说明](reports/dsp-m53/evaluation.md)

云端当前条件预算通过；M54 尚无器件布局布线签核。仍不能声明完整 V/RVA23 或
完整半精度算术。当前入口为 `python3 scripts/verify_m54.py`，历史报告保持原版本。
