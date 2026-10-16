# M32：整数窄化移位

实现 `vnsrl.wv/wx/wi` 和 `vnsra.wv/wx/wi`，以及由 `vnsrl.wx` 配合 x0 表达的 `vncvt.x.x.w` 伪指令。支持源 16/32/64 位到目的 8/16/32 位，合计 15 种合法 SEW/LMUL 组合。源超过 ELEN64 或源 EMUL 超过 8 的编码保留非法；目的 m8 因源 EMUL=16 不支持。本阶段仍是部分 RVV、单指令容量。

源 vs2 的 EEW/EMUL 为目的的两倍，wv 的 vs1 移位量向量仍使用目的 SEW/LMUL。只使用移位量低 `log2(2*SEW)` 位；wi 是无符号 5 位立即数。整数 lane 按宽源执行原有分级移位，写回按目的位宽截取，保留未写字节。没有增加 DSP、状态、流水级、RAM 端口或整组快照，复用 M31 的源位宽寄存器与原 64 位暂存。

宽源按自身 EMUL 对齐；目的可覆盖其最低部分，要求 vd=vs2。同一指令的宽数据源与窄移位向量源不得按不同 EEW 共享物理寄存器；目的与移位向量的同宽别名可用。mask/tail 保留、合法 vstart、VL0/no-op 与 flush 均有参考模型覆盖；fflags/vxrm/vxsat 保持不变，完成握手后才提交版本。monitor ABI 仍为 1.0，ID0x3201，caps0xfffff 的 bit19 表示窄化整数移位。

完整 RTL 参考测试 4,945 条命令，包含 1,566 条合法窄化指令（含空操作）、1,753 次非法拒绝及 198 个取消场景；15 种合法类型逐条检查 32 个寄存器、配置和版本。smoke 为 489 条，另有无 FP / 16 位切分版各 487 条。52 条混合序列覆盖窄化、扩展、普通 INT/FP、FMA 和 compress；FP FMA 与窄化复用相同 funct6，按 funct3 区分的回归也包含在内。最终回归、资源和时序见 [M32 报告](../reports/m32/evaluation.md)。

## 时序与本地基线

云端使用固定 M25 权重和 100ps/段假设的条件门槛，公开顶层预算 3.300ns、计算/访存 3.050ns，均不超过 3.333ns。该模型不等于器件 STA；没有本轮 Vivado 布局布线、速度档校准或 DSP/hold/真实时钟与接口时序验证。

M31 的实际本地 OOC 结果冻结保存于 archive/m31/local-report：3.333ns 下 setup+0.392ns、hold+0.009ns、布线错误0，实际使用7个DSP和2个RAMB36。HD.CLK_SRC 和外部 IO delay 未指定，尚非完整 SoC 时序签核。M32 的 RTL 已改变，不能继承 M31 本地通过结论。此轮先云端推进，不要求立即重复本地运行；后续接入实际时钟/接口后再验证。

## 复现

```sh
make bootstrap
python3 scripts/verify_m32.py
python3 scripts/package.py --milestone m32
```

M32 项目包包含源码、生成 RTL、当前测试/网表和冻结基线；本轮不生成新的 Windows 执行包。原 M31 Windows 包继续对应 M31，不能作为 M32 的本地验证。后续继续宽化算术、定点、FP 宽窄转换与更多访存模式，同时推进 Orbital 接入协议。
