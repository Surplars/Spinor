# M61：可选寄存隔离顶层

新增 `SpinorIsolated` 与 `GenerateIsolated`，旧提交边界保留。
49个原有Scala文件精确不变，5个增加默认关闭的可选分级；四种旧直接配置重新生成的完整SV与已验收M56逐字节相同。
本轮优化SoC接入时序，不增加ISA指令，也不在VPU内加入CPU退休器或MMU。

## 协议与边界

命令、context、grant token、FCSR输入先采样，宽token比较在采样之后进行。
RAM A/D及monitor A/D分别经过非直通寄存切片；ready仅由本地寄存状态产生，未使用透明flow/pipe队列。
预览包只保存一份，供preview和done共用；授权前核心completion.ready保持0。
monitor A另加一拍控制值校验，保持64位非法高位拒绝与32位未使用高半部忽略，
再用等价的小位宽控制替代原64位<=2比较链；实际snapshot/clear和非法写均经真实端口验证。
隔离顶层另启用LSU几何译码寄存和短地址分段；整数隔离配置在RAM窗口选择与操作数扩展之间再加一拍，
切断实际映射中暴露的长链。四种旧直接配置不启用这些新增分级；不能把旧核心测试自动当作分级后的证据。

CPU在不可撤销队头完成本地资格检查后offer；收到preview后，通过完整80位token的grant授权。
grant握手后在本地检查身份、执行核心完成握手、采样发布后状态，再返回可反压done。
CPU在done.fire处理标量结果/异常/flags，授权至done期间不得丢弃owner或插入恢复/年轻指令。
这是一项明确的新协议，不能将grant视为旧reply的同拍退休握手。

授权前算术stop可取消，memory stop保留总线与所有者；grant胜过同拍stop，此后不能撤销授权。
身份错误封锁，不消费核心完成。数据/状态观察也经过寄存；同频隔离不提供CDC。

## 功能验证

四配置：标准host、Deep host、标准standalone、integer-deep。
从冻结M60独立参考语料取SEW8/16/32/64、LMUL1、分离布局、起点0/2场景。
前三配置覆盖330编码，整数配置229编码。不是完整M60全部几何重跑，也不把旧核心证据冒作新隔离顶层测试。

矩阵在真实隔离顶层GSim公共端口执行 **41,648条VPU命令**，另有5,280次测试宿主自身FCSR访问。
每条比较完整32向量寄存器和已实现状态，阻塞preview与done，检查未授权普通指令不提前发布，
检查完整身份和授权后owner保持。done的发布后状态快照也与参考CSR值比较，反压期间必须保持。
host FCSR观察与执行舍入快照分开：首次offer前的context访问也必须正确观察宿主frm/fflags，
done.state.fflags是CPU合并本条flags之前的值。共46,928个测试命令记录；不是DUT轨迹重放。

每配置另有真实RTL数值/访存定向测试：offer同拍stop、preview后stop、grant同拍stop、
被反压A上的load/store停止、响应排空、原基址前缀重试、denied错误、monitor多请求反压，
及已知答案FP舍入快照/flags（整数版为FP拒绝）。合计66条定向VPU命令、
72次实际RAM A/D请求/响应。停止的待返回load不写入响应数据并保留vstart=0；
已发store仍提交1元素前缀、vstart=1，再从原基址恢复。没有将两者混为同一个前缀策略。
12次运行比较器/错误授权控制与12次结构检查负控制均检出。

针对新增LSU分级，每配置再经真实端口执行冻结M58的404场景、1,384条命令，
使用未修改Spike参考与显式VL/vstart规则，比较完整32向量寄存器、已实现CSR及8KiB RAM。
覆盖strided NF5/6/7的EEW16/64字段故障、FOF NF2/8全EEW的首元素异常和后续截断、恢复后的算术。
合计5,536条恢复测试命令、24,928次实际RAM请求/响应。
本轮正向测试共47,250条隔离顶层接收的VPU命令，包含预期取消/非法场景；测试宿主FCSR操作另计。

## 组合隔离与时序

对四份完整xcup映射网表检查全部非clock/reset输入到全部输出的组合锥，均为0条组合通路。
另检查所有外部payload没有在输入采样寄存器前进入组合逻辑，避免仅切断ready却留下宽token比较。
wire旁路、LUT旁路、采样前payload逻辑的三种故意破坏均被检查器检出。
这是对当前生成网表的结构检查，不是CDC、IO约束或器件时序认证。

四配置资源与固定100ps/link条件预算：

| 配置 | 逻辑LUT | FF | DSP | 条件预算ns |
|---|---:|---:|---:|---:|
| host | 24966 | 15414 | 9 | 3.300 |
| deep | 24994 | 15696 | 9 | 3.300 |
| standalone | 24909 | 15404 | 9 | 3.300 |
| integer | 14375 | 8701 | 1 | 3.277 |

使用原M25固定家族权重与显式连线假设，排除DSP影响端点、主IO、真实时钟和器件布线，
未按ZU15EG-2校准；不含hold/恢复移除/存储写入签核。实际300MHz仍未知。
寄存隔离消除了当前网表中的跨接口组合贯穿，不能保证系统布局拥塞、IO延迟或时钟质量不影响Fmax。
保留版本化RAM和FP单元，不把向量寄存器文件改成大规模触发器。

完整协议、生成命令和CPU迁移要求见[隔离指南](../../docs/m61-isolation.md)。
```bash
python3 scripts/verify_m61.py
python3 scripts/verify_m61.py --check-only
```
完整重跑需要已保留的固定工具与M60参考产物；使用/tmp的构建中间文件可再生成，
当前验收绑定的SV/FIR/GSim源码和网表以gzip保存在build/m61，check-only不依赖/tmp仍存在。
旧功能/文档receipt不改写。当前仍不声明完整V/RVA23/Zvkt、实际CPU/Linux集成或器件300MHz通过。
