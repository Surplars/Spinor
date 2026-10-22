# 工具入口

日常使用从根目录 `make help` 开始。以下命令区分当前生成、目录维护和历史验证，避免误跑旧版本脚本覆盖保留产物。

| 工作 | 当前入口 |
|---|---|
| 安装固定工具 | `make bootstrap` / [bootstrap.py](bootstrap.py) |
| 编译Chisel | `make compile` |
| 生成直接/隔离顶层 | `make rtl-direct` / `make rtl-isolated`，支持 `PRESET`、`FCSR_OWNER`、`RTL_OUT` |
| 目录、注释、链接检查 | `make check` / [check_repository.py](check_repository.py) |
| 本次整理的RTL对照 | `make check-rtl`，需保留的M61参考产物 |
| 历史证据审计 | `make audit-evidence`，需原工具和build产物 |
| 旧文档检查命令 | [check_docs.py](check_docs.py)，转入当前维护检查 |

[maintenance/](maintenance/) 保存目录映射、Scala注释/token检查和历史输入解析。[legacy.mk](legacy.mk) 保存原Makefile的里程碑配方，显式使用 `make -f scripts/legacy.mk <target>`，并准备对应版本的源码与工具。

`verify_m*.py`、`report_m*.py`、`m*_baseline.py`、`m*_evidence.py` 和按里程碑命名的打包脚本属于相应快照。文件中的旧源码路径可能是报告的原始键，不能批量改写。需要原样复现M61时使用提交 `f8df80e` 和匹配产物；当前整理通过8个完整生成顶层与该版本逐字节比较。

`prove_*.py`、`emit_gsim*.py` 和通用综合/测试工具已经适配递归源码布局，但其中一些仍写入历史固定输出目录。复现前查看脚本的输出位置，使用单独工作区保留原验收产物。Windows打包器名称中的 `current` 仍可能固定旧里程碑，以脚本检查的receipt和RTL版本为准。
