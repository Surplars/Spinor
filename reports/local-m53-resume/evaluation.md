# M53：Windows/Vivado 恢复运行完成

用户回传的 M53_Resume_20261019_151042_926 精简报告包表明，fix1 在实际 Windows /
Vivado 2025.1 完整执行到 `DONE: M53 routed reports`，没有 flow/launch/DSP 导出错误。
先前收尾脚本的问题已修复。本次从原 routed checkpoint 读入，只生成报告和 DSP
表，没有再次综合、布局布线、物理优化或改变时钟约束。

## 时序和物理证据

setup **+0.090ns**、hold **+0.042ns**、pulse width **+1.124ns**；各类失败端点为 0。
周期保持 3.333ns，26,029 条可布线网络全部完成，路由错误为 0。完整 timing 表、
check_timing 覆盖和路由统计均与 [首轮物理结果](../local-m53/evaluation.md) 一致。
标准版资源仍为 18,085 LUT、12,490 FF、2 BRAM36、7 DSP。

校验上传 ZIP 的 CRC、输出 SHA256、fix1 输入 manifest，以及原 run-inputs 文件
散列和完整 prior_run_inputs。记录的本地 DCP SHA256 为：
`330b78b511f338e4cfab3bd4840379f1a078cfc3c21c1fe6384ba15dd991a138`。
DCP 本身没有上传，因此此项是本地记录的文件指纹，并非云端对 DCP 的独立重算。
恢复后的 Vivado design 名为 `checkpoint_routed`，公共端口、part 和时钟检查通过。

300MHz 结论仍限于标准顶层的内部 OOC 约束。外部 613 个输入、608 个输出没有 IO
delay，HD.CLK_SRC 未指定；未做 SoC/板级时钟、接口、其他预设、500MHz 或 SDF 签核。

## DSP 导出

7 个 DSP 均通过本地非空检查，导出统计为 **611 行**：整数乘法 65 行，6 个浮点
部分积各 91 行。`dsp-configurations.txt` 记录两类不同配置：

| 实例类 | 个数 | AREG | BREG | MREG | PREG |
|---|---:|---:|---:|---:|---:|
| 整数乘法 product_reg | 1 | 0 | 0 | 0 | 1 |
| 浮点 partials_p* | 6 | 2 | 2 | 0 | 1 |

均为 USE_MULT=MULTIPLY、USE_SIMD=ONE48。6 个浮点实例的完整已记录配置相同；这
只证明这些配置属性一致，不证明每个实例的数据路径或导出 arc 数值必然相同。

本精简报告包不含 `dsp_delay/*.txt` 原始表。日志/coverage 证明本地导出达到非空检查，
不能据此在云端复算 arc、验证所有端点/模式/角落覆盖或修改云端 DSP 校准。不会把
`NONEMPTY_FILES_ARC_COMPLETENESS_UNVERIFIED` 升格成完整 arc 验证通过。

随后用户单独上传了原始 `dsp_delay.zip`。其 7 个文件、611 行记录、全部已记录配置
均已与本报告核对，已生成引脚级参考库，见 [DSP 原始数据审计](../dsp-m53/evaluation.md)。
不需要为本次数据再运行 Vivado。样本与当前 Yosys DSP 寄存器拓扑不匹配，仍不能直接
替换现有云端预算或宣称完整 DSP 时序签核；详细限制保留在独立数据审计中。

原包保留为 [input-reports.zip](input-reports.zip)，核验结果在 [receipt.json](receipt.json)。
云端复核入口为 `python3 scripts/analyze_m53_resume.py`；该脚本核验实际上传数据，
不执行其中内容或重跑器件实现。
