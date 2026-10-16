# M32：整数窄化移位

新增vnsrl.wv/wx/wi和vnsra.wv/wx/wi，共6种编码；覆盖16→8、32→16、64→32的15种合法SEW/LMUL组合。源vs2的EEW和EMUL为目的的两倍；vs1移位量向量仍按目的SEW/LMUL读取。shift取低log2(2×SEW)位，wi使用无符号5位立即数；wx配合x0可执行vncvt.x.x.w伪指令。SEW64→128超出ELEN64、目的LMUL=m8使源EMUL=16，均保留非法。仍为部分RVV、单指令容量，未接实际Orbital/Linux，不能发布完整V/RVA23或misa.V声明。

## RAM和微架构

复用M31源SEW寄存器、现有RAM端口、64位a/b暂存和原整数分级移位流水。dispatch按宽源寻址，captureA之后将vs1地址恢复为目的SEW；整数lane按宽源位宽移位，流水返回时按目的SEW的tag/字节mask截断写回。无新状态、DSP、整组寄存器快照或流水级，9个FP/整数/RF/LSU/host单元RTL保持M31。

源组按自身EMUL对齐；目的与宽源重叠时必须位于最低部分（vd=vs2）。窄源vs1与宽源vs2的不同EEW物理别名保留非法；目的与vs1的同宽重叠可用。支持mask、tail undisturbed、合法vstart及VL0检查。fflags/vxrm/vxsat保持不变，提交握手才切换目的版本，flush抛弃候选结果。Monitor ABI1.0，ID0x3201，caps0xfffff，bit19表示窄化整数移位。

新源对齐布尔表达式由全输入SAT与独立计数表对照；原组重叠/最高部分、增量、地址和配置比较证明继续通过。

## 验证

完整窄化RTL测试4945条命令，1566条合法窄化指令（含空操作）、1753次非法拒绝、198个取消场景，覆盖15种合法类型；逐条对照32个寄存器、版本与配置。覆盖宽源与窄移位向量跨寄存器、算术负数、高移位位、超宽scalar、uimm16..31、最低重叠、v24..v31边界、mask/tail、VL0、vstart、源别名及取消恢复。489条smoke当前RTL/映射的数值、版本和周期一致；无FP与16位切分版各487条smoke通过。52条混合指令RTL/映射通过，包含窄化→扩展→FP FMA（同funct6不同funct3）→compress，检查模式切换。

原整数扩展4212/884、FP宽化归约1664/266、单宽FP归约5771/588、宽化INT归约1025/163、compress1229/189、gather3675/404的完整RTL与smoke映射继续通过。旧源别名、slide/index/prefix/mask/INT归约、乘除、FP向量、streaming完整RTL回归通过，220组旧性能周期保持M31。未改动数值单元与局部证明复用按原输入SHA绑定的已通过证据；冷启动verify会重跑它们。

公开SpinorVpu并发monitor下279组完整RTL及119组RTL/映射访存通过，末尾执行窄化wx/wi/wv、masked保留、flush与非法混合EEW源别名。独立LSU279/119 RTL及119映射通过；monitor2600周期RTL/映射、tiny与软件fixture通过。不是实际Linux或上板验证。

## 资源

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 | RAM32M16 |
|---|---:|---:|---:|---:|---:|
| M31 SpinorVpu | 18529 | 12308 | 9 | 32 | 6 |
| M32 SpinorVpu | 18674 | 12308 | 9 | 32 | 6 |
| M31 LishiVpuMemory | 16220 | 10934 | 9 | 32 | 6 |
| M32 LishiVpuMemory | 16460 | 10934 | 9 | 32 | 6 |

Yosys xcup未布局映射；RAM另占LUT，非BRAM块数。新指令复用原分级shift，FF/DSP/RAM计数保持M31。M31本地Vivado使用14173总LUT、11605FF、7DSP、2RAMB36，工具映射拓扑不同，不能把该物理资源计数直接当成M32结果。

## 固定云端门槛与本地基线

| 每段连线假设ps | M31公开ns | M32公开ns | M32计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.627 | 2.700 | 2.500 |
| 100 | 3.277 | 3.300 | 3.050 |
| 200 | 4.577 | 4.500 | 4.227 |

固定100ps/段下公开3.300ns、计算/访存3.050ns，余量0.033/0.283ns，均≤3.333ns。仍使用冻结M25权重/锚点，按SHA恢复M31图对比，未改变权重或连线假设。

M31本地报告作为冻结基线保留：Vivado2025.1、ZU15EG-2、3.333ns，setup+0.392ns、hold+0.009ns、布线错误0、两组XSim通过。HD.CLK_SRC及613个输入/608个输出的接口延迟未设，仍非完整SoC时序签核。M32改变了RTL，不能继承M31的本地通过结论。

M32只经过云端条件预算，无布局布线/速度档校准，DSP相关端点排除，没有hold、时钟树、RAM写、接口或SDF检查；当前物理300/500MHz均未知。200ps/段档不满足300MHz，公开顶层100ps档余量也较小。

## 复现和交付

make bootstrap；python3 scripts/verify_m32.py；python3 scripts/package.py --milestone m32。完整包包含当前源码/RTL、测试与网表、冻结M25/M31图及M31本地报告。此轮无新的Windows执行包，不要求立即重跑本地；先在云端推进功能并保留M31实测比较基线。旧M31 Windows包用于验证M31，不能代表M32。未修改Valence或调用Verilator。下一步继续宽化算术/定点与FP宽窄转换、访存模式和Orbital接入。
