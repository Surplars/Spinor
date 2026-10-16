# M28：RAM反馈式单宽浮点归约

新增vfredosum.vs、vfredusum.vs、vfredmin.vs、vfredmax.vs，FP32/FP64的9种合法SEW/LMUL、5种合法frm。无序求和采用规范允许的确定顺序折叠。宽化FP归约尚未实现；仍为VLEN128/ELEN64、单条指令容量的部分RVV，未接真实Orbital或Linux，不能发布misa.V或完整V/RVA23声明。

## 实现与边界

复用已有reductionSeedRead/Capture、64位累加器、dispatch、FP lane和reductionWrite，只扩展解码与归约选择；没有增加状态、寄存器、整组快照或RF端口。RF保持双版本64×128同步读、字节写使能LUTRAM。选中的元素逐个执行浮点运算，结果反馈累加器；fflags累积到私有状态，和目的版本一起在完成握手时发布。flush撤销私有结果，下一条指令重新读取mask和seed。

seed与目的均为单寄存器，可不按LMUL对齐，可与数据组合法重叠；目的仅写元素0，其余tail保留。VL0完全不写目的；VL>0且无选中元素，原位复制seed，保留sNaN/qNaN负载和负零位型，不规范化NaN且不新增异常。有有效元素时逐步按frm舍入并累积异常，min/max使用IEEE minimumNumber/maximumNumber与规定的NaN/±0规则。masked data/seed v0、源组不对齐、SEW8/16、保留frm、非零vstart在VL0也拒绝，非法保持RF及CSR。Monitor ABI1.0，ID0x2801/caps0xffff，bit15表示单宽FP归约；TileLink与原LSU合同保留。

## 验证

独立SoftFloat参考从不可变源组提取有效元素并进行左折叠，52组已知答案锚点先校验参考库。完整RTL 5771条命令、1770次合法归约、308次非法、96次撤销，覆盖9种类型/全部5种frm、NaN/无穷/±0/子正规/舍入边界/溢出/消去、全mask关闭、VL0、跨寄存器、seed/目的/源别名、未对齐标量、保留编码、完成背压、粘滞fflags；逐条读取32个寄存器并检查版本与CSR。完成之前和背压期间额外检查fflags及版本不提前发布。

smoke 588条命令通过当前RTL与映射网表，逐项结果和周期一致；无FP及16位切分版负向测试确认四类FP归约仍非法。30条混合序列交替INT/MUL/FP、整数归约、mask/索引、compress/gather、FP归约及返回FP/compress，当前RTL/映射均通过。公开SpinorVpu并发monitor下，原物理访存279组RTL与119组RTL/映射及新增四类归约、取消恢复、tail检查通过；物理LSU本身279/119组回归通过。Monitor2600周期RTL/映射、tiny回绕与用户态文件fixture通过。

旧compress1229、gather3675、slide5576、index1674、prefix2888、mask/scalar10198、scan2894、整数归约3418、INT乘除1673、旧整数789、FP向量2157、streaming251重新通过RTL。compress/gather smoke与558个保留源别名反例在当前映射通过。原220组性能结果与周期均保持M27。FP lane、转换、整数算术、RF、物理LSU等9个单元RTL按SHA保持M27；6811组FP、5021组转换及未变的局部数值证明复用已绑定证据，不冒充完整顶层的本轮网表覆盖。新增归约的性能行见receipt，串行反馈每个有效元素均需等待浮点单元，没有宣称多指令并行或高吞吐。e32/m8、VL32、RNE、无完成背压时，求和1229拍，min/max301拍（含准备）。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M27 SpinorVpu | 18292 | 12300 | 9 | 32 | 6 |
| M28 SpinorVpu | 18183 | 12300 | 9 | 32 | 6 |
| M27 LishiVpuMemory | 15888 | 10926 | 9 | 32 | 6 |
| M28 LishiVpuMemory | 15981 | 10926 | 9 | 32 | 6 |

Yosys xcup未布局映射，RAM另占器件LUT，原语数量不是BRAM块数；全局映射变化不等于新功能本身的增量成本。

## 固定云端门槛

| 每段连线假设ps | M27公开ns | M28公开ns | M28计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.500 | 2.518 | 2.518 |
| 100 | 3.050 | 3.118 | 3.118 |
| 200 | 4.227 | 4.318 | 4.318 |

100ps/段固定假设下公开3.118ns、计算/访存3.118ns，余量分别0.215/0.215ns，均≤300MHz周期3.333ns。门槛继续锚定冻结M25权重/家族参考，M27冻结图按SHA恢复用于比较；假设未改动。

仅为条件参考预算。没有布局布线和ZU15EG-2器件校准；DSP相关端点排除，没有时钟树/hold、RAM写、IO或SDF检查。物理300/500MHz通过字段仍为null，不继承旧M5物理结果。200ps档不满足300MHz周期。

## 复现

make bootstrap；python3 scripts/verify_m28.py；python3 scripts/package.py --milestone m28。receipt绑定源码、当前RTL/网表、独立参考、测试台、局部证明与冻结基线。未修改Valence或使用Verilator。下一步继续宽窄整数、宽化FP归约及更多访存模式，再推进Orbital程序闭环。
