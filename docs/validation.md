# 验证、证据与时序

## 当前功能证据

最新功能轮次为M60，标准/Deep公共端口合计726,000条命令通过，覆盖全部330种算术编码的重启分类。参考变换、独立Python/SoftFloat校准、29次错误注入及边界见[完整报告](../reports/m60/evaluation.md)。这不等同于完整ISA/架构套件认证；[ACT4接入](act4-intake.md)目前还未生成或运行官方ELF。

本次整理只更新文档与文档审计入口，未改硬件、参考语义、功能测试或旧receipt。M60及更早报告保留原文，其文档输入由精确快照解析；不会把新介绍写回旧报告来改动历史证据。

## 文档检查

在仓库根目录运行，无需下载构建工具：

```bash
python3 scripts/check_docs.py
```

检查当前入口文档的本地文件链接、整理前文档快照和M60硬件源文件哈希。它不重新执行功能仿真。

在保留完整历史工具/build产物的工作区，还可检查M50至M60证据绑定：

```bash
python3 scripts/check_docs.py --evidence
```

仅对明确冻结的文档使用快照解析，其他源码、工具和测试产物必须按原精确SHA匹配；缺失产物会失败。新clone通常不含这些build/tools文件，应先使用不带`--evidence`的文档检查。

## 功能复现

M60的原始入口为：

```bash
python3 scripts/verify_m60.py
python3 scripts/verify_m60.py --check-only
```

这两个命令对应提交`0790a6e`的精确输入，须在匹配checkout和固定工具/build环境运行。文档整理后的目录请使用上面的文档审计入口核对保留证据；不要把旧入口的文档哈希变化误判为硬件变更，也不要覆盖原receipt来绕过检查。

新接入的联调步骤见[接入指南](integration.md)。已有仿真使用独立宿主/内存模型，不能替代真实CPU退休、VS/FS、Linux驱动、MMU/PMP和缓存一致性验收。

## 资源与300 MHz目标

默认host FCSR配置的历史Yosys xcup结果为24,247逻辑LUT、13,882 FF、9 DSP，详见[M56报告](../reports/m56/evaluation.md)。配置、生成输入或映射流程变化后需要重新评估，其他预设不能直接套用这一数字。

当前云端宿主公共/计算顶层沿用3.300ns条件预算；独立标准/Deep沿用3.292/3.232ns。条件模型排除DSP影响端点与主IO，不含真实器件布局布线、时钟树和ZU15EG-2校准，不能作为STA/SDF或实际频率通过证明。

[M53本地结果](../reports/local-m53-resume/evaluation.md)为旧RTL的300MHz OOC setup +0.090ns、hold +0.042ns，仅对该输入有效。当前RTL和真实SoC仍需Vivado完整约束及实现：明确时钟、IO/宿主侧带、时钟域和例外，检查setup、hold、未约束路径与方法学报告，再生成bitstream。

[实际DSP表与配置限制](../reports/dsp-m53/evaluation.md)单独保留。不要将功能仿真耗时、云端条件预算或旧版本通过结果当作当前器件Fmax。
