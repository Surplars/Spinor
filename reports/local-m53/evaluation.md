# M53：Vivado 本地时序结果与收尾修复

**当前标准浮点 SpinorVpu 在 ZU15EG-2 的独立 OOC 内部时序满足本次约 300MHz
约束。** 这是用户本地综合、布局布线后的真实 Vivado 报告。本次退出 1 发生在报告
写完之后：收尾 Tcl 错用了 Vivado 不支持的 `redirect` 命令。`routed.dcp` 已按日志保存。

## 核验结果

| 指标 | 本次值 |
|---|---:|
| Part | xczu15eg-ffvb1156-2-i |
| 申请 / 保存周期 | 3.333333ns / 3.333ns |
| Setup WNS / TNS | +0.090ns / 0 |
| Hold WHS / THS | +0.042ns / 0 |
| Pulse width slack / 总违反值 | +1.124ns / 0 |
| Setup / hold 端点 | 各 27,562，失败均为 0 |
| Fully routed / routable nets | 26,029 / 26,029 |
| Routing errors | 0 |
| 无时钟 / 内部未约束端点 / 时序环 | 均为 0 |
| 总 LUT / 其中逻辑 LUT | 18,085 / 17,989 |
| FF / BRAM36 / DSP | 12,490 / 2 / 7 |

Vivado 2025.1 build 6140274，Windows，-2 production speed file。报告目录时间为
2026-10-19 14:41:08 至约 14:50:17（用户机器本地时间）。检查上传 ZIP 的 CRC、
全部输出 SHA256，以及输入 manifest 与原始 handoff ZIP 完全一致；RTL SHA256 为
`e01014731b31a242a778f66a999de789a90b2e7b1a606ae9770da9f0a0da169d`。
硬件与 M50/M51/M52/M53 已验证版本相同。

## 范围和关键路径

613 个输入和 608 个输出未指定 IO delay，HD.CLK_SRC 未指定，Vivado 明确提示 OOC
时钟延迟/偏斜估计的限制。内部数据连线完成布线，但这是独立块在当前 OOC 时钟假设下
的结果；SoC 时钟缓冲/位置、接口延迟、负载、跨时钟路径及板级约束需要集成后另行验证。
不能据此签核整 SoC 的 300MHz，也不能宣称 500MHz 或由正裕量直接保证更高频率。

最紧 setup 路径从 `rf/storage_ext/Memory_reg_1/CLKARDCLK` 的 RAMB36E2 读出，
到 `vpu/vpu/stagedData_reg[79]/D`，经过 5 级 LUT（LUT5×1、LUT6×4）。
数据路径 3.177ns，其中逻辑 1.404ns、布线 1.773ns（55.8%）。后续增加余量可优先
检查 BRAM 读出后的选择/合并和物理位置，而不是把最差路径默认归因于 DSP。

DRC 是 10 条 Warning：2 条 DSP 输入流水、7 条 DSP MREG 流水、1 条无 routable
load 提示；没有本报告中的 Error/Critical Warning 规则项。OOC DRC 本身也注明并非
所有连通性检查均运行。缺少 MREG 的提示是后续频率/功耗的参考，当前内部 setup/hold
已满足约束。Vivado 将 VRF 推断到 BRAM；云端 Yosys 使用不同 RAM/逻辑映射，
不能把两个工具的 LUT 数直接当作一次 RTL 优化收益。

## 失败与修复

`flow-error.txt` 精确指出：

```text
invalid command name "redirect"
redirect -file .../check_timing.rpt {check_timing -verbose}
```

此行在 routed DCP、EDIF、布线/资源/DRC、完整 setup/hold 报告之后，在摘要及 DSP
导出之前。已完成报告有效，摘要缺失、DSP 导出尚未到达，不把它们算作成功。
没有执行 post-route SDF 仿真，也没有生成 bitstream。

修复采用原生 `check_timing -verbose`，输出保留在日志，并从已经生成的
`report_timing_summary` 提取其 check_timing 节。新增 `resume.ps1` /
`resume_vivado.tcl`：校验先前记录的 RTL、DCP part/公共端口和保存的时钟，读取原
`routed.dcp` 后只重做报告/DSP 导出；另建输出目录，原 checkpoint 不变，不重跑
任何综合、物理优化、布局布线，也不改时钟约束。

首版云端 mock 对未知 Tcl 命令过于宽松，漏检了 `redirect`。现在改为显式支持命令
白名单，未知命令直接失败；另加旧错误的负控制、checkpoint 继续流程、part/端口
不符、原文件不变、零实现步骤、原 RTL 不符等检查。PowerShell/Tcl/ZIP 流程测试
通过，**fix1 和继续流程尚未在真实 Vivado 运行**。

## 使用与复现

解压 [fix1](../../handoff/spinor-m53-timing-fix1.zip)，在含 `resume.ps1` 的目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\resume.ps1 -PreviousRun "D:\surplars\Downloads\spinor-m53-timing\runs\M53_Timing_20261019_144108_769"
```

从旧 `run-inputs.json` 自动读取实际安装位置
`E:\Xilinx\2025.1\Vivado\bin\vivado.bat`。原目录和 `routed.dcp` 需保留。
上传新的报告 ZIP；DSP 原始表仍保存在新目录的 `dsp_delay` 下，可按需要再打 full 包。

上传原包原样保存为 [input-reports.zip](input-reports.zip)，机器可读核验在
[receipt.json](receipt.json)。云端重算与流程检查：

```bash
python3 scripts/analyze_m53_vivado.py
python3 scripts/package_windows_timing.py
python3 tests/test_windows_timing_bundle.py
python3 scripts/verify_m53.py --check-only
```

这次物理证据仅覆盖默认标准浮点顶层，未测其他规模预设、Orbital 集成、Linux
上下文切换或板上运行；未改写先前冻结报告中的历史“物理时序未知”字段。
