# M29：RAM式宽化整数归约

新增vwredsumu.vs、vwredsum.vs，支持8→16、16→32、32→64，18种合法源SEW/LMUL。源m8合法；64→128超出ELEN64，VL0也报非法。仍为VLEN128/ELEN64、单指令容量的部分RVV，不能发布完整V/misa.V/RVA23声明，尚未接实际Orbital/Linux。

## 实现与边界

源RAM地址与元素提取保持SEW/LMUL，seed、算术请求和单元素写回使用2×SEW。unsigned将窄元素零扩展，signed按窄元素符号位扩展，复用现有IntegerLane和64位reductionAccumulator，按2×SEW取模回绕。复用原seed读取、dispatch反馈、候选RAM、tail保留及完成版本提交，无新增状态、寄存器、RAM端口、整组快照或DSP。源/目标宽度选择用现有稳定owner指令和sew布尔计算，普通整数/FP路径保持原宽度。

加宽的seed和目的各为EMUL1单寄存器，不按数据LMUL对齐，目的允许与源或mask重叠。但seed与数据是不同EEW的两个源，同一物理寄存器不能同时提供二者；检查覆盖源组内每个位置，分数LMUL也按物理寄存器约束。masked data/seed v0、数据组不对齐、非零vstart、源SEW64和错误编码在VL0也拒绝，非法保持架构状态。VL0不写目的；VL>0但无有效元素时按2×SEW复制seed。目的其余tail保留，完成背压与flush不提前发布版本或修改CSR。Monitor ABI1.0，ID0x2901/caps0x1ffff，bit16表示宽化整数归约。

## 验证

独立Python参考从不可变整组数据按源SEW取有效元素，以任意精度整数进行signed/unsigned数学求和，加完整2×SEW seed后仅在最终取模；不复制RTL的宽度选择、状态机或RAM算法。完整RTL 1025条命令，其中合法260、非法325、撤销60；覆盖18种类型、跨寄存器、m8末端v24..v31、seed高位、正/负扩展、溢出、全mask关闭、VL0、所有源组位置的混合EEW seed别名、masked源v0、目的重叠及tail、未对齐标量、保留vstart/编码、完成背压和CSR保持。逐条回读全部32个寄存器并检查版本，提交前和背压期间版本保持不变。

163条smoke在当前RTL和映射网表结果/周期一致；无FP、16位切分版smoke也通过。35条混合向量序列在INT/FP/同宽归约/宽化归约/compress/gather之间交替，当前RTL和映射均通过，检查算术宽度与signed控制不泄漏。公开SpinorVpu并发monitor流量下，279组RTL及119组RTL/映射访存回归通过，末尾执行两类32→64归约、取消、源别名非法、tail保留和返回普通整数执行。独立物理LSU279/119组RTL及119组映射通过；monitor2600周期RTL/映射、tiny回绕和用户态fixture通过。

旧FP归约5771条完整RTL及588条RTL/映射重新通过，包含FP32/64和flags。旧compress1229、gather3675、slide5576、index1674、prefix2888、mask/scalar10198、scan2894、单宽整数归约3418、INT乘除1673、旧整数789、FP向量2157、streaming251重新通过RTL；compress/gather smoke及558个保留源别名反例在当前映射通过。原220组性能结果和周期保持M28。FP、转换、整数数值单元、RF、物理LSU等9个单元RTL与M28的SHA一致，复用已绑定的6811组FP、5021组转换及局部数值证明；这不冒充本轮完整顶层测试。

新宽化归约仍为串行反馈，性能行见receipt，包含准备与命令开销，不是多指令并行。e8/m8、VL128、无完成背压时128/64个有效元素分别1421/781拍。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M28 SpinorVpu | 18183 | 12300 | 9 | 32 | 6 |
| M29 SpinorVpu | 18384 | 12300 | 9 | 32 | 6 |
| M28 LishiVpuMemory | 15981 | 10926 | 9 | 32 | 6 |
| M29 LishiVpuMemory | 16020 | 10926 | 9 | 32 | 6 |

Yosys xcup未布局映射；RAM另占器件LUT，不是BRAM数量。全局映射变化不等于新增指令本身的增量成本。

## 固定云端门槛

| 每段连线假设ps | M28公开ns | M29公开ns | M29计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.518 | 2.700 | 2.591 |
| 100 | 3.118 | 3.300 | 3.141 |
| 200 | 4.318 | 4.577 | 4.318 |

原100ps/段及家族权重下公开3.300ns、计算/访存3.141ns，余量0.033/0.192ns，均≤300MHz周期3.333ns。公开顶层条件余量很小。门槛仍锚定冻结M25权重/参考，M28冻结图按SHA恢复用于比较，未改变假设。

未布局布线、未按ZU15EG-2校准；DSP相关端点排除，无时钟树/hold、RAM写、IO或SDF验证。物理300/500MHz通过字段仍为null，不继承旧M5结果。200ps档不满足300MHz周期。

## 复现

make bootstrap；python3 scripts/verify_m29.py；python3 scripts/package.py --milestone m29。receipt绑定源码、当前RTL/网表、独立参考/测试台、局部证明和冻结基线。未修改Valence或使用Verilator。后续继续宽窄整数、宽化FP归约与更多访存模式，再推进实际Orbital程序闭环。
