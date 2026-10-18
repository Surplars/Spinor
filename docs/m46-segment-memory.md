# M46：单位步长分段访存

新增`vlseg2…8e8/16/32/64.v`与`vsseg2…8e8/16/32/64.v`，共56种标准编码。把内存中的结构数组拆到连续向量寄存器组，或反向打包；例如RGB/RGBA、复数实虚部、坐标和结构字段。VLEN128/ELEN64、单lane和单条指令/单个总线事务在途保持。此轮仅单位步长分段；跨步/索引分段与全部FOF仍待实现，见[完整性计划](rvv-completion-plan.md)。

## 布局与合法性

地址为`base + (element × NFIELDS + field) × EEW/8`，按模2^64计算。VL和vstart均以整段元素计，mask按整段生效。每个字段占`max(1, EMUL)`个寄存器，EMUL=LMUL×EEW/SEW；基寄存器按字段EMUL对齐，整体不要求按总寄存器数对齐。支持分数EMUL，字段仍分别从下一个寄存器起始。要求EMUL范围1/8～8、EMUL×NFIELDS≤8、最后寄存器≤v31；非法几何在空VL、全mask关闭和vstart越界时也拒绝。masked数据v0与EEW1的mask源重叠继续按保留形式处理。NF不允许绕过MEW、vtype、宽度与lumop检查。规范摘录见[依据](references/m46-segment-memory-v1.0.txt)。

mask关闭段不读数据RF、不访存；prestart、mask-off和tail数据选择保留。当前vta/vma仍采用允许的保留策略。整组/mask访存使用独立的M45路径，不把它们的NF误识别为segment。仅访问物理普通RAM，没有分页/PMP/MMIO或缓存一致性。

## RAM通路、故障和停止

复用原64位RF块缓存和内存地址阶段；新增字段号、字段组跨度、字节偏移等31位状态，没有额外整组FF快照、RF端口、DSP或RAM。初始偏移用最多8次短加法计算`vstart×NFIELDS×EEW/8`，避免组合乘法链；正常元素的偏移也在前一状态寄存，原非分段指令周期保持。字段串行处理，没有多字段并行或burst。

字段按序单独提交，整段全部字段完成后才推进vstart。故障可以留下当前段内已完成的字段，vstart仍指向该段；重试从原基址、该段字段0重做。普通RAM中重复写同一值可接受，不能将此语义用于MMIO。stop等待已经发布的事务排空；已发store不可撤销，load的未提交结果可丢弃。响应错误优先于同拍停止。宿主继续保留owner/token直到completion/status，不得把部分段当作整条指令已取消。

## 验证与时序

独立LSU Python模型覆盖全部56编码、合法SEW/LMUL/EEW/NFIELDS组合、分数及多寄存器组、v0/v31、mask、vstart、64位回绕、非法几何、五种响应错误、反压及停止竞争。RTL和完整映射网表均逐命令检查全部64个RF块；停止时依据总线前缀和实际RF写入数量计算期望字段状态，不从DUT数据生成期望值。

真实RAM/TileLink测试完整RTL核对全部32个寄存器，两种ALU分段均执行精简RTL/网表，保留56编码、字段故障重启及停止。停止案例检查完整RF/相关内存与全部允许的当前段字段前缀，不以仅比较整段前缀误拒合法部分写回。公共SpinorVpu用字面量检查三字段e16、非零vstart与mask跳段；四预设检查两字段e32拆包/打包及实际请求次数。旧访存矩阵继续执行；未变化算术仅在完整输入/RTL/证据SHA核对后复用。

monitor实现ID为0x4601，ABI1.0和能力位布局不变。先检查两个顶层、四预设的固定M25预算，再执行完整回归。云端仍用Yosys xcup、Icarus功能仿真及RapidWright家族表参考；100ps/link与3.333ns门槛不变。未布局布线、未按ZU15EG-2校准，排除DSP端点；不是器件STA或300/500MHz签核。[结果和散列](../reports/m46/evaluation.md)。
