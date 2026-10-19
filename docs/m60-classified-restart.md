# M60：全部算术编码的重启分类

标准/Deep各通过363,000条公共端口命令，共726,000条。
330种编码全部有合法样本；307种在非零vstart下产生可见RF或标量结果，
另外23种按归约、prefix、compress等限制拒绝非零起点。
每预设72,600个目标中50,914合法、21,686拒绝；40,072个非零起点合法。

参考按语义分类，未修改Spike，也没有直接让Spike执行非零算术vstart：

- 268种普通maskable编码：v0只作执行谓词，清除起点之前的mask位再从零执行；
  不将这一变换套到v0数据、归约或特殊搬运。
- 31种carry/borrow/merge、broadcast和mask逻辑：原始v0保持为数据，
  使用无flags计算结果并独立恢复目标前缀。
- 23种非零起点限制：拒绝并保持RF/flags/vstart。
- 四种whole move：独立Python按EVL和源快照执行，与起点0 Spike结果交叉核对。
- 两种scalar read和两种scalar insert：按专门规范处理，单独核对返回值、
  sign extension/NaN boxing、VL和vstart条件。

在M59独立Python/SoftFloat模型支持的26种操作上，再次校准5,720个新场景通过。
所有实际DUT命令完整比较32个向量寄存器、CSR和Completion身份。
24次运行比较器错误注入及5次语义负控制全部检出。

检查了430,822个普通prestart元素保持；88个VL=0的whole move仍拷贝有效后缀，
62个VL=0的scalar read仍返回结果，114个非零起点scalar insert仍写元素0。
这些是单份语料计数，两种DUT均执行通过，不重复相加。

本轮两种布局包含选定同宽/比较指令原地操作；宽窄和gather/slideup保持分离，
更多类型重叠沿用M59。五种profile与策略/舍入模式循环，不是所有编码/布局/数据的穷举。
结果表中的“有可见效果”检查RF变化或标量返回，不把仅有计算范围称为活动结果。

[ACT4接入清单](act4-intake.md)固定官方仓库版本和机器目标契约；本轮没有生成或运行
官方ACT4 ELF，仍不声明完整V/RVA23/Zvkt。下一步推进独立ELF测试宿主桥接与官方套件。

54个Scala文件精确不变，没有新增指令或资源。沿用3.300ns云端条件预算，
当前RTL实际300MHz仍需Vivado器件结果；没有把旧M53时序移作当前签核。

[完整报告](../reports/m60/evaluation.md)、[逐编码分类/覆盖](../reports/m60/restart-coverage.csv)、
[规范引文与负控制](../reports/m60/semantic-clauses.json)。
入口：`python3 scripts/verify_m60.py`，`--check-only`核对精确证据。
