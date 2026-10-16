# M26：舍入/IEEE封装分级与保留编码检查

继续完善Spinor本体；没有新增指令种类，仍为部分RVV、VLEN128/ELEN64、单条指令容量。公开顶层SpinorVpu，目标ZU15EG-2。未接实际Orbital或Linux，不声明完整V/RVA23。

## 实现

StagedRound在指数修正、overflow/underflow判断和特殊值封装之间增加一级。FloatingPointLane的FP32/64转IEEE先寄存指数、非规格化移位距离及有效数，再执行移位、NaN规范化和回应封装。FMA族及DIV/SQRT相对M25每有效元素增加2拍，整数转FP增加1拍；FP比较/分类/符号、FP转整数与整数执行周期不变。完成背压保持tag/flags/data；flush清除owner，不发布旧响应。

索引递增与mask字节推进改用已有ParallelIncrement，保留8位推进到128的语义，没有增加元素周期。增量器证明扩展5位宽；没有新增RF读端口、快照或整组FF数组。RF仍是双版本64×128、同步读取和字节写使能的LUTRAM。

统一普通INT/FP/乘除/归约/滑移的执行mask与v0数据源双EEW别名检查，归约seed也算SEW源。LSU拒绝masked store v0；masked load v0同样非法。非法检查在VL0、全mask关闭和vstart越过VL之前执行，保持寄存器、版本、CSR及vstart，不产生访存请求。EEW1掩码源可与执行mask同用v0，单目selector0和标量寄存器号0不当作v0数据读；unmasked v0仍合法。独立用例表与Python算术/滑移/归约golden同步修正，没有用旧正向测试替代合法性依据。

Monitor ABI1.0，ID0x2601/caps0x3fff；接口、RAM容量与ISA能力位不变。TileLink仍预留，物理normal-RAM访存尚无VM/PMP/缓存一致性。

## 验证

专项保留编码RTL 558个反例加10类合法零字段，当前映射网表同结果/周期；无FP及16位切分版也通过。滑移5576条中894条非法（新增134个masked源v0反例）；归约3418条中386条非法（176个seed v0反例），不再把这些保留编码计作合法运算。

四格式舍入相对固定HardFloat有界10步全raw位证明；新增IEEE解码相对固定HardFloat有界4步、任意recoded位及capture/hold证明；均为局部证明，不是完整FP流水或全ISA证明。并行增量/地址/配置、recode、divider和mask-prefix证明的源码SHA逐一核对。FP lane 6811组SoftFloat位/flags比较、205次撤销/复位；smoke与映射增加舍入末段逐拍取消。转换5021组、492次撤销/复位重新通过。

完整gather3675、索引1674、前缀mask2888、mask/scalar10198、scan2894、INT乘除1673、旧向量789、FP向量2157、streaming251重新通过RTL。19条INT/FP/归约/排列交替序列与gather smoke在当前RTL/映射通过；monitor RTL/映射2600周期及tiny计数回绕通过。220组性能逐组核对数值，整数周期保持M25，vfadd增加恰好每有效元素2拍，未把增加流水级称作吞吐提升。

LSU完整279组（78种EEW/EMUL、77次边界停止）及119组smoke RTL/映射通过；新增24组四种EEW的masked v0 load/store非法边界和1组unmasked v0 store正例。公开SpinorVpu在monitor并发访问下279组RTL及119组RTL/映射通过；逐请求数据与周期按参考检查。旧M25完整映射证据不冒充当前网表。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M25 SpinorVpu | 18109 | 11992 | 9 | 32 | 6 |
| M26 SpinorVpu | 18314 | 12300 | 9 | 32 | 6 |
| M25 LishiVpuMemory | 15755 | 10618 | 9 | 32 | 6 |
| M26 LishiVpuMemory | 15922 | 10926 | 9 | 32 | 6 |

Yosys xcup未布局映射；RAM还会消耗器件LUT，表中数量不是BRAM。

## 云端验收

| 每段连线假设ps | M25公开ns | M26公开ns | M26计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.791 | 2.700 | 2.609 |
| 100 | 3.391 | 3.300 | 3.209 |
| 200 | 4.591 | 4.500 | 4.409 |

固定100ps/段假设下，公开顶层3.300ns、算术余量0.033ns，计算/访存3.209ns、余量0.124ns，均在300MHz的3.333ns条件预算内。check_timing_gate.py对两个顶层强制检查，权重和RapidWright家族来源与冻结M25完全一致，不改连线假设换取通过。

这仅是条件参考门槛通过。没有布局布线、-2器件校准、DSP相关端点、时钟树/hold、RAM写或I/O检查，没有器件STA/SDF或WNS；物理300/500MHz通过仍为null。200ps档结果见表，不能据100ps档声称实际300MHz已过，旧M5物理结果不能继承。

## 复现与后续

make bootstrap；python3 scripts/verify_m26.py；python3 scripts/package.py --milestone m26。receipt绑定源码、当前RTL/网表、测试台、局部证明、冻结基线、固定时序门槛与报告。后续继续compress、宽窄整数、FP归约及更多访存模式。未修改Valence，未调用Verilator。
