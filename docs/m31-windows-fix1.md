# M31 Windows 打包修复

用户本地日志显示 Vivado 已执行到 DSP 导出并正常退出，随后 Windows PowerShell 5.1 找不到 `System.IO.Compression.ZipArchiveMode`，失败发生在结果打包阶段。此前 Linux PowerShell 7.5.4 检查没有覆盖 .NET Framework 的程序集加载差异。尚未收到本地时序报告，不能据此认定 300MHz 已通过。

修复同时显式加载 `System.IO.Compression` 和 `System.IO.Compression.FileSystem`。主脚本在启动 Vivado 前先加载，避免完成长任务后才暴露加载失败；实际打包共用新的独立 `pack_results.ps1`。

## 对现有结果补打包

不需要再次运行 Vivado。把 `scripts/windows-current/pack_results.ps1` 保存到本地原 `spinor-m31` 文件夹，执行：

```powershell
cd D:\surplars\Downloads\spinor-m31
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\pack_results.ps1 -RunDirectory "D:\surplars\Downloads\spinor-m31\runs\M31_All_20261016_225847_511"
```

上传脚本打印的 `spinor_results_M31_All_20261016_225847_511_packed_*.zip`。不必修改原 run.ps1 或原输入 manifest；新脚本读取已有 run-inputs.json 并保留它，刷新 output-sha256.json，把报告、波形、DCP/EDIF 和 DSP 数据一起打包，省略 .Xil/xsim.dir 缓存。它不包含启动 Vivado 的步骤。

重复打包排除旧 output-sha256.json，防止把旧 manifest 的散列写进新 manifest，或者在 ZIP 中出现两个同名 manifest。默认生成独立的新 ZIP，不覆盖已有目标，也不允许 ZIP 位于被打包目录中。

## 后续新运行

`spinor-windows-m31-fix1.zip` 使用独立 `spinor-m31-fix1` 文件夹，包含更新后的 run.ps1、pack_results.ps1 和输入散列；RTL、测试台、Vivado Tcl 以及 DSP 导出器与原 M31 包逐字节相同。可按原方法启动全新运行；当前这次已完成的本地运行只需补打包。

云端用 Linux PowerShell 7.5.4 执行假 Vivado launcher，验证正常/非零退出后的真实 ZIP 打包、连续两次恢复打包、散列、无重复项、保留原始数据，以及拒绝覆盖/目录内目标。未执行 Windows PowerShell 5.1；本次不涉及 HDL 修改，无需重新综合或重跑硬件回归。详情见 reports/m31-fix1/receipt.json。原 M31 报告和原交付 ZIP 保留，不将打包失败当作时序失败或时序通过。
