# M31 本地 Vivado / XSim 核查

M31 的 SpinorVpu 已在 Vivado 2025.1、xczu15eg-ffvb1156-2-i 上完成独立 OOC 布局布线，**当前约束覆盖的内部路径满足约 300MHz**。该结果来自用户本地报告；HD.CLK_SRC 和宿主 IO 延迟尚未指定，不是完整 SoC/板级时钟与接口签核。

| 项目 | 结果 |
|---|---:|
| 时钟周期 | 3.333ns（请求3.333333ns，Vivado按1ps精度取整） |
| Setup WNS / TNS | +0.392ns / 0 |
| Hold WHS / THS | +0.009ns / 0 |
| Pulse width slack | +1.124ns |
| Setup / hold失败端点 | 0 / 0，各检查25,582端点 |
| 需要布线 / 已完全布线网络 | 21,784 / 21,784 |
| 布线错误 | 0 |
| 无时钟寄存器 / 未约束内部端点 | 0 / 0 |
| 未设input / output delay的端口 | 613 / 608 |

布局阶段 WNS +0.502ns、WHS +0.020ns；最终报告为布线后的 +0.392/+0.009ns。两种余量均正，但hold仅9ps，真实时钟树/布局改变后必须重新检查。BUFG使用量为0，工具发出Timing38-242与Route35-197，明确指出缺少HD.CLK_SRC会影响clock delay/skew估计；多项Route35-198来自未指定外部partition pin位置。不能用此结果外推最高频率，也不能声称完整SoC已通过300MHz。

## 功能仿真

- XSim整数扩展自检：884条命令，129,796周期，PASS。
- XSim公开SpinorVpu集成：119组访存，783次请求/响应，18,774周期，PASS。
- 并发monitor参考：7,504次读，313次接受、304次完成，50次故障事件、6次停止事件，PASS；这些是TB主动注入并检查的场景计数，不能当成非预期运行故障。剩余接受/完成差来自取消场景。
- 这里是行为RTL自检与静态时序报告，没有post-route SDF仿真。不是完整ISA合规测试。

## 实际资源

| 项目 | Vivado布线后 |
|---|---:|
| CLB LUT总数 | 14,173（器件4.15%） |
| 逻辑LUT | 14,077 |
| LUTRAM / SRL | 42 / 54（合计96个memory LUT） |
| FF | 11,605（1.70%） |
| RAMB36 | 2 |
| DSP48E2 | 7 |

层次报告显示两个RAMB36属于版本化向量寄存器堆；整数乘法器1个DSP、FP lane6个DSP。monitor为1,071逻辑LUT/1,309FF。云端Yosys估计为18,529逻辑LUT/12,308FF/9DSP，并把寄存器堆映射为LUTRAM；Vivado选择BRAM，映射拓扑不同。不能把资源差异当成功能变化，也不能按一个倍率把云端估计校准为器件STA。

## 关键路径与后续

最差setup：`vpu/vpu/rf/storage_ext/Memory_reg_0/CLKARDCLK` → `vpu/vpu/stagedData_reg[115]/D`。数据路径2.876ns，6级LUT，其中逻辑1.359ns、连线1.517ns。当前优先观察BRAM读出后的选择/移位和写回数据复用，而非仅调整DSP流水。

最差hold：`vpu/vpu/lane/queue/enq_ptr_value_reg[1]/C` → `vpu/vpu/lane/queue/ram_ext/Memory_reg_0_7_0_13/RAMA/WADR1`，数据0.133ns；对应整数结果队列写地址。先确定实际时钟源/BUFG和SoC接口时序，再复验此9ps余量，避免对缺少真实时钟模型的OOC结果直接作hold修补。

Vivado还提示BRAM同址读写碰撞；当前VersionedRegisterFile合同禁止客户端同时读写同一物理行。行为自检通过不等于完成BRAM综合网表碰撞模式验证，后续应保持该合同并作定向验证。timescale警告来自DUT未声明timescale而TB声明1ns/1ps；本次行为自检结束并输出PASS，不能把该警告解读为SDF已执行。

7个DSP导出文件的摘要共611行，均非空。报告小包没有原始arc表、DCP和EDIF，不能在此核查每条arc完整性或恢复设计；已有报告足以核查本次已约束内部STA结果，无需为读取这些报告重新运行Vivado。

后续继续补齐VPU指令，同时以此作为固定本地OOC比较基线；接入Orbital/SoC时加入实际时钟和接口约束、重跑实现。当前仍是部分RVV、单指令容量。

## 证据

上传报告包SHA-256：`bb2a66e9990197b1a1d24ace3c5b7d1507a47c364adaa507e0da7de6931a5584`，119912字节。CRC及32个提取报告/日志的SHA均与原output-sha256.json一致；原manifest列77个文件，另外45个输出未收到，未作完整性声明。输入的两份RTL、两份打包TB、runner/Tcl与M31冻结源码/证据散列一致；尚未复开用户DCP。原始用户日志保留于本会话build/local-m31-reports，不额外发布其中的宿主信息。receipt记录逐项散列、约束范围及解析结果。

复核命令：`python3 scripts/review_local_m31.py <上传的_reports.zip>`。旧M31云端与修复报告保留历史状态；本报告补充实际本地结果，不重写原始交付证据。
