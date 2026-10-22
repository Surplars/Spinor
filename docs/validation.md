# 验证、证据与时序

## 当前功能证据

最新接口优化为M61，验证寄存隔离顶层的数值、授权/取消、访存排空和网表组合隔离，见[M61报告](../reports/m61/evaluation.md)。49个原Scala文件不变，5个增加默认关闭的可选分级；四种旧直接配置RTL逐字节保持。M60标准/Deep的726,000条算术重启分类证据保持，[原报告](../reports/m60/evaluation.md)记录范围。这不等同于完整ISA/架构套件认证；[ACT4接入](act4-intake.md)尚未生成或运行官方ELF。

先前文档整理和M60及更早报告保留原文，其文档输入由精确快照解析；M61新增隔离顶层、可选核心分级及对应验证，没有改写旧receipt。

## 当前目录与注释检查

```bash
make check
make compile
```

新clone可直接运行`make check`；`make compile`需要先按[构建说明](repository.md)准备工具。`make check`核对源码布局、声明注释、长代码块、文档链接和维护检查器的负控制。目录规则见[开发规范](development.md)。兼容入口`python3 scripts/check_docs.py`仅执行布局、注释和链接检查。

本次整理的完整验收：

```bash
python3 scripts/check_repository.py --rtl --evidence
```

`--rtl`比较全部56个Scala文件的代码token，并在`/tmp/spinor-source-layout`重新生成8个直接/隔离顶层，与已验收M61的压缩SV逐字节比较。它需要Mill工具和保留的M61参考产物；不覆盖旧build目录。结果见[整理报告](../reports/repository-layout/evaluation.md)。这项固定基线比较用于本次维护，不代替后续有意硬件变更的功能测试。

`--evidence`（也可用`make audit-evidence`）核对保留的M50–M61原始输入和产物SHA。旧路径通过已有档案或`archive/m61/layout-baseline.zip`解析，旧receipt不改写。完整审计需要原tools/build环境，源码clone本身不包含全部仿真模型、网表或工具二进制。

## 功能复现

原M61入口为`python3 scripts/verify_m61.py`，对应提交`f8df80e`及匹配工具/build环境；原M60入口对应`0790a6e`。在独立checkout中复现相应版本，不要将旧版本的固定源码路径/散列断言当成当前目录检查。通用测试的实际源码文件路径和递归扫描已适配新目录；参考数值与验证逻辑保留。

M61原记录包括47,250条隔离顶层接收命令、24次负控制和四配置映射网表组合隔离。此次只整理目录与注释，通过8个完整生成顶层逐字节相同连接到原硬件证据，没有将旧仿真重记为新运行。

新接入的联调步骤见[接入指南](integration.md)。已有仿真使用独立宿主/内存模型，不能替代真实CPU退休、VS/FS、Linux驱动、MMU/PMP和缓存一致性验收。

## 资源与300 MHz目标

默认host FCSR配置的历史Yosys xcup结果为24,247逻辑LUT、13,882 FF、9 DSP，详见[M56报告](../reports/m56/evaluation.md)。配置、生成输入或映射流程变化后需要重新评估，其他预设不能直接套用这一数字。

M61隔离顶层的标准host、Deep host、标准standalone条件预算为3.300ns，integer-deep为3.277ns，详见[M61报告](../reports/m61/evaluation.md)。保留的直接顶层历史预算与资源见M56。条件模型采用固定100ps/link假设，排除DSP影响端点与主IO，不含真实器件布局布线、时钟树和ZU15EG-2校准，不能作为STA/SDF或实际频率通过证明。

[M53本地结果](../reports/local-m53-resume/evaluation.md)为旧RTL的300MHz OOC setup +0.090ns、hold +0.042ns，仅对该输入有效。当前RTL和真实SoC仍需Vivado完整约束及实现：明确时钟、IO/宿主侧带、时钟域和例外，检查setup、hold、未约束路径与方法学报告，再生成bitstream。

[实际DSP表与配置限制](../reports/dsp-m53/evaluation.md)单独保留。不要将功能仿真耗时、云端条件预算或旧版本通过结果当作当前器件Fmax。
