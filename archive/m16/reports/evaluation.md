# M16 云端优化与边界验证

本轮处理LSU地址和FP后处理增量，并化简vsetvl/vsetvli/vsetivli的长度及分数LMUL检查。没有新增周期、寄存器、ISA或请求队列。目标仍为xczu15eg-ffvb1156-2-i、300MHz基线与500MHz候选。

## 同模型预算

沿用固定RapidWright家族表、相同50/100/200ps每段连线假设及100ps setup预算，重新分析冻结M15和M16：

| 每段假设连线ps | M15预算ns | M16预算ns | 预算减少ps |
|---:|---:|---:|---:|
| 50 | 3.246 | 3.246 | 0 |
| 100 | 3.891 | 3.846 | 45 |
| 200 | 5.291 | 5.200 | 91 |

改善有限；50ps档的300MHz预算差仍约+87ps，中高档分别约-513ps/-1867ps。不能解释为实际WNS、统计显著改善、频率通过或实际Fmax。旧最差LSU地址、FP绝对值链退出当前最差位置；50/100ps档现在转到整数lane控制/进位，200ps档为FP输入到返回数据。详细路径见m15-baseline-budget.json/m16-budget.json。

仍排除346个受未建模DSP影响的捕获端口，当前覆盖18031个FF捕获端口。没有-2校准、布局、布线、实际引脚/负载、时钟树、hold或RAM写setup。完整CARRY8类别最慢弧代替CARRY4等模型假设不提供实际误差界。没有新Vivado P&R或SDF，物理基线仍为M5。

## 改动与代价

FP增量从16位局部进位改为逐位前缀；LSU低字carry-select、高字前缀递增；配置AVL用高位归约+低8位比较，分数LMUL规则使用等价布尔条件。前期候选因集成配置返回链导致预算回退，最终候选已消除该回退；冻结的是最终结果。

集成14686 LUT、10143 FF、440 CARRY4、9 DSP48E2、32 RAM64M8、6 RAM32M16。相对M15增加249 LUT，减少51 CARRY4，FF/RAM/DSP不变。数据路径仍13跳，控制12→10跳，最大扇出403不变；独立LSU9/9跳，FP lane13/10跳。不是整体面积下降，也不是增加向量组FF快照。

全部已测周期不变，24组访存基准逐项与M15一致；FP32/FP64 add仍31周期，SEW64乘法97/101、除法264周期。仍单指令所有权和单请求访存，保持逐元素前缀与延迟停止规则。

## 检查

- 完整访存254组（新增32组边界）、77组停止、78种合法EEW/EMUL。
- RTL/映射后精简94组访存、9组停止，外部结果与周期一致；新边界用例均为本地故障，完整故障地址/vstart/原因/零请求由独立Python模型核对。
- FP算术6811组、205组flush/reset；FP lane转换5019组、492组flush/reset；FP向量2157条，整数乘除向量1673条。
- FP精简RTL/映射后385组、12组取消一致；普通RamVector/RamVector16/RamVectorFlops各789条配置/CSR/整数检查通过。
- 增量32/55/109位全输入、拆分64位地址公式全输入、配置比较与分数LMUL规则全输入SAT等价证明通过。组合证明不覆盖状态机或物理时序。
- IntegerDivide/IntegerMultiply/FloatingPointConvert/TileLinkReservation生成RTL与M15散列相同；复用其按SHA绑定的数值/映射后证据及IEEE编码、carry-select证明，没有把复用结果算作本轮新增测试。

精确输入、输出与通过状态由receipt.json冻结。make verify-m16 / make package-m16可从当前源码重建全部验证。包内包含前后映射JSON、SAT及回归证据。

## 后续

评估整数lane的16位分段候选，比较控制进位链、资源和流式吞吐；继续关注FP输入/返回路径。仍无实际Valence接入、完整RVV、分页/PMP/一致性、MMIO或CPU精确异常，本轮不要求Windows重跑。
