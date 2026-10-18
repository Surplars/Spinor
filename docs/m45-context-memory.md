# M45：整组寄存器与mask访存

新增16种 `vl1/2/4/8re8/16/32/64.v`、4种 `vs1/2/4/8r.v` 及 `vlm.v`、`vsm.v`，共22种标准编码。保持VLEN128/ELEN64、单lane、单条指令及单个外部事务在途。此轮补齐mask/整组访存原语；剩余分段与FOF以及架构/系统缺口见[完整性计划](rvv-completion-plan.md)。

## 整组与mask规则

整组传送NREG=1/2/4/8个连续寄存器，基寄存器按NREG对齐。load支持EEW8/16/32/64，store的标准宽度仅为8。有效长度EVL=NREG×128/EEW，忽略当前VL和全部vtype（包括vill）；从vstart元素继续，vstart≥EVL不访问，成功完成清零vstart。字节布局与普通寄存器相同。支持v0及单寄存器v31，不把低寄存器号解释成标量x0。其他NF、错误对齐、MEW、vm=0及保留store宽度拒绝。

mask按字节传送ceil(VL/8)字节，EMUL固定1，忽略SEW/LMUL对数据布局的影响，但仍受vill约束。vstart以字节计，允许v0作为数据；只允许NF0、width0、vm1。load复制最后一个完整字节，包括VL未覆盖的填充位；之后字节选择保留，属于允许的tail-agnostic实现。vta/vma不改变这一编码的尾部策略。

两类指令均用`Command.scalar`传rs1物理基址，忽略scalar2。有效地址逐元素检查自然对齐与普通RAM区域。上下文访问不修改VL/vtype/FP或定点flags。整组访存EVL最大128，当前7位vstart的可表示范围为0–127；测试不把写入128后截断为0误算为一次空操作。

## RAM通路与停止

复用原长度、索引、宽度、数据块缓存和单位步长地址阶段，没有整组FF快照、额外RF端口或DSP。特殊形式使用两个设置状态，避免EVL/type处理接到原EMUL译码长链；原单位步长、跨步、索引和算术的指令周期保持。EEW64整组load直接覆盖64位RF块，跳过旧值读取。store当前逐字节单事务，未合并总线传输或实现burst。

load/store逐元素提交，故障保留前缀与对应单位的vstart，重试仍传原基址。stop/flush等待已发布事务排空；已发store不可撤销，响应错误优先于停止。宿主须保留所有者/token直到completion。这里只支持物理普通RAM，没有MMIO、VM/PMP或一致性；保存恢复完整向量上下文还需CPU/drivers另行处理VL/vtype/vstart、FCSR、vcsr与VS/FS，不等于Linux上下文切换已经实现。规则摘录见[规范](references/m45-context-memory-v1.0.txt)。

## 验证与时序

独立LSU模型检查全部64个RF块、逐字节内存、完整64位地址、22编码、NREG/EEW、v0/v31、vill/VL0、部分字节VL、重启、保留形式、五类响应错误、接口反压和停止竞争。8KiB循环数据后端与全64位地址检查分别声明。完整真实TileLink RTL检查全部32个寄存器；精简RTL/网表保留22编码、末元素/末组、故障恢复、非法形式及停止检查，核对数据组、v0与保护寄存器，避免重复大量无关context事务。独立LSU完整网表仍检查全部RF。

公共顶层用字面量验证vill/VL0下整组恢复保存、vill拒绝mask、VL9两字节mask与邻字节保护；四种规模预设另用跨区域基址和非零vstart验证原基址定位、单位和实际请求次数。旧访存与算术矩阵继续保留，未改动算术只在精确依赖/RTL/证据SHA校验通过后复用；缺失缓存即完整执行。先过两个顶层和四个预设的固定预算，再启动完整数值矩阵。monitor实现ID为0x4501，ABI1.0与能力位布局保持，不能据此声明完整RVV。

云端仍用Yosys xcup映射、Icarus功能仿真和固定M25/RapidWright模型，100ps/link门槛为3.333ns；未布局布线、未按ZU15EG-2速度档校准，排除DSP端点。器件300/500MHz尚无M45实现结论。结果与输入散列见[评估报告](../reports/m45/evaluation.md)。

## 宿主故障映射

修正旧宿主边界把raw cause=1当作不对齐的问题。实际LSU的load/store不对齐分别为4/6，宿主现在保留对应架构cause4/6，其他物理访问故障映射5/7，非法优先cause2。真实LSU与真实宿主边界直接连接，RTL/网表各检查26例访问前故障；模拟对端另遍历128种raw cause/方向组合。尚未连接Orbital CPU或验证Linux异常处理。
