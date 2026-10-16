# M30：精确FP32→FP64宽化求和归约

新增vfwredosum.vs、vfwredusum.vs，源FP32、seed/累加器/结果FP64；支持e32/m1、m2、m4、m8、mf2五种类型与5种合法frm。unordered选择规范允许的确定顺序折叠。FP16与FP64→128尚未支持；当前仍为VLEN128/ELEN64、单指令容量的部分RVV，未接真实Orbital或Linux，不能发布完整V/RVA23或misa.V声明。

## RAM与数值流水

复用M29源SEW/标量2×SEW的RAM通路和64位累加器。新增内部widenAdd操作：A来自FP32精确raw recode，B为FP64，结果直接按FP64舍入。原共享FP lane已计算三路FP32规格化与FP64 recode，只改变A的格式选择和add/convert/misc路由，复用现有FMA/round流水。不增加状态、寄存器、RAM端口、整组快照或DSP；普通运算时延不变。没有对普通FP宽化转换指令作支持声明。

FP32有限值精确提升，NaN保留signaling属性至实际求和，由浮点加法产生NV；不先把seed截成FP32，也不以FP32舍入中间结果。seed与目的各EMUL1，m8源合法；目的可与任一源或mask重叠，但seed/data是不同EEW的两个源，不能共享物理寄存器。VL0不写目的；VL>0无有效元素时原样复制FP64 seed，包括sNaN负载、qNaN负载、-0，不产生新的flags。目的低64位写回，其余tail保留，fflags与版本在完成握手才提交，flush抛弃私有状态。保留frm、源SEW不支持、非零vstart、源组对齐和masked源v0检查在VL0也执行。Monitor ABI1.0，ID0x3001/caps0x3ffff，bit17表示宽化FP归约。

## 时序优化

AVL/gather边界判断将低8位比较改为四个2位less/equal及平衡布尔组合，保持高56位非零时直接判false，消除该比较的carry链，不增加流水或周期。独立SAT miter对所有64位输入和8位limit与原数学小于关系证明等价；同一证明继续检查组几何与增量。FP recode的局部全输入证明按当前源码重新通过。这些是局部组合证明，不是整机/ISA形式合规证明。

## 验证

新增SoftFloat参考路径使用f32_to_f64后f64_add，保留转换与加法flags并规范NaN；7组新已知答案先锚定该路径，原52组参考锚点保留。混合精度lane 1292组、42次flush/reset完整RTL通过；98组RTL/映射通过，检查高32位垃圾忽略、FP64 seed所有位、子正规、NaN/无穷/±0/舍入边界、五种frm、非法FP32输出模式和frm5/6/7、背压/tag和恢复。

完整向量 1664条命令，合法442、非法194、取消22，覆盖5种类型、精确提升/避免FP32中间舍入、顺序敏感消去、seed高位、无有效元素的原位NaN复制、mixed-EEW源别名、目的重叠、v24..v31边界、tail、VL0、frm/vstart/对齐/v0保留检查、提交前版本与fflags保持；逐条读取32个寄存器。266条smoke当前RTL/映射结果、flags及周期一致；无FP/16位切分版负向测试保持非法。39条混合向量序列当前RTL/映射通过，涵盖新宽化FP→普通FP/INT及compress，检查模式/宽度不泄漏。

原6811组FP lane、5021组转换本轮重新通过RTL，385组FP lane重新通过映射。旧单宽FP归约5771及588映射、宽化INT归约1025及163映射、compress1229及189映射、gather3675及404映射、558个保留源别名反例当前映射，以及slide5576/index1674/prefix2888/mask-scalar10198/scan2894/单宽INT归约3418/INT乘除1673/旧INT789/FP向量2157/stream251完整RTL回归通过。原220组性能结果和周期保持M29。除FloatingPointLane外的8个数值/RF/LSU/host单元RTL按SHA保持M29，未变的局部证明和整数除法单元证据保留绑定。

公开SpinorVpu并发monitor流量下279组RTL与119组RTL/映射访存通过，末尾执行两类FP32→64归约、取消恢复、seed别名非法、tail保留和返回整数运算；独立LSU279/119组RTL及119组映射通过。Monitor2600周期RTL/映射、tiny回绕和软件文件fixture通过，尚非真实Linux内核/上板结果。归约仍为串行反馈，性能行包含准备开销，不是多指令并行。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M29 SpinorVpu | 18384 | 12300 | 9 | 32 | 6 |
| M30 SpinorVpu | 18344 | 12300 | 9 | 32 | 6 |
| M29 LishiVpuMemory | 16020 | 10926 | 9 | 32 | 6 |
| M30 LishiVpuMemory | 16146 | 10926 | 9 | 32 | 6 |

Yosys xcup未布局映射，RAM另占器件LUT，不是BRAM块数；全局映射差异不等于新增指令的独立成本。

## 固定云端门槛

| 每段连线假设ps | M29公开ns | M30公开ns | M30计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.700 | 2.700 | 2.627 |
| 100 | 3.300 | 3.300 | 3.277 |
| 200 | 4.577 | 4.577 | 4.577 |

固定100ps/段下公开3.300ns、计算/访存3.277ns，余量0.033/0.056ns，均≤3.333ns。门槛仍锚定冻结M25家族权重与参考，M29冻结图按SHA恢复用于比较，假设未改动。

仅为条件参考。没有布局布线或ZU15EG-2校准，DSP相关端点排除，无hold/时钟树、RAM写、IO或SDF检查；物理300/500MHz仍为null，不继承M5。200ps档不满足300MHz周期，当前正余量很小。

## 复现

make bootstrap；python3 scripts/verify_m30.py；python3 scripts/package.py --milestone m30。receipt绑定当前源码、RTL/网表、SoftFloat参考与测试台、证明和冻结基线。未修改Valence或使用Verilator。后续继续宽窄整数、FP转换与更多访存模式，再推进Orbital程序闭环。
