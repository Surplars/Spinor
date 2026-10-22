# 验证入口与参考模型

当前硬件功能证据为[M61报告](../reports/m61/evaluation.md)。本次目录和注释整理的验证为[源码布局报告](../reports/repository-layout/evaluation.md)：源码token保持、8个生成顶层逐字节相同、历史证据精确解析。

| 文件类别 | 用途 |
|---|---|
| `test_repository_checks.py` | 目录维护检查器的负控制：注释、字符串、运算符变化和漏注释声明 |
| `test_*lane.py`、`test_ram_vector.py` 等 | 执行单元与向量核心公共端口测试 |
| `test_*memory*.py`、`test_*engine.py` | 访存协议、故障、停止与恢复测试 |
| `reference_*.py`、`*_reference.c` | 数值参考实现与SoftFloat桥接 |
| `test_spike_*.py` | Spike参考适配和语料构造 |
| `test_m*.py`、`m*_driver.cc` | 指定里程碑的矩阵、真实端口驱动与回归 |
| `test_evidence_reuse*.py` | 历史证据复用规则的合成负控制；其中旧路径是测试数据 |

日常维护运行 `make check`。完整功能测试需要所选里程碑的固定工具、参考语料与生成RTL；详见[验证说明](../docs/validation.md)。`tests/`含独立可执行脚本和构建驱动，不是可直接统一运行的pytest目录。

新增测试应写明被测顶层、参考来源、输入范围、输出目录及检查的失效情形。修改辅助路径时保留原参考数值，避免把DUT输出反填为期望值。现有里程碑产物使用原报告解释，不将目录整理计作新增功能覆盖。
