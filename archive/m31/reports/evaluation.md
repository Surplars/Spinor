# M31：整数扩展与当前Windows验证包

新增vzext.vf2/vf4/vf8、vsext.vf2/vf4/vf8，源EEW=SEW/2、/4、/8，目的仍为SEW/LMUL。支持e16/e32/e64的15种合法类型组合；源至少8位、EMUL至少1/8。仍为VLEN128/ELEN64、单指令容量的部分RVV，未接实际Orbital/Linux，不可声明完整V/RVA23或misa.V。

## RAM与流水线

源EEW与目的SEW独立寻址；复用现有RAM、64位暂存、整数move与基本整数元素重叠流水。验证前寄存源几何小表，数据阶段使用2位源SEW，扩展无新增状态或DSP/整组FF快照。源组按自身EMUL对齐；有重叠时要求源EMUL≥1且占据目的组最高部分，fractional源与目的共享物理寄存器则保留非法。用异或与alignment判断最高部分，SAT覆盖所有对齐基址/组大小，与完整端地址判定等价。

支持mask、tail undisturbed、合法vstart恢复、VL0/no-op start及flush。源/目的与执行mask不同EEW的别名、坏selector/位宽/对齐/重叠在VL0也验证。完成握手才切换目的版本，flush丢弃候选结果；不改变fflags/vxsat。Monitor ABI1.0，ID0x3101/caps0x7ffff，新增bit18整数扩展。

## 验证

整数扩展4212条完整RTL命令，1975条非法、198个取消场景，逐条比较32个寄存器、配置与版本；884条smoke当前RTL/映射结果和周期一致。无FP及16位切分版各882条smoke通过。46条混合向量程序交替扩展、INT/FP、归约、gather/compress，通过RTL/映射。新重叠判定的SAT与原增量/地址/配置证明通过。

旧FP宽化归约1664/266、单宽FP归约5771/588、宽化INT归约1025/163、compress1229/189、gather3675/404的完整RTL与smoke映射继续通过。源别名、slide/index/prefix/mask/INT归约、乘除与FP向量、streaming完整RTL回归通过；220组旧性能周期保持M30。9个FP/整数/RF/LSU/host单元RTL按SHA保持M30；独立数值单元与未改动证明复用绑定原输入的已通过证据，冷启动verify命令会重跑这些证据。

公开SpinorVpu并发monitor下279组完整RTL及119组RTL/映射访存通过，末尾执行新扩展、flush/非法重叠和返回普通运算。独立LSU279/119 RTL及119映射通过，monitor2600周期RTL/映射、tiny与软件fixture通过。当前不是Linux驱动上板结果。

## Windows本地验证

spinor-windows-m31.zip内含当前SpinorVpu和RamVectorFp、生成的两个自检TB、PowerShell/Tcl和散列。默认All先XSim功能自检，再按3.333333ns对SpinorVpu全新综合、布局、phys_opt与布线，导出setup/hold、资源、DCP/EDIF和对应DSP延迟。失败也自动流式打包嵌套日志/波形和已生成报告；无旧DCP恢复入口。

两个打包后的原样TB已在云端Icarus重放。Tcl以mock验证9种正常/仿真失败/缺失PASS/缺失时钟/空DSP数据路径；Linux PowerShell7.5.4实际解析并以假launcher执行成功、非零退出和篡改输入检测，包含路径空格、参数、散列和嵌套ZIP检查。这些只验证编排，未执行Windows5.1、XSim、Vivado、P&R或真正DSP导出。功能TB是约10ns抽象tick加稳定等待；实现频率参数不会把RTL仿真变成时序证明。本包没有post-route SDF仿真或可上板bit。具体本地命令见docs/m31-integer-extensions.md。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M30 SpinorVpu | 18344 | 12300 | 9 | 32 | 6 |
| M31 SpinorVpu | 18529 | 12308 | 9 | 32 | 6 |
| M30 LishiVpuMemory | 16146 | 10926 | 9 | 32 | 6 |
| M31 LishiVpuMemory | 16220 | 10934 | 9 | 32 | 6 |

Yosys xcup未布局映射，RAM另占器件LUT，不是BRAM块数。

## 固定云端门槛

| 每段连线假设ps | M30公开ns | M31公开ns | M31计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.700 | 2.627 | 2.591 |
| 100 | 3.300 | 3.277 | 3.141 |
| 200 | 4.577 | 4.577 | 4.241 |

固定100ps/段下公开3.277ns、计算/访存3.141ns，余量0.056/0.192ns，均≤3.333ns。仍使用冻结M25家族权重与锚点，按SHA恢复M30图比较，未放宽假设。只有条件参考：无布局布线或ZU15EG-2校准，DSP相关端点排除，无hold/时钟树/RAM写/IO/SDF验证；物理300/500MHz仍为null，不继承M5。本地需检查完整约束覆盖、setup/hold与route状态。

## 复现

make bootstrap；python3 scripts/verify_m31.py；python3 scripts/package.py --milestone m31。Windows编排检查额外下载散列固定的Linux PowerShell用于测试脚本，不作为HDL工具。receipt绑定源码、RTL/网表、测试台、证明、两份交付与冻结基线；未修改Valence或使用Verilator。后续继续宽窄整数算术、FP转换、更多访存及Orbital程序闭环。
