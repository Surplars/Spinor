# M18：砺矢 · Spinor VPU

Valence SoC / Orbital CPU / Spinor VPU。公开可综合顶层SpinorVpu，内部保留Lishi/RamVector兼容名称。新增8条单宽整数归约和独立VpuHostBoundary；不包含实验OoO窗口，没有实际Orbital或Linux计算驱动集成，仍非完整RVV/RVA23。

## 功能证据

归约完整RTL：3418条命令，其中1411次合法归约、210次非法指令，22种合法SEW/LMUL组合、8种运算、10次flush。任意scalar种子/目的、重叠v0/源组、掩码、vl0、vstart、尾部与签名极值均覆盖，每次读取全部32个寄存器和版本图。映射smoke为530条命令，结果、覆盖与周期均同RTL；另测无FP与16位分段版本。

7条混合向量程序在RTL/映射上均通过：归约→普通streaming加法→归约→MUL→归约→FP→归约；使用非零fflags/frm/vxrm/vxsat检查保留，并读取所有寄存器。是有限差分验证，不是全状态形式化或合规测试。

原有1673条整数/乘除、2157条FP向量、789条旧版向量和251条streaming回归通过，220组旧性能用例逐项周期不变。默认RAM访存254组RTL/94组映射；公开SpinorVpu在持续monitor读取时另外通过254组RTL/94组映射，并实际执行vset+vredsum、验证尾部与算术取消。所有访存逐用例性能指标与M17相同，总周期差值来自新增末尾指令和监控检查。

Host boundary的RTL/映射各128次事务（112次返回、16次取消）及6类粘滞协议错误检查通过，含80位token高位、防止坏完成触发提交、load/store错因、stop保留所有权和反压。使用合成CPU/VPU对端，尚非真实Orbital测试。

Monitor生产RTL/映射、8位回绕和非零基址各2600周期通过，ABI1.0保留，ID=0x1801/caps=0x7f；UIO工具通过编译/文件夹具，未在真实Linux设备上运行。历史monitor-v1/OOO报告不代表本轮新功能的集成状态。

## 资源与周期

| 顶层 | LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M17 LishiVpuMemory | 14530 | 10143 | 9 | 32 | 6 |
| M18 LishiVpuMemory | 14790 | 10209 | 9 | 32 | 6 |
| M18 SpinorVpu（含monitor） | 17014 | 11570 | 9 | 32 | 6 |

归约复用现有流水线，新增一个64位标量累加寄存器，计算顶层总计增加66 FF和260 LUT；没有新增DSP/向量RAM副本或整组FF快照。RAM资源为分布式映射，不是BRAM数量。独立Host boundary另为332 LUT/116 FF，尚未算入Spinor顶层；不能由独立单元预算相加推算完整SoC时序。

无completion反压的vredsum m8，SEW8/16/32/64对应VL128/64/32/16，延迟1421/717/365/189周期。串行反馈约11周期/活动元素；不是并行归约树，不是测得的应用带宽或Fmax。

## 云端条件预算

公开SpinorVpu和默认计算顶层均保持M17条件预算：

| 每段假设连线ps | SpinorVpu ns |
|---:|---:|
| 50 | 3.082 |
| 100 | 3.732 |
| 200 | 5.032 |

Yosys未布局网表、RapidWright家族单元参考和显式连线/建立假设；346个DSP相关端点排除，没有-2校准、时钟树/布线/hold/RAM写/I/O signoff。不是STA、WNS或300/500MHz通过。实际器件时序基线仍只有历史M5，本轮无Vivado执行。

## 接入与剩余工作

CPU连接、不可撤销授权、访存前缀/停止、非法与访问错误见docs/cpu-spinor-contract.md；完整缺失范围见docs/isa-coverage.md。PS ARM与PL RISC-V共享monitor ABI，两个Linux需要单一快照写所有者。原生RISC-V Linux仍缺完整ISA、VS/FS/上下文、保护/翻译、一致性和精确异常接入；ARM还缺计算作业队列或代理。

复现：python3 scripts/verify_m18.py；打包：python3 scripts/package.py --milestone m18。每份源码、RTL、网表、测试台和报告的SHA见receipt.json。没有Valence/Orbital源码改动，没有安装或调用Verilator。
