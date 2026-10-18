# M39：可验证规模预设与浮点搬运

新增统一 `SpinorParams` 与 Mill 生成入口，生产顶层支持裁掉浮点及选择整数 ALU 分段。继续使用版本化 RAM 和单条在途指令；此轮没有扩大 VLEN 或增加 lane。与此同时实现 vfmv.f.s、vfmv.s.f、vfslide1up.vf、vfslide1down.vf 四种编码。

## 当前可配置范围

| 参数 | 支持值 | 实际影响 |
|---|---|---|
| enableFp | true / false | 删除或保留 FP32/64 运算、FP CSR 状态/端口、FP 指令支持及 monitor 能力位 |
| aluStageBits | 16 / 32 | 64位整数 ALU 的流水分段粒度；不是向量宽度或 lane 数 |
| regionBase / regionBytes | 64位地址空间内对齐的2幂大小普通RAM窗口，至少8字节 | LSU物理访问检查；不代表缓存、PMP或虚拟内存 |
| monitorBase | 4KiB对齐64位地址 | 独立monitor TL从端窗口 |
| VLEN / ELEN | 当前128 / 64 | 固定，不支持更大值；不接受后静默截断 |
| lanes / 指令容量 | 当前1 / 1 | 不含多lane、双发射或乱序 |
| 架构VRF容量 | 当前512字节 | 32个128位架构寄存器；双版本物理存储1024字节，始终使用RAM |

| 预设 | 浮点 | ALU分段 | 用途 |
|---|---|---:|---|
| standard | FP32/64 | 32位 | 既有ZU15EG设计默认配置 |
| deep | FP32/64 | 16位 | 更多流水切分，需独立比较面积和时序 |
| integer | 无 | 32位 | 减少DSP与逻辑的整数/定点配置 |
| integer-deep | 无 | 16位 | 整数配置的深流水候选 |

不能把较深流水等同于更小面积、更大吞吐或已验证更高频率。每个预设独立综合、功能仿真与云端预算；报告中的器件300/500MHz签核字段仍为空。整数预设不支持基础V中的浮点指令，不能宣称完整V或RVA23。standard目前同样是部分RVV。

关闭浮点不再隐式关闭解码/合法性寄存阶段和候选写回阶段。新增stageControl把这些时序结构与数值FP硬件分离；保留旧RamVector构造默认行为，生产顶层显式启用时序切分。

## 生成与SoC连接

```bash
./mill Vpu.runMain vpu.GenerateConfigured --preset integer --out build/my-vpu --name MySpinor
./mill Vpu.runMain vpu.GenerateConfigured --preset deep --out build/my-vpu-deep --name MyDeepSpinor
./mill Vpu.runMain vpu.GenerateConfigured --preset integer --alu-stage-bits 16 --region-base 0x80000000 --region-bytes 0x10000000 --monitor-base 0x40000000 --out build/custom --name CustomSpinor
python3 scripts/generate_profiles.py
```

每次生成独立SystemVerilog及同名JSON配置清单。布尔参数只接受true/false；未知/重复选项、未实现VLEN或lane数量、无效分段和物理窗口会失败。硬件在Chisel elaboration时确定；不是运行时切换大小。JSON的preset字段记录起点，最终参数以其余字段为准。

```scala
val cfg = SpinorParams.preset("integer-deep")
val vpu = Module(new SpinorVpu(monitorBase = 0x40000000L, config = cfg))
```

完整配置保留原公开端口。整数配置的io.core.frm/fflags端口不存在，Scala集成必须使用匹配参数；其余命令、context、完成、物理TL主端和monitor从端保留。monitor ABI仍1.0，ID为0x3901；整数配置清除FP32、FP64、FP单宽归约和FP宽化归约能力位，几何和容量由硬件返回。

## 浮点搬运语义

四种新增形式仅支持SEW32/64、FLEN64，不经过FP数值运算器。向量位模式原样搬运，包括sNaN payload、负零和非规格化数；不会新增fflags。frm不影响这些指令，保留frm编码也不使搬运非法。标量FP32输入仍检查NaN boxing：高32位非全1时使用canonical NaN；FP32读到标量时高32位置全1。

vfmv.f.s忽略VL/vstart执行element0读取，忽略LMUL对源寄存器对齐的限制。即使rd=0也必须写f0；f0不是x0。vfmv.s.f只在vstart<vl时更新目标element0，其他位保留，LMUL不扩大目标写回组。成功完成清零vstart，完成等待或flush不提前发布架构状态。

vfslide1up/down复用已有整数slide地址与move通路。支持mask、非零vstart、跨寄存器和down原地别名；up源/目的组不得重叠。仅有效插入位置读取标量值；mask关闭的位置、prestart与tail保留。

Completion布局不变，writesScalar表示是否需要宿主标量写回。对于成功vfmv.f.s，宿主依据回显instruction选择FPR及rd，必须允许f0写回；VSET/CSR/vmv.x.s等仍选择GPR且抑制x0。宿主需预先保留正确的FPR或GPR写回资源并管理VS/FS，不能把全部writesScalar无条件接到整数RF。独立VpuHostBoundary原样传递，不负责寄存器文件选择；尚未真实集成Orbital。

## 验证边界及后续参数化

新增矩阵逐条核对全部32个向量寄存器、版本、vstart、vxrm/vxsat和FP状态，覆盖VL0、f0、未对齐的单寄存器搬运、四种指令、保留frm、非法SEW、mask、撤销和反压。公共预设测试检查实际可见FP端口、硬件删除、monitor能力、整数运算、FP标量回传、物理TL读写和窗口拒绝。它们是定向配置测试，不等同于四个预设各执行完整ISA回归。

VLEN扩展还需一起调整VRF几何、mask缓存、VLMAX/index/tag位宽、context寻址、LSU chunk和进度、monitor打包及全部参考模型；多lane还需RF端口/分银行、元素分发、结果仲裁与相关处理。当前统一参数入口为后续改造提供配置边界，不把未实现规模列为可用预设。

资源、测试数量和固定300MHz条件预算见[M39报告](evaluation.md)。规范依据为固定的V v1.0源码，SHA与官方编码见[参考](../../docs/references/m39-fp-transfers-v1.0.txt)。


## 验证结果

新增FP搬运完整RTL 422条命令、9种合法FP类型，4种编码；包含36次撤销和f0、VL0、NaN boxing、保留frm等情况。32位及16位ALU配置精简RTL/当前网表各110条，所有架构状态和周期一致；无FP配置拒绝全部新FP形式。

102项RTL子进程、17项定向网表子进程通过。其中4个生产预设各运行公共命令/context/TL/monitor集成测试，明确为定向范围；默认核心重跑旧M38及全部既有RTL族，并运行旧M38/M37/M36精简网表、MAC、混合序列和LSU/公共顶层143组。默认公开顶层完整RTL303组访存后执行新FP位模式序列，覆盖sNaN、canonical NaN、f0与原地down。7项CLI拒绝测试通过，默认配置生成RTL与公开顶层逐字节相同（仅替换顶层名称）。回归日志与源输入SHA均绑定receipt。

旧220组及全部既有族性能记录相同。保留SHA绑定的8个旧数值/存储/边界单元RTL未改变；FP数值证据重用这些相同单元，FP向量集成矩阵重跑。增量/地址SAT重跑，不作为新FP搬运的形式证明。[性能与预设表](performance.md)。

## 默认配置资源（括号相对M38）

| 顶层 | 逻辑LUT | FF | DSP | RAM64M8 / RAM32M16 |
|---|---:|---:|---:|---:|
| SpinorVpu | 21145 (+4) | 12734 (+0) | 9 | 32 / 6 |
| LishiVpuMemory | 18963 (+92) | 11360 (+0) | 9 | 32 / 6 |
| RamVectorFp | 17659 (+48) | 10348 (+0) | 9 | 32 / 6 |

## 四个生产预设

| 顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
| SpinorStandard | FP32/64 | 32 | 21145 | 12734 | 9 | 3.292 |
| SpinorDeep | FP32/64 | 16 | 21070 | 12951 | 9 | 3.050 |
| SpinorInteger | 整数 | 32 | 11812 | 6179 | 1 | 3.292 |
| SpinorIntegerDeep | 整数 | 16 | 11845 | 6396 | 1 | 3.292 |

各预设RAM64M8/RAM32M16均32/6，架构VRF仍512字节；LUTRAM另计，不等于Vivado BRAM数量。整数预设删除FP而保留定点、整数乘除和物理LSU。接口缺失FP CSR端口和能力位已检查。

## 固定条件时序预算

| 连线ps/段 | M38公共ns | M39公共ns | M39计算/访存ns |
|---:|---:|---:|---:|
| 50 | 2.662 | 2.662 | 2.700 |
| 100 | 3.292 | 3.292 | 3.300 |
| 200 | 4.592 | 4.592 | 4.592 |

默认100ps/段下公共3.292ns、计算/访存3.300ns；四个预设也各自要求≤3.333ns。M25权重、参考图和门槛未放宽。未布局、未按-2校准，排除DSP端点，未签核RAM写、hold、时钟树或IO。M39未执行Vivado/SDF，实际300/500MHz未知。
