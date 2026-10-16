# M27：RAM式vcompress与组边界检查优化

新增vcompress.vm；仍为VLEN128/ELEN64、单条指令容量的部分RVV，不声明完整V/RVA23。公开顶层SpinorVpu，目标ZU15EG-2，尚未接实际Orbital或Linux。

## 实现

显式vs1为EEW1掩码，选中vs2中VL以内的元素，保持顺序压紧到目的组前部，其后按tail策略允许的undisturbed选择保留。支持22种SEW/LMUL，vm=0和非零vstart报非法；目的不得重叠数据组或掩码，掩码与数据源的不同EEW物理寄存器重叠也拒绝。检查在VL0同样执行，非法保持架构状态。

复用已有indexGenerate模式3、scalarResult的8位计数和slideAddress地址阶段，没有新增状态、状态宽度或寄存器。掩码读取一次进入已有128位缓存；未选中元素不读数据，选中元素从已提交RAM读取，独立一拍计算密集目的地址，复用整数move单元串行写候选版本，完成握手才发布。flush抛弃候选写入与计数owner；没有整组快照或新增读端口。显式掩码缓存不会延续到下一条普通指令，原指令会重新取v0。

组边界检查利用1/2/4/8个寄存器的对齐条件，以地址高位匹配替代compress、gather、mask目的和viota的组end-address加法/比较；alignment使用布尔形式，EI16显式拒绝不支持的count=0。Yosys SAT对所有5位基址/寄存器号、四种组尺寸及合法基址对齐证明成员、不同组尺寸重叠、alignment与末端不溢出等价；这是局部组合证明，不是整机或完整ISA证明。

Monitor ABI1.0，ID0x2701/caps0x7fff，bit14表示compress；容量仍为一条指令。RF保持双版本64×128、字节写使能和同步读LUTRAM；FP数值单元和物理LSU RTL按SHA确认与M26相同。

## 验证

独立Python参考从不可变完整源组取VL前缀，用显式掩码过滤列表，不复制RTL的计数、模式编码或RAM地址算法。完整RTL 1229条命令，非法363、撤销37，覆盖22种类型、空/满/稀疏/随机掩码、每个源索引单独选择、跨寄存器压紧、VL/VLMAX边界、tail保留、掩码高于VL位忽略、v0作为三种合法角色、未按LMUL对齐的掩码、非法重叠/对齐/vm/vstart、VL0检查、完成背压及CSR保持；逐条读取32个寄存器并检查版本。smoke 189条在当前RTL与映射网表结果和周期一致，无FP及16位切分版smoke通过。

旧gather3675、滑移5576、索引1674、前缀mask2888、mask/scalar10198、scan2894、归约3418、INT乘除1673、旧整数789、FP向量2157、streaming251重新通过RTL。558个保留源别名反例及合法零字段专项RTL/映射通过。24条混合序列交替compress、FP、viota、gather及原INT/MUL/归约/滑移，通过当前RTL/映射，检查共享模式/计数/地址/掩码缓存无泄漏。原220组性能的结果与周期均保持M26。e8/m8、VL128、无完成背压时，选中0/1/64/128个元素分别151/162/855/1559拍；该类型测试精确核对23+VL+11×选中数，包含准备开销，不是每拍压紧一个元素。

物理访存279组RTL及119组RTL/映射通过。公开SpinorVpu并发monitor流量下279组RTL及119组RTL/映射通过，末尾执行compress取消、稀疏压紧、四类非法编码，随后回到普通整数流水。Monitor2600周期RTL/映射、tiny回绕及用户态文件fixture通过。M26数值单元RTL与相应测试台/网表SHA均保持，复用6811组FP、5021组转换及局部数值证明的绑定证据；它们没有冒充当前完整顶层的网表测试。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M26 SpinorVpu | 18314 | 12300 | 9 | 32 | 6 |
| M27 SpinorVpu | 18292 | 12300 | 9 | 32 | 6 |
| M26 LishiVpuMemory | 15922 | 10926 | 9 | 32 | 6 |
| M27 LishiVpuMemory | 15888 | 10926 | 9 | 32 | 6 |

Yosys xcup未布局映射，RAM另消耗器件LUT，原语数量不是BRAM块数。

## 固定云端门槛

| 每段连线假设ps | M26公开ns | M27公开ns | M27计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.700 | 2.500 | 2.700 |
| 100 | 3.300 | 3.050 | 3.300 |
| 200 | 4.500 | 4.227 | 4.577 |

100ps/段固定假设下公开3.050ns、余量0.283ns，计算/访存3.300ns、余量0.033ns，均≤300MHz周期3.333ns。门槛仍锚定冻结M25权重/家族参考，M26冻结图另按SHA恢复用于上表比较，没有通过更改参数取巧。

仅为条件参考预算。没有布局布线或ZU15EG-2器件校准，DSP相关端点排除，无时钟树/hold、RAM写、IO或SDF检查；物理300/500MHz通过仍为null，不能继承旧M5物理结果。200ps档不满足300MHz周期。

## 复现

make bootstrap；python3 scripts/verify_m27.py；python3 scripts/package.py --milestone m27。receipt绑定源码、当前RTL/网表、独立参考测试台、局部证明、冻结基线和报告。未修改Valence或调用Verilator。后续继续宽窄整数、FP归约及更多访存模式与SoC集成。
