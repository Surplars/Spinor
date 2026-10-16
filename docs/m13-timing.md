# M13 时序优先

本轮先做云端条件预算并切分识别到的浮点输入重编码路径。没有增加请求队列、多请求并行或 ISA 指令。仍以 ZU15EG-2、300 MHz 为设计目标，500 MHz 为候选。

## 条件模型

scripts/cloud_budget.py 从 tools.lock.json 固定的 RapidWright JAR 读取 UltraScalePlus 家族单元表，先验证 JAR SHA。LUT 最慢 O6 弧150ps，RAM读参考165ps，CQ参考77ps。CARRY4 保守计完整 CARRY8 最慢241ps，而不是假装已经有 CARRY4 实际布局。BUF/INV保守按 LUT150ps计。FF setup100ps为额外假设。

对 FF→组合逻辑→FF 的保守依赖图逐路径累计，分别假设每段连线50/100/200ps，包括最终捕获前的连线。没有针对 -2 的标定、位置、负载、实际引脚映射或 LUT 输入排列。这些也不是乐观/典型/悲观工艺角，不能解释成实测置信区间。

DSP48E2 没有新布局和匹配的输入/输出弧，不能把旧 M5 的实例延迟表当作新 DSP 延迟。工具排除所有组合上受未建模 DSP 影响的捕获端点，当前为346个；已覆盖18000个FF捕获端口，数量不是寄存器数。没有完整 VPU 时序覆盖、主输入/输出、RAM写setup、hold、恢复/移除、时钟树或 SDF 仿真。

测试用手算2级LUT链检查数值，确认DSP端点和主输入路径排除、组合环拒绝，以及失败后清除旧成功结果。输出记录工具、网表、JAR和表的散列；脚本失败不能留下旧成功报告。

## RTL 改动

M12 最长数据链为 request_c→rc 的 FP32 精确 widening：前导零/规格化、指数偏置扩展和特殊值打包在同周期。现在先把三路输入的 RawFloat(8,24) 注册，再在 recodeFinish 阶段扩展至 FP64 共用格式。double 输入在第一阶段直接重编码，统一等待第二阶段后继续。

仍调用固定版本 HardFloat 的 rawFloatFromFN/resizeRawFloat，没有修改第三方源码。NaN payload、signaling bit和符号保持，不发生第一次舍入。新增寄存器不是整个向量组快照。flush/reset 在任一阶段取消请求，回复仍遵守背压和容量一。

所有合法 lane 请求增加一个周期；FP32/FP64 add 从30变为31周期。没有提高每周期发射能力。访存引擎生成RTL与M12完全相同；少量访存基准周期可能因全局周期性 A 背压相位改变而波动，不能记为新 LSU 吞吐收益。

## 复现

make verify-m13 / make package-m13。rapidwright-probe 使用固定 JAR；已有工具时离线读取。预算命令：

```bash
python3 scripts/cloud_budget.py --netlist archive/m12/synth-LishiVpuMemory/mapped.json --output build/timing-budget/m12
python3 scripts/cloud_budget.py --netlist build/synth/LishiVpuMemory/mapped.json --output build/timing-budget/m13
```

package 含旧映射 JSON，便于相同模型复算；不含庞大工具缓存。物理验证仍需匹配当前 RTL 的 Vivado 实现，本轮不要求 Windows 运行。
