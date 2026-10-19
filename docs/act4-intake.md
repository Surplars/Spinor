# ACT4架构测试接入条件（M60）

已检查并固定官方[riscv-arch-test](https://github.com/riscv-non-isa/riscv-arch-test/tree/51c0ed49294c5797a59d0203517b14e1f5fe9656)
提交`51c0ed49294c5797a59d0203517b14e1f5fe9656`（2026-10-19）。
[原始README](references/m60-act-README.md)和完整递归目录快照按SHA256冻结，
见[来源锁定](references/m60-act-sources.json)。没有执行README中的安装脚本。

当前官方框架是ACT4，已替代弃用的RISCOF。它按UDB配置选择测试，使用配置一致的
Sail模型生成期望，编译成自检ELF；用户仍须在自己的DUT测试平台上运行这些ELF。
官方README说明当前参考模型为Sail 0.16，工具链验证版本包括LLVM/Clang22；
本工作区沿用Clang19.1.7，没有把它冒充当前官方验证版本。

| 接入项 | Spinor已有 | 仍需落实 |
|---|---|---|
| 向量目标 | VLEN128/ELEN64、RV64宿主约定、基础V/Zvfhmin/Zvbb实现 | 生成与Sail一致的UDB配置；Zvkt保持未认证状态 |
| 向量执行 | 公共命令/Completion、上下文、CSR和TileLink RAM检查器 | ELF标量执行到向量命令的实时桥接，不能用预先录好的执行轨迹代替 |
| 标量/特权 | 现有编译器内核使用有界标量测试适配器 | ACT4要求的标量控制流、trap、VS/FS与宿主状态适配；不放入VPU硬件 |
| 平台钩子 | 程序回归有现有链接布局与RAM | ACT4用的rvmodel_macros.h、pass/fail/console退出约定与匹配链接脚本 |
| 参考/工具 | 已有Spike、SoftFloat、Clang19 | Sail0.16、Ruby/UDB及选定工具链的固定安装；本工作区未发现Ruby/Sail可执行文件 |
| 覆盖 | 当前Spike/SoftFloat/Python有界矩阵 | 运行实际生成的ELF并收集相应官方规范覆盖，不把目录项统计当作测试通过 |

当前状态为**接入条件清点完成，ACT4 ELF生成0个、执行0个**。
`scripts/m60_act_intake.py`检查冻结来源和条件，输出机器可读目标/执行器契约，
不会生成看似可用、但未经UDB/Sail验证的配置文件。

接下来先完成独立于Orbital的ELF测试宿主桥接和最小向量ELF试运行，再固定UDB、
Sail和平台宏生成配置，逐扩展运行ACT4。真实Orbital退休、页表/PMP和一致性验收
仍单列，不为跑测试在VPU内复制CPU。官方也明确ACT不能替代更广泛的设计验证。
