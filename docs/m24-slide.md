# M24：RAM整数滑移

新增六种RVV编码：vslideup.vx/.vi、vslidedown.vx/.vi、vslide1up.vx、vslide1down.vx。保持VLEN128/ELEN64、单指令容量与RAM优先设计，继续完善VPU本体。实际Orbital接入和Linux程序闭环仍待完成。

## 指令语义

| 指令 | funct6 | funct3 | 有效目的元素i的值 |
|---|---:|---:|---|
| vslideup.vx/.vi | 0x0e | 4 / 3 | i小于OFFSET保留；其余取源i−OFFSET |
| vslidedown.vx/.vi | 0x0f | 4 / 3 | 取源i+OFFSET；源索引达到VLMAX时补0 |
| vslide1up.vx | 0x0e | 6 | i=0取标量，其余取源i−1 |
| vslide1down.vx | 0x0f | 6 | i=VL−1取标量，其余取源i+1 |

全部22种合法SEW/LMUL、目的mask和vstart恢复均支持。保留tail、inactive、vstart之前及上移OFFSET以下元素。VL0或vstart≥VL时目的不变，合法完成清vstart。上移源目的组不能重叠，下移允许同组别名；正常LMUL源和目的必须对齐。masked目的组不能包含v0。这些非法限制在VL0仍检查。

特别注意vslidedown的源界限是VLMAX，而不是VL。例如VL=3、VLMAX=4、源[10,20,30,40]、OFFSET=1，目的有效三元素为[20,30,40]，不能把第三个值错误补0。只有源索引达到4时才补0。

vx偏移为完整无符号XLEN64，不能截到SEW。vi为无符号5位，16..31不能符号扩展。slide1的标量截到SEW；执行mask只控制目的，末尾标量位置被屏蔽时不会向前寻找另一有效位置。FP标量vfslide1up/down尚未实现。

## 微架构与RAM

译码先寄存低8位偏移与高位非零标志；当前VLMAX≤128，任何偏移≥256对普通上移均无元素可写，对普通下移有效元素均补0。该标志仍精确保留所有64位偏移的语义，不进行XLEN加法回绕。

dispatch以9位加减计算源索引，暂存到已有a操作数寄存器。新增的slideAddress阶段独立处理负索引、VLMAX比较和源行/位偏移，再进入原同步RAM读/取及整数Op.move流水。9位能够容纳index+255以及上移的负值标志。VLMAX复用nextVl暂存，但普通算术kind=0不会把它发布为架构VL。保持原状态编码及5位状态宽度，不增加整个向量组快照、RF副本或DSP。

所有源读取已提交RAM，所有结果写候选版本；因此下移别名不会读到提前写入的目的值。目的写回按原元素tag计算位置，不能误用源位偏移。完成等待流水和候选写排空，reply背压不提交版本；flush丢弃候选数据。

普通源读取元素的发射间隔为5周期，标量/补0路径绕过RAM读为3周期，上移OFFSET以下跳过为2周期；执行mask屏蔽元素仅推进索引。e8/m8、VL128、偏移1、无mask时，up.vx为667周期，down.vx及slide1up/down为668周期，包含握手和组复制。不是多条指令并行，也不是128路SIMD。旧220组整数/FP基准结果与周期保持M23值。

## 验证

`tests/test_slide.py`先复制不可变源组元素数组，用完整Python整数偏移计算结果；不会复制RTL的偏移截取、高位标志和9位阶段。完整RTL5576条命令，760次非法、128次撤销，覆盖六种编码、22种类型、所有32种立即数、跨寄存器、VL/VLMAX边界、64位超大偏移、别名、mask、vstart、VL0及标量插入。每条检查32个寄存器、版本与CSR。376条smoke在RTL与原语映射网表比较功能和周期；无FP及16位切分版各374条。

旧指令全RTL回归、220组性能对照、13条INT/FP/滑移/归约交替命令、物理TL访存和monitor检查继续执行。公开顶层在持续monitor读取下验证新滑移、下移别名、标量插入、取消与非法上移重叠，并保留mask/index检查。Monitor ABI1.0，ID=0x2401、caps=0x1fff，bit12表示整数滑移。

资源和三档云端预算见[报告](../reports/m24/evaluation.md)。Yosys负责xcup原语映射，Icarus验证RTL和映射网表；RapidWright家族弧加显式连线假设提供条件延迟预算。无放置布线、-2速度校准或DSP相关端点覆盖，也没有器件STA/SDF；300MHz仍是目标，不能把预算直接当作通过证据。

复现：`make bootstrap`、`python3 scripts/verify_m24.py`、`python3 scripts/package.py --milestone m24`。后续继续gather/compress、宽窄整数、FP归约及更多LSU模式，逐轮比较资源和时序。
