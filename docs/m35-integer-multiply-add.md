# M35：单宽整数乘加与访存地址分段

新增 `vmacc/vnmsac/vmadd/vnmsub.vv/vx` 共8种编码，SEW8/16/32/64，全部22种合法SEW/LMUL组合。结果按SEW取模；低积无须区分有符号/无符号。`vmacc` 为 vs1×vs2+旧vd，`vnmsac` 为旧vd−vs1×vs2；`vmadd` 为 vs1×旧vd+vs2，`vnmsub` 为vs2−vs1×旧vd。vx标量先截取SEW位。宽化整数乘加仍未实现。

复用原16×16分时乘法器和分段IntegerLane加减流水；顺序读取vs2、vs1（vv）、旧vd，没有新增RAM端口、整组FF快照或乘法器。第三操作数复用原FP的64位c暂存；无FP配置现在也使用该暂存。低积返回后写入已有64位归约暂存寄存器，经过独立macLaunch/macAwait阶段调用原ALU；乘法输出与加减之间有寄存器边界，返回选择不进入RAM→移位/扩展→a/b的读操作数路径。仍为容量一、逐元素串行乘加，没有每拍一元素或多指令并发保证。乘加模式、目的乘数选择和加减方向在decode阶段寄存，避免指令字段解码直接进入ALU操作数选择和比较路径。

同宽源/目的组可相互重叠，所有读都从已提交RAM版本取得；候选目的组仅在完成握手后切换版本。保留prestart、mask和tail元素，支持合法vstart；VL0及无有效元素时仍检查编码和组对齐。遵守现有执行mask（EEW1）与数据源（SEW≥8）的不同EEW源别名检查。取消执行不会发布候选结果；vxrm/vxsat和FP舍入/flags保持不变。

初次公共顶层映射出现3.368ns条件预算，最长链经过LSU的index→字节偏移→寄存器块地址→共享RF接口。将6位chunkAddress移入现有addressLow阶段寄存，后续checkAddress/readChunk/写回使用该地址；mask读取保留固定地址。没有增加访存状态或元素周期，write-through缓存匹配和停止/故障前缀语义不变。必须重新验证访存端点，不能沿用旧VectorMemoryEngine的逐字节等价声明。

RAM读返回路径使用16位one-hot字节选择，在原RAM请求阶段寄存选择码，保持读延迟不变；新增SAT检查其与128位字节移位取64位窗口对所有输入等价。FP配置增加一个合法性结果阶段，以原illegal寄存器分离组重叠/合法性检查与状态/结果控制。每条向量算术指令固定增加1拍，CSR/vset和LSU元素周期不变；无FP配置保持原指令开销。

独立Python参考对三源使用不可变架构快照，按规范的四个数学表达式计算任意精度整数后截取SEW；逐条读取全部32个向量寄存器，并检查版本、配置及sticky状态。覆盖全部同宽类型、全别名、分数LMUL、最高寄存器组、标量截断、溢出/减法回绕、mask、VL0、非零vstart，以及RAM/部分积/ALU/候选写回/停顿完成阶段的取消。无FP和16位切分配置有smoke；79条混合序列检查与FP FMA、普通乘法、排列和宽窄操作切换。

保留旧向量族完整RTL回归和220组旧性能对比。当前顶层网表用精简集覆盖全部8种单宽乘加编码和4种SEW、别名/掩码/重启/跨组/取消，并验证79条混合序列（含宽化乘法）、LSU/公共接口和monitor。未改动数值单元按输入SHA保留证据，冷启动verify重跑数值测试；局部SAT证明按输入SHA检查，增量/地址证明因控制器和LSU改动重跑。Monitor ABI仍1.0，ID0x3501、caps0x7fffff，新增bit22单宽整数乘加。Command/Completion和TileLink外部端口不变。

云端评估使用Yosys xcup映射、Icarus RTL/网表功能仿真、SAT及RapidWright家族延迟参考。固定M25权重和100ps/段连线假设，公共和计算/访存顶层均须≤3.333ns。模型排除DSP相关端点，不含布局布线、-2速度档校准、hold、时钟树、RAM写时序、外部IO或SDF。实际300/500MHz未知，不能继承M31本地OOC结论。

当前仍是部分RVV、容量一；Orbital/Linux未实际接入。剩余大项与验收条件见[完整性计划](rvv-completion-plan.md)，不是完整V/RVA23支持声明。

复现：

```sh
make bootstrap
python3 scripts/verify_m35.py
python3 scripts/package.py --milestone m35
```

本轮项目包包含当前源码、RTL、验证和映射证据，冻结M25/M34比较图与M31本地基线记录。没有新的Windows执行包，旧M31包只验证M31。规范语义与8条编码摘录见 `docs/references/integer-multiply-add-v1.0.txt`。
