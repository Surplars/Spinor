# M31：整数扩展与本地验证

新增 `vzext.vf2/vf4/vf8` 和 `vsext.vf2/vf4/vf8`。源 EEW 为 SEW 的 1/2、1/4、1/8，目的按当前 SEW/LMUL 写回；支持 e16/e32/e64、共 15 种类型组合。源 EEW 至少 8 位、EMUL 至少 1/8。未包含普通宽化算术、窄化、饱和或 FP 宽窄转换；仍是部分 RVV、单指令容量。

源使用自己的 RAM 地址和位偏移；复用候选 RAM、整数 move 与元素重叠流水，没有整组 FF 快照或额外 DSP。源组按自身 EMUL 对齐。目的与源有物理寄存器重叠时，源 EMUL 必须至少为 1，并占据目的组最高部分；fractional 源与目的共用一个物理寄存器也非法。最高部分的异或判定通过全输入 SAT，与完整端地址相等的判定等价。

mask/tail 保留、合法 vstart、VL0、start≥VL、提交前版本保持和 flush 撤销均有参考模型测试；selector 不作为 vs1 数据源。monitor ABI 仍为 1.0，ID 更新为 0x3101，caps 0x7ffff 的 bit18 表示这些整数扩展指令。完整结果见 [M31 报告](../reports/m31/evaluation.md)。

## Windows 本地执行

下载 `spinor-windows-m31.zip` 并完整解压，进入 `spinor-m31`。仅需已安装的 Vivado 和对应 Zynq UltraScale+ 器件支持/许可证，不需要 Mill、Java、Python 或 RapidWright。以实际安装位置替换下面的路径：

```powershell
cd D:\surplars\Downloads\spinor-m31
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -VivadoBat "E:\Xilinx\2025.1\Vivado\bin\vivado.bat"
```

默认 `-Mode All` 先跑 XSim 功能自检，再以 **3.333333ns / 300MHz** 对当前 `SpinorVpu` 重新综合、布局、phys_opt 与布线。没有旧 DCP 恢复入口。两个功能 TB 分别检查整数扩展和公开接口的访存、FP/整数计算、归约、mask、扩展与并发 monitor。

分步运行可在上述命令末尾加 `-Mode Rtl` 或 `-Mode Implement`。后者全新实现，不读取前一个功能仿真的结果。`-Threads 4` 可调线程数；可独立用 `-PeriodNs 2.000000` 做 500MHz 实验。

结束后上传脚本打印的 `spinor_results_M31_*.zip`。即使失败，也会保留已产生的文件并尽量打包。包括输入/输出散列、Vivado/XSim 日志、嵌套 `.wdb` 波形、setup/hold 路径、资源报告、匹配的 routed DCP/EDIF 与 DSP 配置/延迟。`.wdb` 可通过 Vivado 打开；只记录测试台时钟、复位、周期和 DUT 顶层端口。

## 如何解读

功能 TB 使用约 10ns 的抽象 tick 并留出驱动稳定时间；更改实现周期不会使 RTL 仿真检测出长组合路径。云端按原样重放打包 TB 使用的是 Icarus。本地 XSim/Vivado 尚未执行；本包不跑 post-route SDF 仿真，也不生成上板 `.bit`。

是否满足时序请检查 `timing_routed.rpt` 的 setup/hold、约束覆盖，以及 `route_status.rpt`；同时上传 `setup_paths.rpt`、`hold_paths.rpt` 和 `run-summary.txt`。流程正常退出或单个正 setup slack 不足以证明完整时序。此次 OOC 未指定宿主 IO delay 和 `HD.CLK_SRC`，不能代替实际 SoC/板级时钟与接口约束。

云端固定参考门槛为公开顶层 3.277ns、计算/访存 3.141ns，仍使用原 M25 权重及 100ps/段假设，DSP 相关端点排除；尚无 ZU15EG-2 布局布线与速度档校准。物理 300/500MHz 状态均未知。

## 云端复现

```sh
make bootstrap
python3 scripts/verify_m31.py
python3 scripts/package.py --milestone m31
```

Windows 编排检查额外使用散列固定的 Linux PowerShell 7.5.4，脚本为 `scripts/bootstrap_powershell.py`。Tcl 用 mock 覆盖正常流程及失败分支，PowerShell 实际解析并通过假 launcher 检查路径空格、参数、输入篡改、退出码和嵌套 ZIP。该部分不是 Windows 5.1 / XSim / Vivado 执行证据。
