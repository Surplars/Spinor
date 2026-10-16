# M23：viota.m / vid.v

本轮优先完善VPU本体，增加索引生成。程序级ELF/Orbital闭环后移，当前没有实际CPU或Linux执行声明。目标仍为ZU15EG -2、300MHz；实现与周期数并不代表物理频率通过。

## 指令与约束

| 指令 | 编码 | 结果 | 约束 |
|---|---|---|---|
| viota.m vd, vs2, vm | OP-V，funct6=0x14，funct3=2，vs1=16 | 每个有效元素i之前，源mask与执行mask共同有效的置位数 | vstart必须为0；单mask源不得在目的LMUL组内；masked目的不得包含v0 |
| vid.v vd, vm | OP-V，funct6=0x14，funct3=2，vs1=17，vs2=0 | 原始元素索引i，masked-out元素不重新编号 | 支持vstart；非零vs2保留编码报非法；masked目的不得包含v0 |

两者支持全部22种合法SEW/LMUL。目的按SEW与LMUL分组和对齐；viota源只有一个mask寄存器，无LMUL对齐要求。目的8/16/32/64位元素零扩展结果。当前最大VL128，计数0..128可用8位表示。非法检查在VL0时仍执行。保留tail、inactive及vstart之前的元素，符合允许的undisturbed行为；合法完成清vstart。FP和定点CSR保持不变。

viota示例（从元素0开始列出）：源置位[1,1,0,1]、执行mask[1,0,1,1]，有效位置0/2/3输出0/1/1，位置1保持原值；被执行mask屏蔽的源位不计数。vid同样执行mask的输出为0/原值/2/3。

## RAM与流水

目的先复制到未提交版本，源仍读取已提交RAM。viota每个有效元素从单mask行读取相应源位，将已有scalarResult低8位的旧计数送到整数Op.move，并独立更新前缀计数。8位增量使用ParallelIncrement平行前缀，不引入64位反馈加法器。vid直接将index送入同一流水，省掉源RAM读周期。

复用既有b暂存、整数lane、tag写回、候选RAM和版本表，不新增向量组快照、数据RAM或DSP。增加2位工作类型和FP版2位寄存译码；公开综合FF增加4。内部计数不作为标量完成值返回，写标量标志为false。一次仍只有一条指令在途，基础整数元素允许流水重叠。

VL128、e8/m8、无掩码时，FP顶层viota为542周期、vid为414周期，包含命令与完成握手。有效元素发射间隔分别4/3周期；未启用的元素只推进索引。这里的串行RAM访问及单lane限制吞吐，不应推导成128路并行SIMD。旧220组性能的结果和周期保持M22值。

完成等待候选写排空。完成背压不发布版本和CSR；flush使候选写与后续流水无效。下一条译码重置私有计数，取消不会污染下一次索引生成。

## 验证与时序

`tests/test_index_generate.py`使用整向量索引集合的数学前缀和作参考，逐条检查32个寄存器、版本、CSR与完成信息。完整RTL1674条命令，455次viota、283次vid、296次非法、62次撤销，覆盖22种类型、全部128源位、稀疏/全零/全一mask、VL0、部分尾部、目的组首尾重叠、v0源/目的、vstart恢复及背压。238条smoke另在映射网表运行，要求功能和周期与RTL完全一致；无FP与16位切分版也运行独立smoke。

`GenerateIncrementProof`把8位计数增量加入原32/55/109位增量、地址和配置比较的SAT检查。此证明局限组合公式，不能替代FSM、撤销和RAM仿真。

公开SpinorVpu联合TL与monitor测试新增viota→标量提取→vid和结果RAM核对。Monitor ABI1.0保持，实现ID更新0x2301，capability bit11表示这两条索引指令。

公开顶层17767 LUT、11972 FF、9 DSP、RAM64M8×32/RAM32M16×6；相对M22增加36 LUT/4 FF。RAM原语是LUTRAM，不是BRAM。相同RapidWright家族参考与每段50/100/200ps连线假设，公开顶层最大预算2.791/3.391/4.591ns；100ps档仍是FP32舍入输出路径。新功能没有抬高该档最大预算，但3.391ns大于300MHz周期3.333ns；不能据此宣布通过或不通过实际器件时序。

没有布局布线、-2校准、DSP相关端点、时钟树/hold、RAM写及I/O检查；没有器件STA、SDF或WNS。当前工具负责功能仿真、Xilinx原语映射和条件延迟预算，每轮保持这些边界。

完整证据与输入SHA见[报告](../reports/m23/evaluation.md)。复现：`make bootstrap`、`python3 scripts/verify_m23.py`、`python3 scripts/package.py --milestone m23`。

## 后续

继续补排列/滑移、宽窄整数、FP归约与更多LSU模式，并逐轮保持资源和路径对照。实际Orbital提交、权限/VS/FS、VM/PMP/一致性及Linux上下文仍需独立集成验证。当前不发布完整V、RVA23或所有程序可运行的承诺。
