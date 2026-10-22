# 日志与验证产物保留规则

Git 的当前目录保留源码、人工可读的验证结论、小型结果表、必要参考数据，以及压缩的原始 receipt。运行过程的大量日志、波形和展开网表放在 `build/`；默认由 `.gitignore` 排除。

## 当前保存方式

- `reports/m*/evaluation.md`：该版本的结论、验证范围和限制。
- 小型 `receipt.json`：保留完整原文；大型版本改为明确标记的索引，完整原文在同目录 `receipt.json.gz`。
- [日志摘要](../reports/retention/log-summary.json)：89份旧日志的行数、诊断节选和结尾。节选不代表完整的告警清单，也不产生新的PASS结论。
- [保留清单](../reports/retention/manifest.json)：原路径、长度、SHA256、Git blob及压缩副本的位置。
- 历史源码、规格和本地Vivado报告仍保留。重复receipt、展开网表和旧路径明细从当前目录移除，可从固定Git对象恢复。

大型receipt索引的`original_status`仅引用旧报告。它不包含原来的完整输入/产物字段；需要程序读取原始记录时使用`maintenance.retention.read_receipt`，或解压完整副本。当前`make audit-evidence`已适配。

## 检查与恢复

```bash
make check             # 检查索引、压缩副本、目录、注释和链接
make audit-retention   # 检查全部保留原文的长度与SHA256
make audit-evidence    # 原M50–M61证据审计，还需要保留的tools/build

# 提取一个旧日志；输出文件必须尚不存在。
python3 scripts/retained_artifacts.py --extract archive/m1/reports/mill-generate.log --out /tmp/spinor-old-mill.log

# 提取一份完整原始receipt，不覆盖当前的精简索引。
python3 scripts/retained_artifacts.py --extract reports/m55/receipt.json --out /tmp/spinor-m55-receipt.json
```

压缩receipt随当前仓库提供。旧日志、展开网表等原始Git对象属于清理前提交`63de85e`；普通完整clone可直接读取。浅克隆或源码ZIP不一定包含这些对象，此时需要获取该提交或使用完整clone。恢复工具不会自动联网、重置工作区或覆盖已有文件。

历史里程碑脚本仍应在对应源码提交中复现；它们可能直接读取当时的展开文件。当前文件精简不会把这些旧脚本升级成当前全功能入口。

## 后续提交约定

每轮提交优先保存一份结论、配置/工具版本、必要统计及输入/产物哈希。完整日志留在`build/`；失败时在报告中保留关键错误和定位信息。确有必要保存完整诊断时，使用明确命名的压缩文件，并在报告中说明用途。

不要重复复制整份历史receipt、把生成网表提交进源码目录，或将摘要当作完整原始证据。此次只精简当前文件树，没有重写Git历史；普通完整clone仍会保留过去的对象，`.git`大小不会按目录缩减比例下降。
