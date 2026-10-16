# RapidWright 实测与用途

本工程固定 `v2026.1.1-beta`，下载 standalone Linux x64 JAR，SHA-256 见
`tools.lock.json`。只提取 UltraScale+ 延迟表和 part 表，并按需获取 ZU15EG 数据库；
无需下载完整约 2 GB 的器件数据包。本地该工具目录约 118 MiB。

## 已实际运行

`make rapidwright-probe` 编译并运行 `scripts/java/RapidWrightProbe.java`：

- `PartNameTools` 找到 `xczu15eg-ffvb1156-2-i`，device 为 `xczu15eg`，speed 为 `-2`。
- `Device.getDevice` 成功加载 ZU15EG，数据库网格为 435 行、455 列。
- `DelayModelBuilder` 成功读取 `ultrascaleplus` 家族模型。
- 示例 A6LUT 的 A1→O6 表值 150 ps、AFF CLK→Q 表值 77 ps；这些只是模型 API 查询。
- 输入散列、输出日志保存在 `build/rapidwright/`，随 M4 报告复制。

上述探针本身没有实现 VPU；这些表值不是 ZU15EG-2 上该 VPU 的真实路径延迟。
模型接口不包含负载依赖；查询也未按本器件速度等级完成校准。不能将逻辑跳数乘某个 LUT
表值后宣称 300/500 MHz 通过。

## 能帮助当前设计的地方

RapidWright 有器件连线数据库、逻辑/物理网表接口、RWRoute 和时序分析代码。
可用于分析物理扇出、尝试局部布局/布线，以及比较实现候选。
官方 YosysTools 包含 `synth_xilinx -family xcup -flatten` 到 EDIF 的入口；
它提供逻辑网表导入，不会自动完成所有合法化、单元打包和通用布局。
当前 Yosys 输出的逻辑 CARRY4、LUTRAM 和 DSP 仍须合法映射到原生器件位置。
官方 ReportTimingExample 读取的是已布局布线的 DCP。

本设计含 DSP48E2。RapidWright 的 DSPTimingData 说明，DSP 单元延迟通常由 Vivado
运行 `tcl/rwroute/dump_all_dsp_delay.tcl` 生成，再交给 `--dspTimingDataFolder`。
缺少这些数据时工具可以继续运行，但路径估计可能乐观；当前探针明确记录
`DSP_delays_available=false`。通用 LUT 家族模型不能替代 DSP 延迟。

因此当前采用 Yosys 映射、结构路径分析、Icarus/SoftFloat 功能检查推进流水设计，
RapidWright 作为下一步物理分析工具。器件级 setup/hold、时钟约束、布线、速度等级及
最终 bitstream 仍须完整实现流程验证；最初的能力探针没有 WNS/TNS、器件 SDF 或真实 Fmax，后续 M4 本地结果见下节。

## 后续获得的 M4 实现基线

用户在 Vivado 2025.1 对同一份 M4 RTL 完成了 OOC 布局布线：6 DSP48E2、2 RAMB36E2，
在 3.333 ns 约束下 setup +0.346 ns、hold +0.042 ns，布线错误为零。
HD.CLK_SRC 未设置，380 个输入和 258 个输出未指定宿主延迟，故不构成完整系统频率签核。
后续已导出独立 routed.edf 和 6 份 DSP 文件，共 546 条边界延迟；RapidWright 成功读取并解析。

`scripts/rapidwright_timing.py --checkpoint PATH/routed.dcp --dsp-dir PATH/dsp_delay`
可以构建这份已有物理实现的参考图。脚本显式核查固定版本中 DSP 文件夹构造参数的赋值，
必要时通过反射修正该实例字段，并在结果中记录；不修改原 JAR。
该图不验证真实时钟树、hold、完整 PVT/速度等级及所有 DSP 内部路径，不能把其路径权重换算为最高频率。
M4 的 DCP、DSP 文件及该参考图不得当作 M5 新硬件的实现结果。新硬件需要重新实现和导出。

## 上游依据

- [Introduction：与 Vivado 的关系及 DCP](https://www.rapidwright.io/docs/Introduction.html)
- [固定版本 YosysTools](https://github.com/Xilinx/RapidWright/blob/v2026.1.1-beta/src/com/xilinx/rapidwright/edif/YosysTools.java)
- [固定版本 ReportTimingExample](https://github.com/Xilinx/RapidWright/blob/v2026.1.1-beta/src/com/xilinx/rapidwright/examples/ReportTimingExample.java)
- [固定版本 DSPTimingData](https://github.com/Xilinx/RapidWright/blob/v2026.1.1-beta/src/com/xilinx/rapidwright/timing/DSPTimingData.java)
- [固定版本 DSP 延迟导出脚本](https://github.com/Xilinx/RapidWright/blob/v2026.1.1-beta/tcl/rwroute/dump_all_dsp_delay.tcl)

## M5 实测与 M7 边界

后续 M5 已有本地 Vivado OOC 结果：3.333 ns，setup +0.477 ns、hold +0.036 ns，仍未指定 HD.CLK_SRC/主机 IO 延迟。
云端使用匹配的 DCP/EDF/DSP 表重建 M5 参考图，对导出的 20 条路径逐项对照；Q→D 参考延迟平均绝对差约 50 ps，最大低估约 120 ps。
这些只是已导出样本的误差，不是全图或未来布线的误差保证。
一键流程为 `scripts/cloud_timing_screen.py --results DIR --label M5 --output OUT`；完整记录见 `reports/cloud-m5`。
砺矢 M7 新增除法后仍需独立实现才能得到器件 WNS，旧图只用于理解路径与筛选方向。
