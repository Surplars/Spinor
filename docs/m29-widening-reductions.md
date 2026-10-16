# M29：宽化整数归约

新增RVV 1.0的 `vwredsumu.vs` 与 `vwredsum.vs`，源SEW8/16/32分别归约到16/32/64位标量。支持18种合法源SEW/LMUL，包含m8与合法分数LMUL；64→128超出ELEN64，尚未支持。仍为单指令容量、部分RVV，不能声明完整V/RVA23。

## 语义与边界

unsigned对窄源零扩展，signed按源SEW符号扩展，再与完整2×SEW seed相加，按2×SEW取模回绕。VL0不写目的，VL>0且全masked时复制完整宽seed。目的仅更新低2×SEW位，其余tail选择保留。

数据源按源LMUL对齐；加宽的seed和目的均为EMUL1单寄存器，可不按源LMUL对齐，所以m8合法。归约目的可重叠源或mask。但seed/data两个源以不同EEW读取，不能共享物理寄存器，包括分数LMUL；该约束与目的重叠许可分开检查。masked数据源或seed不能使用v0，非零vstart、SEW64、源组不对齐及保留编码在VL0也检查。

## RAM与流水

保留源地址和提取宽度为SEW，seed、IntegerLane请求与写回宽度为2×SEW。复用64位累加器、seed阶段、整数流水和候选RAM；现有owner指令稳定到完成/flush，可直接决定扩展类型和算术宽度，不增加状态、寄存器、RAM端口、整组快照或DSP。目的版本在完成握手才发布，取消丢弃候选结果。后续FP/INT和排列指令恢复各自原宽度。

Monitor ABI1.0，ID0x2901/caps0x1ffff，bit16表示宽化整数归约，保留bit15单宽FP归约。

## 验证

独立Python参考对不可变完整源组过滤有效元素，用任意精度数学求和，再对2×SEW取模。完整RTL 1025条命令，合法260、非法325、取消60；覆盖18种类型、seed高位、signed负数、溢出、空/稀疏mask、VL0、末端v24..v31、目的别名、每个源组位置的混合EEW seed别名、保留编码/CSR/背压，并逐条检查32寄存器和版本。163条smoke通过当前RTL/映射；无FP与16位切分版各161条通过。

35条混合序列通过RTL/映射，包含宽化归约→普通INT→FP归约→FP加法，检查宽度不泄漏。公开SpinorVpu并发monitor流量下检查32→64两类归约、取消恢复、tail保留、非法源别名及返回普通INT。旧FP归约5771条RTL、588条映射和原整数/排列/访存回归继续核对；原220组性能结果与周期保持M28。新归约仍是串行反馈，不是向量指令并行。e8/m8、VL128、无完成背压时，128个有效元素1421拍，64个有效元素781拍，均包含命令与准备开销。

## 云端参考与资源

| 顶层 | 50ps/段 | 100ps/段 | 200ps/段 |
|---|---:|---:|---:|
| SpinorVpu | 2.700ns | 3.300ns | 4.577ns |
| LishiVpuMemory | 2.591ns | 3.141ns | 4.318ns |

固定100ps/段参考门槛均≤3.333ns，公开顶层仅余0.033ns。权重仍锚定冻结M25，没有降低假设。无布局布线或ZU15EG-2校准，DSP相关端点、hold、时钟树、RAM写、IO或SDF不在该预算中；物理300/500MHz尚未验证。

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| SpinorVpu | 18384 | 12300 | 9 | 32 | 6 |
| LishiVpuMemory | 16020 | 10926 | 9 | 32 | 6 |

RAM另占器件LUT，不是BRAM数量。全局映射差异不能直接视作新功能的独立成本。FP、整数数值单元、RF、物理LSU等9个单元RTL的SHA保持M28。

完整证据见[报告](../reports/m29/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m29.py`、`python3 scripts/package.py --milestone m29`。下一步继续宽窄整数、宽化FP归约及访存模式，再推进Orbital程序闭环。
