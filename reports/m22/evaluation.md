# M22：前缀掩码指令

新增vmsbf.m、vmsif.m、vmsof.m，分别生成首个有效置位之前、包含首位、仅首位的掩码。仍为VLEN128/ELEN64、单条指令在途的部分RVV，未接入实际Orbital或Linux计算驱动。

## 语义与实现

支持v0.t、全部22种合法SEW/LMUL，源和目的各为单个mask寄存器，忽略组对齐。非零vstart、vd=vs2，以及masked时vd=v0非法；限制在vl=0时同样检查。合法完成清vstart，非法或撤销不改变架构状态。尾部和inactive位采用保留原值的合法策略。

复用M21字节通路：dispatch、源读/取、字节前缀、候选目的读/写，每次8个mask元素、6周期。先按VL和v0过滤源，再做小规模前缀OR，以1个seen位跨字节携带“此前存在有效置位”。结果和有效字节仍复用原寄存器，不新增整组快照或RF副本。完成握手才提交版本；flush取消候选写。VL=128三条指令均为105周期，包含命令/完成握手；命中位置不改变周期，因为后续有效目的位仍需写零。

## 验证

独立Python模型先求整条向量的首个有效置位索引，再按索引写结果，不复用字节前缀算法。完整RTL2890条命令：1505次合法前缀、431次非法、75次撤销，核对全部32个向量寄存器、版本表、CSR、完成背压与提交。覆盖22种类型、128个one-hot位置、跨字节、VL外置位、v0源/目的、无置位、全masked、零VL以及所有重叠限制。保留原FP/定点CSR并验证不泄漏。

277条命令的FP版smoke在RTL与映射网表中覆盖、功能、周期一致；无FP/16位切分版另通过smoke。字节helper的2048种source/seen/selector组合通过SAT，与独立的最低置位隔离及减法公式等价。该证明只覆盖组合helper；实际FSM、RAM、flush和提交由仿真验证。

原mask/scalar10198条、扫描2894条、归约3418条、整数乘除1673条、FP向量2157条、旧向量789条、streaming251条重新通过RTL。原220组整数/FP性能和旧mask/扫描基准的结果与周期均和M21相同。FP向量仍为225358周期。混合INT/FP/归约程序通过RTL与映射。

默认访存封装254组RTL通过；公开SpinorVpu在持续monitor读取时通过254组RTL及94组RTL/映射子集。逐访存用例请求与周期和M21相同；测试台末尾增加真实前缀命令、取消、非法重叠、v0生成/消费及返回masked vadd，所以总测试周期增加。monitor ABI1.0，ID=0x2201/caps=0x7ff，bit10表示这三条前缀指令；生产RTL/映射与8位计数回绕检查通过。

SHA确认9个数值/访存/RF/CPU边界单元RTL与M21完全一致，按输入SHA复用既有数值单测、映射单测及局部舍入/重编码/进位证明。本轮未重跑这些未修改单元；局部证明不覆盖整条VPU。实际Orbital接入仍未验证。

## 资源

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M21 SpinorVpu | 17609 | 11965 | 9 | 32 | 6 |
| M22 SpinorVpu | 17731 | 11968 | 9 | 32 | 6 |
| M21 LishiVpuMemory | 15348 | 10591 | 9 | 32 | 6 |
| M22 LishiVpuMemory | 15417 | 10594 | 9 | 32 | 6 |

Yosys xcup未布局映射。RAM原语是分布式LUTRAM，不是BRAM块数；这些RAM也消耗器件LUT。

## 云端条件时序

| 每段假设连线ps | M21公开顶层ns | M22公开顶层ns | M22计算/访存封装ns |
|---:|---:|---:|---:|
| 50 | 2.682 | 2.791 | 2.791 |
| 100 | 3.232 | 3.391 | 3.391 |
| 200 | 4.409 | 4.668 | 4.668 |

100ps档公开顶层3.391ns，相对300MHz的3.333ns算术余量-0.058ns；计算/访存封装3.391ns，余量-0.058ns。公开顶层覆盖路径为vpu.vpu.unit.r32.sAdjustedExp[0]到vpu.vpu.unit._r32_io_out[22].D。两种封装各自综合，不能混用预算。

使用相同的Yosys网表分析、RapidWright家族参考弧、50/100/200ps连线与100ps建立假设。M21图从gzip冻结包恢复后核对原始SHA，两版权重/来源一致。没有放置布线、-2速度校准、DSP相关路径、时钟树/hold、RAM写或I/O时序，没有器件SDF/STA、WNS或Fmax。本轮未执行Vivado，300/500MHz是否通过仍为null；M5的真实OOC结果不能继承。

## 复现与剩余范围

make bootstrap；python3 scripts/verify_m22.py；python3 scripts/package.py --milestone m22。receipt.json绑定源码、冻结基线、RTL、网表、测试台和证据。完整复现入口会重新生成复用单元的证据。见docs/m22-prefix-mask.md与docs/isa-coverage.md。viota/vid、排列、宽窄/定点、FP归约、完整LSU、系统保护/上下文和真实SoC接入仍未完成，不声明完整V/RVA23。本轮未运行Verilator或修改Valence源码。
