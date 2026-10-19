# M60：全部330种算术编码的重启分类与ACT4接入清点

标准/Deep分别通过363,000条新命令，合计 **726,000条**。
每条在实际GSim公共命令、Completion、上下文和CSR端口执行并比较全部32个向量寄存器；
包括完成身份、延迟接收和提前发布检查。24次运行比较器错误注入及5次独立语义负控制全部检出。
本轮没有发现需要修复的硬件问题，54个Scala文件精确不变，没有新增指令、DSP或RAM。

## 参考方法

固定Spike本身仍在vstart=0运行，没有修改其拒绝非零算术起点的策略。
按官方目录和语义分类，明确区分以下参考方法；不是原指令/原状态的直接Spike重启差分。

| 参考分类 | 编码数 | 非零起点期望来源 |
|---|---:|---|
| execution-mask | 268 | v0只作执行谓词；参考清除起点之前的predicate位，必要时将vm=1转成vm=0，恢复不作数据源的原v0 |
| flagless-prefix | 31 | carry/borrow/merge、broadcast和mask逻辑使用原始v0数据；Spike从零计算，独立恢复目标前缀，仅用于不产生flags的形式 |
| nonzero-reject | 23 | 归约、mask scalar/prefix、viota、compress按非零vstart限制拒绝；保持原RF/flags/vstart |
| whole-evl | 4 | Python按NREG、SEW、EVL和源快照直接拷贝；起点0结果另与Spike核对，忽略VL/LMUL |
| scalar-read-exception | 2 | scalar read即使VL=0或vstart≥VL仍返回元素0，另用位运算检查sign extension/NaN boxing |
| scalar-write-exception | 2 | scalar insert只在vstart<VL时写元素0，按其专门定义处理，不能套普通prestart保持规则 |

执行掩码变换不用于carry/merge的v0数据、归约、prefix、whole或scalar例外。
只选择v0不作普通源/目标的布局；masked/unmasked和TA/MA参考使用实际profile配置。
固定Spike和Spinor当前都选择允许的undisturbed策略；不意味着所有实现须作相同选择。
在M59已建立的独立Python/SoftFloat模型支持的26种操作上，
**5,720个新场景再次逐RF/flags/vxsat/vstart/非法状态校准参考变换通过**。
没有从DUT输出生成期望，也没有重放DUT执行轨迹。

## 数值矩阵

330编码×22种基础合法vtype×2种布局×5种profile = **72,600个目标/预设**。
每目标含vtype/vcsr/FCSR/vstart四条初始化及目标指令，共363,000条命令/预设。
布局包括分离与选定同宽/比较指令原地操作；宽窄、扩展、gather/slideup保持分离，
其更广的类型重叠沿用M59证据，并未声称所有330编码都有全部重叠布局。

| SEW | 目标 | 合法 | 拒绝 | 非零起点合法 | 非零起点有可见RF/标量结果 |
|---|---:|---:|---:|---:|---:|
| 8 | 23,100 | 14,208 | 8,892 | 11,176 | 4,793 |
| 16 | 19,800 | 12,644 | 7,156 | 9,952 | 4,137 |
| 32 | 16,500 | 14,710 | 1,790 | 11,584 | 4,678 |
| 64 | 13,200 | 9,352 | 3,848 | 7,360 | 2,888 |
| 合计 | 72,600 | 50,914 | 21,686 | 40,072 | 16,496 |

全部330种编码均有合法数值样本；307种在非零起点下有可见结果样本，23种拒绝非零起点。
每种操作不支持的SEW/EMUL仍应拒绝，不能把全部目标都称为有效运算。
[逐编码参考类别及结果数](restart-coverage.csv)。所有统计按单份语料，不把两个DUT重复相加。

五种profile是起点0满VL、起点1满VL、起点2带mask、起点127全mask关、起点1且VL=0。
四种vta/vma、五种合法frm、四种vxrm随profile/编码循环；不是所有策略/起点/数据的穷举。
数据包含非零整数边界、sNaN/subnormal、FP标量NaN-box边界；1,755目标改变fflags，
691目标改变vxsat。40072个非零合法目标中的无可见结果样本仍比较完整状态。

独立谓词对发出的完整期望流检查430,822个普通prestart元素和21,686个拒绝状态保持。
**88个VL=0的whole move仍改变RF，62个VL=0的scalar read仍返回结果，
114个非零起点scalar insert仍写元素0**，覆盖通常容易被普通循环规则误处理的例外。
whole计数包含非零起点，88个均为profile4；scalar例外按专门规范逐字引文检查。
五类语义负控制分别破坏prestart、非法vstart、whole-VL0、scalar-read-VL0和scalar-insert行为，
均被独立谓词检出。[条款引文/行号及计数](semantic-clauses.json)。

## ACT4与时序

固定官方riscv-arch-test提交51c0ed49294c5797a59d0203517b14e1f5fe9656，
冻结README和完整目录，核对ACT4/UDB/Sail/ELF要求并记录机器可读接入契约。
本轮ACT4 ELF生成0个、运行0个；不把接入条件检查称为官方测试通过。
缺少Ruby/Sail运行环境、UDB/参考配置和完整ELF测试宿主桥接，当前Clang19也不是
上游README当前验证的Clang22。详见[接入清单](../../docs/act4-intake.md)与[机器契约](act4-intake.json)。
现有有界编译器内核标量适配器不是完整ACT4执行器，未修改Orbital/Valence或在VPU内复制CPU。

54个RTL源文件精确不变，沿用M56宿主公共/计算顶层3.300ns条件预算，
独立标准/Deep沿用M55的3.292/3.232ns。没有重综合或新增器件时序结果。
条件模型排除DSP影响端点和主IO，不含器件布局布线/真实时钟、未按ZU15EG-2校准，
不是STA/SDF，**当前实际300MHz仍未知**。M53旧RTL本地通过不移作当前签核。

仍不声明完整V/RVA23/Zvkt；375基础V+16Zvbb目录及310访存形式历史结论保持。
后续聚焦真实ELF架构测试宿主、更多访存异常/恢复条款、Zvkt覆盖义务和当前器件时序。

```bash
python3 scripts/verify_m60.py
python3 scripts/verify_m60.py --check-only
```

需要保留的M55至M59工具、模型与历史产物；build/、tools/不入Git。
旧receipt不改写，M59文档冻结于archive/m59/source；新clone不具备工作区全部历史证据。
