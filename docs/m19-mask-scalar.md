# M19：掩码逻辑与整数标量搬运

新增 `vmandn.mm / vmand.mm / vmor.mm / vmxor.mm / vmorn.mm / vmnand.mm / vmnor.mm / vmxnor.mm` 和 `vmv.x.s / vmv.s.x`。语义与编码依据 RVV 1.0 和官方 riscv-opcodes，摘录见 [参考文本](references/mask-scalar-v1.0.txt)。

掩码逻辑每个元素是一位，所有源与目的都是单个寄存器，不受 LMUL 组对齐限制，可以任意重叠，包括 v0。`vm=0` 的编码非法。只修改 `[vstart, vl)`，成功完成后清零 vstart，尾部选择保留旧值，属于 tail-agnostic 策略允许的行为。`vl=0` 或 `vstart>=vl` 时不写目的寄存器。

实现逐位读取两个已提交源，经现有整数流水线运算，再读改写候选目的字节。最后仅在 completion 握手时翻转单个目的版本。不新增向量 FF 快照、DSP 或 RAM 副本。这是串行功能实现，尚未做字节并行的吞吐优化；无 completion 反压、vstart=0、VL=128 时，当前 FP 顶层的 mask 逻辑为 1929 个仿真命令周期。

整数标量搬运忽略 LMUL。`vmv.x.s` 读取 vs2 的第零元素，SEW 小于 RV64 XLEN 时符号扩展；`vl=0` 和 `vstart>=vl` 仍读取。rd=x0 时不请求宿主写 GPR。`vmv.s.x` 从宿主 scalar 输入写 vd 第零元素，截断到 SEW，保留其他字节；`vstart>=vl` 时不写。两者的 `vm=0` 以及不满足固定源字段的编码均非法。成功完成清 vstart；非法指令保留原状态。GPR 的读值、x0 和实际写回仍由 CPU 接口承担。

标量读取复用 RF 读口和现有 scalar completion；标量写入复用候选复制与归约末尾的单元素写入路径。无 completion 反压时，当前 FP 顶层标量读/写分别为 6/8 个仿真命令周期，包含首尾开销，不代表 SoC 指令延迟。

独立 Python 参考使用逐位布尔真值及有符号整数，不导入硬件运算模型。检查全部 32 个寄存器、版本位、vstart 和非零 FP/定点 CSR，并验证完成背压及 flush 与 completion-ready 同时到来。完整 RTL、映射子集、无 FP 和 16 位切分版本的实际覆盖见 [M19 报告](../reports/m19/evaluation.md)。公开 SpinorVpu 还运行真实指令序列：归约→标量读写→构造 v0→masked vadd，与访存和 monitor 流量共用顶层。

Monitor ABI 保持 1.0，实现 ID 更新为 `0x1901`，caps=`0x1ff`：bit7 表示上述八种 mask 逻辑，bit8 表示上述两种整数标量搬运。FP 标量搬运、完整 mask、排列及完整 RVV 仍未实现。

```bash
make bootstrap
python3 scripts/verify_m19.py
python3 scripts/package.py --milestone m19
```

云端工具仍为 Yosys/Icarus 和 RapidWright 家族参考。功能仿真使用一个时钟并不意味着器件能满足该周期；300 MHz 仍需要相应时序模型或器件实现报告。
