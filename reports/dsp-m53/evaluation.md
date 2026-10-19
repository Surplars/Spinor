# M53 DSP 原始数据：已导入的配置参考与适用范围

收到原始 `dsp_delay.zip`，7 个文件、611 行数据，与本次恢复报告的实例名、逐文件
计数和配置属性全部对应。CRC/散列、行格式、重复引脚、有限数值和配置均核验通过。
完整数据保留，另生成 [reference.json](reference.json) 和 [arcs.csv](arcs.csv)，可供
后续云端工具读取，不需要再次本地运行 Vivado。

## 数据内容

| 配置 | 实例数 | AREG/BREG/MREG/PREG | 每实例 clk→out 行 | 每实例 input→seq 行 |
|---|---:|---|---:|---:|
| 整数乘法 | 1 | 0/0/0/1 | 32 | 33 |
| 浮点部分积 | 6 | 2/2/0/1 | 43 | 48 |

全体为 290 行 clk→out、321 行 input→sequential，没有 input→output 组合弧。
6 份浮点表在全部导出属性和数值上完全相同，按配置去重后保留 156 个记录；原始
7 份文件和散列仍各自保留。这里只能说在本次导出的 0.01ns 精度下相同。

clk→out 导出值为 0.25–0.34ns。整数乘法 A/B 输入到内部寄存器的导出数据延迟
约为 1.40–1.45ns，另有 CEP 控制行；浮点 AREG/BREG 已启用，输入引脚到首级内部
寄存器的数据延迟导出为 0，第四列另列 setup。这不是“浮点乘法无延迟”。

第四列是有符号 **setup**，不是 hold；整数表出现的 -0.01ns 不得取绝对值或当作
负数据延迟。所有数值按 ns 保存，原文件由上游 `%7.2f` 输出，不能当作皮秒级精度。

## 为什么尚不能直接替换云端 DSP 预算

当前同一 RTL 的 Yosys 映射有 9 个 DSP，全部 AREG/BREG/MREG/PREG=0/0/0/0。
Vivado 映射为 7 个 DSP，全部 PREG=1，其中 6 个还启用 AREG/BREG=2。寄存器吸收和
乘法拆分不同。因此 **0/9 个当前 Yosys DSP 与这份表的寄存器配置相符**。
直接套用 clk→out 值，或以不存在的组合弧填零，会把组合乘法的关键延迟隐藏掉。

当前固定云端预算保持原权重和 DSP 端点排除规则，没有声称 DSP 全路径已校准。
本轮新增的是经过核验、可读的实际配置参考库，以及明确的不兼容判定。

上游导出器以 `report_timing -delay_type max` 查找活动端口路径。PREG=1 的结果不能
补足 PREG=0 的组合弧；对浮点配置，端口 input→seq 在 AREG/BREG 停止，clk→out
从 PREG 开始，也没有完整列出 AREG/BREG→PREG 等 DSP 内部寄存器之间的级间路径。
最差 50 条 setup 报告未包含 DSP 路径，不能用它们补齐此缺口。

另据导出器实现，clk→out 返回输出 pin 的累计 arrival，未独立去嵌时钟到达项；
不能把它自动视作独立纯 cell C-to-Q。表也不含独立 min/hold 和完备、分角落标注的
数据库。这些限制记录在 reference.json，后续读取者必须保留。

下一步若扩展 DSP 图估算，需要先使开源映射的寄存器拓扑与样本相符，或实现按流水
配置拆分的模型，再补内部级间/组合弧和相应路径验证。不能只按 DSP 数量查一个常数。
这不影响已收到的 **标准 SpinorVpu 在 ZU15EG-2 内部 OOC 300MHz setup/hold 通过**
结果：+0.090 / +0.042ns；它仍不是 SoC 外部 IO/实际时钟位置或 500MHz 签核。

## 证据与复现

原包：[input-dsp-delay.zip](input-dsp-delay.zip)。来源记录：
[恢复运行报告](../local-m53-resume/evaluation.md)，包含本地 checkpoint 指纹及实际
导出器版本。原 DSP ZIP 没有额外签名/散列 manifest；与恢复报告的关联由上传上下文、
文件名、记录计数及全部已记录配置交叉核对，不宣称独立 DCP 重放证明。

```bash
python3 scripts/analyze_m53_resume.py
python3 scripts/import_m53_dsp.py
python3 scripts/verify_m53.py --check-only
```

导入程序检查 raw ZIP 后输出机器可读参考、CSV 和 [receipt.json](receipt.json)，
同时记录当前 Yosys 9 个 DSP 的配置以及输入/源码/产物散列。
