# Spinor 当前进度：M56

M56 增加宿主管理 FCSR 模式：CPU 保留唯一架构状态，VPU 锁存 frm 并返回本条
指令的 flags；宿主版 monitor ID0x5602。原四种独立预设的 SV 与 M55 逐字节一致。
继续使用 Mill、Chisel7.16.0、VLEN128/ELEN64 和 RAM；Orbital/Valence 未修改。

- [M56 接口、上下文与延迟审计](docs/m56-host-fcsr.md)
- [M56 验证与时序](reports/m56/evaluation.md)
- [M55 的 Zvbb 操作集合](docs/m55-zvbb.md)
- [M53 实际 Vivado 时序](reports/local-m53-resume/evaluation.md)：适用旧 RTL

默认宿主公共/计算顶层的云端条件预算均3.300ns，通过300MHz条件门槛；仍无 M56
器件布局布线签核。两宿主预设各完成43,560个按规范分组的延迟抽样，不能据此声明
完整 Zvkt/V/RVA23。当前入口 `python3 scripts/verify_m56.py`。
