# 验证、证据与时序

## 当前功能证据

最新接口优化为M61，验证寄存隔离顶层的数值、授权/取消、访存排空和网表组合隔离，见[M61报告](../reports/m61/evaluation.md)。49个原Scala文件不变，5个增加默认关闭的可选分级；四种旧直接配置RTL逐字节保持。M60标准/Deep的726,000条算术重启分类证据保持，[原报告](../reports/m60/evaluation.md)记录范围。这不等同于完整ISA/架构套件认证；[ACT4接入](act4-intake.md)尚未生成或运行官方ELF。

先前文档整理和M60及更早报告保留原文，其文档输入由精确快照解析；M61新增隔离顶层、可选核心分级及对应验证，没有改写旧receipt。

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

当前隔离顶层：

```bash
python3 scripts/verify_m61.py
python3 scripts/verify_m61.py --check-only
```

完整重跑需要固定工具与保留的M60参考语料；生成/映射中间文件使用`/tmp/spinor-m61`，精确输入和网表压缩保存在`build/m61`，当前check-only不要求临时目录仍存在。

M60的原始入口为：

```bash
python3 scripts/verify_m60.py
python3 scripts/verify_m60.py --check-only
```

这两个命令对应提交`0790a6e`的精确输入，须在匹配checkout和固定工具/build环境运行。文档整理后的目录请使用上面的文档审计入口核对保留证据；不要把旧入口的文档哈希变化误判为硬件变更，也不要覆盖原receipt来绕过检查。

新接入的联调步骤见[接入指南](integration.md)。已有仿真使用独立宿主/内存模型，不能替代真实CPU退休、VS/FS、Linux驱动、MMU/PMP和缓存一致性验收。

## 资源与300 MHz目标

默认host FCSR配置的历史Yosys xcup结果为24,247逻辑LUT、13,882 FF、9 DSP，详见[M56报告](../reports/m56/evaluation.md)。配置、生成输入或映射流程变化后需要重新评估，其他预设不能直接套用这一数字。

M61隔离顶层的标准host、Deep host、标准standalone条件预算为3.300ns，integer-deep为3.277ns，详见[M61报告](../reports/m61/evaluation.md)。保留的直接顶层历史预算与资源见M56。条件模型采用固定100ps/link假设，排除DSP影响端点与主IO，不含真实器件布局布线、时钟树和ZU15EG-2校准，不能作为STA/SDF或实际频率通过证明。

[M53本地结果](../reports/local-m53-resume/evaluation.md)为旧RTL的300MHz OOC setup +0.090ns、hold +0.042ns，仅对该输入有效。当前RTL和真实SoC仍需Vivado完整约束及实现：明确时钟、IO/宿主侧带、时钟域和例外，检查setup、hold、未约束路径与方法学报告，再生成bitstream。

[实际DSP表与配置限制](../reports/dsp-m53/evaluation.md)单独保留。不要将功能仿真耗时、云端条件预算或旧版本通过结果当作当前器件Fmax。
