# M18：Spinor 整数归约与 Orbital 接入边界

命名：Valence为SoC，Orbital为CPU，Spinor为VPU，中文保留砺矢。公开SoC顶层为SpinorVpu；RamVector、LishiVpuMemory、LishiVpuMonitored是兼容实现类。SpinorVpu含物理RAM TL主端和独立monitor TL从端，io.core仍为单条不可撤销命令接口；VpuHostBoundary作为CPU侧独立配套模块，尚未连接实际Orbital。

## 新增8条单宽整数归约

vredsum.vs、vredand.vs、vredor.vs、vredxor.vs、vredminu.vs、vredmin.vs、vredmaxu.vs、vredmax.vs。编码及语义对照官方RVV 1.0和riscv-opcodes，摘录见references/reductions-v1.0.txt。

支持SEW8/16/32/64及22种合法SEW/LMUL组合，包括分数LMUL。vs2按LMUL组读取；vs1[0]是单寄存器种子，vd[0]是单寄存器结果，vs1和vd无组对齐要求；目的可与任意源、v0重叠。只有vs2的活动元素参与，种子始终参与。vl>0且全掩码时写回种子；vl=0不写寄存器。vstart非零非法，按通用非法指令规则保留原vstart及寄存器状态。普通成功完成清vstart。尾部在vta=0/1时都选择保留旧值，符合允许的undisturbed选择。

原有RAM版本方案继续使用：先复制单个目的寄存器到候选区、缓存128位v0、从RAM读种子；逐个活动元素进入现有整数流水线，返回后更新一个64位标量累加寄存器；最后只写vd的低SEW字节。完成握手前不发布版本。flush丢弃候选、清流水，旧架构数据保持。没有整组向量FF副本、新增DSP或新的向量RAM副本。

归约当前串行反馈，每个活动元素占用11周期左右，追求功能与时序可控，不是并行树。无completion反压时，m8 vredsum：e8/vl128为1421周期，e16/vl64为717周期，e32/vl32为365周期，e64/vl16为189周期。这些是仿真命令延迟，包含首尾开销，不含CPU执行/缓存/真实SoC内存，不能直接当作已实现MHz或整体应用性能。

## 验证与资源

独立Python整数折叠参考，完整RTL包含1411次合法归约、210次非法指令、10次flush，覆盖全掩码、vl0、源/目的/掩码别名、任意标量寄存器、vta/vma、签名极值、加法回绕、非零vstart、源组错误对齐和不支持的标量编码。每个用例读取全部32个寄存器并核对版本位，completion反压期间禁止提前提交。另在无FP和16位分段顶层检查，使用映射网表复测smoke子集。是有限差分验证，不是RVV全合规证明。

原有220组性能用例与M17逐项周期相同；整数、FP、streaming和访存继续回归。RamVectorFp/LishiVpuMemory数值单元和寄存器资源不复制；详细新旧资源、云端条件预算及输入散列见reports/m18/evaluation.md和receipt.json。所有新实现仍未经本地Vivado布局布线。

Monitor ABI仍为1.0，实现ID更新为0x1801，caps的bit6表示单宽整数归约。软件工具仍兼容旧ABI1.0。Spinor集成测试另外实际执行归约，再检查访存、取消及monitor快照。

## 复现

M18交付包包含M17基线RTL/网表用于对照。沿用Mill1.1.7、Chisel7.16.0、Java21、Yosys/Icarus及RapidWright家族参考表，无需Vivado：

```bash
python3 scripts/verify_m18.py
python3 scripts/package.py --milestone m18
```

monitor-v1附加包及其verify_monitor.py/report_monitor.py是历史M17工作流；当前以verify_m18.py为准。实验OoO窗口仍未接入，真实指令容量为1。宽化整数归约、浮点归约及其余缺失ISA继续按isa-coverage.md推进。
