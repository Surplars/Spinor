# M31 报告包上传

完整 Vivado 结果 ZIP 可能超过当前云端文件下载工具的 32MiB 单文件读取限制。用户 2026-10-16 上传的 `spinor_results_M31_All_20261016_225847_511_packed_20261016_231416_221.zip` 被下载工具以该原因拒绝；尚未读取其中内容，不能据此确认 XSim/布线/setup/hold 或资源结果。

无需重跑 Vivado。把 `scripts/windows-current/extract_reports.ps1` 保存到原本的 `spinor-m31` 文件夹，从现有完整 ZIP 生成较小报告包：

```powershell
cd D:\surplars\Downloads\spinor-m31
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\extract_reports.ps1 -ResultZip ".\spinor_results_M31_All_20261016_225847_511_packed_20261016_231416_221.zip"
```

上传脚本打印的 `*_reports_*.zip`。脚本显式加载两个 Compression 程序集，流式保留 ZIP 根目录的报告、约束、运行信息、散列和 Vivado 日志，以及嵌套仿真日志/PASS 记录；保留条目路径和原始字节。省略 DCP、EDIF、WDB、缓存及 DSP 完整 arc 表；DSP 配置和导出覆盖摘要仍保留。完整包留在本地，后续有需要再单独传较小的器件数据。

也可直接上传 run-summary.txt、timing_routed.rpt、route_status.rpt、utilization_routed.rpt 和 run-inputs.json，先评估时序、布线、资源和源码版本。完整仿真自检证据则需要 simulation 子目录中的 result.txt / simulation-logs.txt。

云端只测试了报告选择器：Linux PowerShell 7.5.4 下的真实 ZIP 流式复制、空格路径、精确内容、缓存排除及拒绝覆盖。没有读取被拒绝的大文件，也没有新增硬件或时序结论。检查记录位于 build/report-extractor/results.json。
