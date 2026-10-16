# M28：RAM反馈式FP归约

本轮新增 `vfredosum.vs`、`vfredusum.vs`、`vfredmin.vs`、`vfredmax.vs`。支持FP32/FP64、9种合法SEW/LMUL、全部5种frm。无序求和选择规范允许的顺序左折叠，结果确定；宽化FP归约尚未实现。当前仍为单条指令容量、部分RVV。

## 数据与状态

已提交RAM提供vs1的元素0作为seed，然后按索引升序读取vs2组内被执行mask选中的元素。复用原整数归约的64位累加器、seed阶段和单元素写回；有效元素经过现有FP lane逐个反馈，完成后只更新vd元素0，目的tail保留。源组需要LMUL对齐，seed及目的占一个物理寄存器，无LMUL对齐要求，可合法重叠。没有新增状态、寄存器、RAM端口或整组快照。

VL0不更新vd。VL>0而没有选中元素时，将seed原始位复制到vd，包括sNaN、qNaN负载、负零，不产生新的异常。正常计算按frm逐步舍入，fflags粘滞累积。完成握手才发布目的版本与fflags，背压保持私有状态，flush撤销后可继续执行普通FP/INT和排列指令。

保留frm、SEW8/16、非零vstart、数据源组不对齐、masked data/seed v0均报非法，VL0仍先检查。非法不改变架构寄存器或CSR。Monitor ABI1.0，ID0x2801、caps0xffff，bit15表示单宽FP归约；该位不表示完整V支持。

## 验证

独立SoftFloat数值参考先通过52组已知答案锚点，再对不可变完整源组做元素过滤与左折叠。本轮完整RTL 5771条命令，其中合法归约1770、非法308、flush 96次。覆盖NaN/无穷/±0/子正规、溢出、舍入和顺序敏感的消去；全masked、VL0、重叠、组边界、完成背压和CSR保持，逐条检查全部32个寄存器与版本。映射smoke与当前RTL逐项核对结果及周期；无FP/16位切分版负向检查四类FP归约仍拒绝。

公开SpinorVpu接口执行四类归约、取消恢复及tail保留；混合序列扩展至30条向量指令，交替整数/FP归约、FP加法、compress、gather、mask和整数运算。旧220组性能逐组对比M27，结果与周期保持。新增归约为串行反馈，性能行记录命令至完成的总周期，不代表每拍接收一个向量元素。e32/m8、VL32、32个有效元素、frm=RNE且无完成背压时，求和1229拍，min/max 301拍；含命令和准备开销。

## 云端参考与资源

两个顶层固定100ps/段参考预算均为3.118ns，余量0.215ns，满足3.333ns云端门槛。50/200ps档均为2.518/4.318ns。权重继续锚定冻结M25，未调低假设。无布局布线或ZU15EG-2校准，DSP相关端点、hold、时钟树、RAM写和IO未纳入；物理300/500MHz仍未验证。

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| SpinorVpu | 18183 | 12300 | 9 | 32 | 6 |
| LishiVpuMemory | 15981 | 10926 | 9 | 32 | 6 |

RAM另占器件LUT，不是BRAM数量。FP lane等9个单元RTL与M27的SHA相同；资源小幅变化包含全局映射变化。

完整证据见[报告](../reports/m28/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m28.py`、`python3 scripts/package.py --milestone m28`。下一步补齐宽窄整数、宽化FP归约与更多访存模式；Orbital/Linux真实接入仍待完成。
