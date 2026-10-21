# 当前进度：M61

新增可选寄存隔离顶层 `SpinorIsolated`，原直接提交协议保留。隔离配置启用LSU分级和整数操作数分级；四种旧直接配置重新生成的RTL与已验收版本逐字节相同。

- [隔离顶层接入](docs/m61-isolation.md)：输入/总线寄存化、preview/grant/done、停止和上下文迁移。
- [M61报告](reports/m61/evaluation.md)：四配置数值/访存定向回归、完整映射网表组合隔离与条件预算。
- [通用接入](docs/integration.md)、[文档导航](docs/README.md)、[验证说明](docs/validation.md)。

CPU在offer前完成本地队头/排空资格检查，preview不是完成；grant授权后保持不可撤销owner，直到done.fire。错误身份封锁，不通过缓冲提前消费核心完成。外部payload先采样再比较，RAM和monitor A/D各自经过非直通寄存切片；仍只支持同一时钟域。

仍为VLEN128/ELEN64、单lane、单指令在途和版本化RAM。M60全部330算术编码的重启分类及历史访存证据保持；未声明完整V/RVA23/Zvkt或真实CPU/Linux集成。当前实际300MHz仍需Vivado器件结果，组合隔离和云端条件预算不能替代布局布线签核。

当前验收入口：`python3 scripts/verify_m61.py`，`--check-only`核对精确输入与压缩证据。历史文档及M50至M60证据通过`python3 scripts/check_docs.py --evidence`按快照核对，不改写旧报告。
