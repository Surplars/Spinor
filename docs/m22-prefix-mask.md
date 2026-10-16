# M22：前缀掩码

新增 `vmsbf.m`、`vmsif.m`、`vmsof.m`，用于生成首个有效置位之前、包含首位、仅首位的掩码。例如VL=8、源mask=0b10010100时，三者得到0b00000011、0b00000111、0b00000100。masked时只把有效源位计入“首位”，被屏蔽的目的位保留。

## 语义

使用真实RVV编码：OPMVV、funct6=0x14、vs1选择子分别为1/3/2。源与目的都是单个mask寄存器，忽略LMUL组对齐；支持全部22种合法SEW/LMUL。非零vstart、vd=vs2、masked时vd=v0均非法，包括vl=0时。允许unmasked写v0，以及使用v0作为源但写其他目的寄存器。

合法完成清vstart；非法和flush不改变架构状态。尾部及inactive位保留原值，属于规范允许的策略。未实现viota/vid等其余合法RVV unary指令，仍会报告不支持；不能把所有未实现选择子都称为规范保留。官方语义与编码见[参考摘录](references/mask-prefix-v1.0.txt)。

## 微架构

复用M21的源/结果/有效字节暂存器、单RAM读口和候选目的读改写。每次8位，依次经历dispatch、源读、源取与predicate过滤、前缀计算、候选目的读、目的写，共6周期。增加的seen位跨字节记录是否已有有效置位；并行的小范围OR决定字节内的首位，不使用128位串联扫描或整组FF快照。

VL128的三条指令都是105周期（包含命令与完成握手）。后续目的有效位要写零，因此不会在找到首位后提前结束。命令仍逐条执行；基础整数元素的流水重叠与M21相同。

## 验证和接口

独立Python参考先找全向量的最小有效置位索引，再按索引生成结果。完整RTL2890条命令，1505次合法操作、431次非法、75次撤销；覆盖全部类型、128个one-hot位置、字节边界、VL外置位、源/目的v0和重叠限制。277条smoke另跑RTL与映射；无FP和16位切分版本也通过。实际资源和时序结果见[M22报告](../reports/m22/evaluation.md)。

8位helper对独立的最低置位隔离/减法公式完成2048种输入组合的SAT检查。它只证明组合逻辑，FSM/flush/RAM提交由指令级仿真检查。SoC顶层在monitor流量下运行三条新指令、取消/非法指令、v0消费和后续普通masked vadd。

monitor ABI1.0，ID=0x2201，caps=0x7ff，bit10表示这三条前缀指令。命令与MMIO布局见[CPU合同](cpu-spinor-contract.md)及[monitor文档](monitor-soc.md)。尚未接入实际Orbital，未完成Linux计算驱动和完整RVV。

## 复现

```bash
make bootstrap
python3 scripts/verify_m22.py
python3 scripts/package.py --milestone m22
```

M21公开映射图以gzip冻结，`prepare_m22_baseline.py`恢复后核对原始SHA，以节省仓库空间。数值单元未修改，当前报告按生产RTL/输入SHA复用其证据；完整复现入口会重新运行这些单元测试。

300MHz仍是设计目标。云端使用相同的Yosys未布局图、RapidWright家族参考弧和显式连线/建立假设；未覆盖实际布线、DSP、-2校准、时钟树/hold、RAM写或I/O，不是器件STA或SDF结论。
