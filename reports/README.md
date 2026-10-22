# 验证报告

- [M61](m61/evaluation.md)：当前寄存隔离顶层的硬件验证。
- [源码整理](repository-layout/evaluation.md)：56个Scala文件整理、8个顶层RTL一致性，记录对应提交`63de85e`。
- [产物精简](retention/evaluation.md)：日志摘要、压缩receipt和原始文件恢复检查。
- [保留规则与恢复命令](../docs/artifacts.md)。

历史`m*/evaluation.md`描述当时的输入与结论。较大的`receipt.json`现在只保留索引，完整原文为同目录`receipt.json.gz`；索引明确标记格式和原始SHA256。最新小型receipt继续保留原文。不要把旧报告或索引中的状态当作当前代码新执行的结果。
