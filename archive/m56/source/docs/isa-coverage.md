# Spinor 指令覆盖矩阵（M50）

实现范围以解码器和回归为准；本表不构成RVV/RVA23合规或misa.V发布依据。VLEN128、ELEN64，整数SEW8/16/32/64，浮点SEW32/64，LMUL m1/m2/m4/m8及合法分数LMUL。真实指令容量1，整数元素可流水重叠，归约为串行反馈。实验OoO模块未接入。

| 分组 | 当前状态 | 边界或下一步 |
|---|---|---|
| 配置/CSR | vsetvli、vsetivli、vsetvl；vstart/vxrm/vxsat/vcsr/vl/vtype/vlenb；FP配置与flags | CPU仍需实现权限及VS/FS管理 |
| 基本整数 | add/sub、逻辑、移位、min/max、比较、merge/move；M36新增vrsub.vx/vi、vmsgt[u].vx/vi共6种编码 | M37新增15种carry/borrow编码；完整编码仍需审计 |
| 整数乘除 | vmul、vmulh、vmulhu、vmulhsu、vdiv[u]、vrem[u] vv/vx | 迭代单元，容量1 |
| 单宽整数乘加 | M35：vmacc/vnmsac/vmadd/vnmsub vv/vx，SEW8/16/32/64、22种类型 | 复用乘法器和分段ALU，逐元素串行 |
| 宽化整数乘加 | M36：vwmaccu/vwmacc/vwmaccsu vv/vx、vwmaccus vx，共7种编码；源SEW8/16/32、目的2×SEW | 目的EMUL≤8；旧vd也是宽源，不允许与窄源组重叠；复用乘法器/ALU/RAM |
| 单宽整数归约 | M18新增vredsum/and/or/xor/min[u]/max[u].vs | seed/目的可不按LMUL对齐；合法源重叠；非零vstart非法 |
| 宽化整数归约 | M29：vwredsum[u].vs，源SEW8/16/32，18种SEW/LMUL（含m8），标量2×SEW | SEW64→128超出ELEN64；不同EEW的seed/data不能重叠 |
| 宽化FP算术 | M40：vfwadd/vfwsub vv/vf/wv/wf、vfwmul vv/vf及四类宽化FMA vv/vf，共18编码 | FP32→64、目的EMUL≤8，复用原FP单元 |
| 基本FP | 加减/反减、乘除/反除、sqrt、FMA系列、min/max、比较、sign注入、分类 | FP32/64，固定SoftFloat数值参考；M50加入Spike独立差分，补vfmerge.vfm/vfmv.v.f |
| FP估算 | M42：vfrec7.v、vfrsqrt7.v，FP32/64、mask/vstart/合法LMUL | 七位估算；vfrsqrt7忽略frm，倒数溢出使用frm；独立精确整数参考 |
| FP转换 | 6种同宽；M41新增15种宽化/窄化编码，含ROD、整数16↔FP32的6种合法形式 | FP16数据格式、Zvfhmin/Zvfh未实现 |
| FP归约 | M28单宽FP32/64求和/min/max；M30新增vfwredosum/vfwredusum，FP32源→FP64累加；unordered用ordered折叠 | FP16及FP64→128未支持；非零vstart非法 |
| 排列/索引生成 | vid.v、viota.m；M24新增整数slideup/down vx/vi、slide1up/down vx；mask、22种SEW/LMUL、除viota外可vstart恢复；M25新增vrgather vv/vx/vi、vrgatherei16 vv；M27新增vcompress.vm | M39新增vfslide1up/down.vf |
| 显式mask运算 | 8种mask逻辑.mm、vcpop.m/vfirst.m，M22新增vmsbf/vmsif/vmsof | 8位通路；viota使用独立元素结果路径 |
| 标量/整组搬运 | M19新增vmv.x.s和vmv.s.x；M36新增vmv1r/2r/4r/8r.v，直接RAM整组复制 | 整组搬运忽略VL/LMUL/vill，按SEW解释vstart；M39新增vfmv.f.s/vfmv.s.f，注意f0可写 |
| 宽化整数加减 | M33：vwaddu/vwadd/vwsubu/vwsub 的 vv/vx/wv/wx 共16种编码，SEW8/16/32，目的2×SEW/2×LMUL | 目的EMUL≤8；允许最高部分窄源重叠和同宽源原地写回；mask/vstart与不同EEW源别名检查 |
| 宽化整数乘法 | M34：vwmulu/vwmulsu/vwmul vv/vx，SEW8/16/32，完整2×SEW积 | 原单DSP分时乘法器；目的EMUL≤8；高位重叠、mask/vstart |
| 定点/宽窄/进位 | vzext/vsext.vf2/vf4/vf8；M32新增vnsrl/vnsra.wv/wx/wi，支持mask/vstart和宽窄源独立寻址；M37新增饱和加减10种、平均8种、舍入移位6种、carry/borrow15种 ；M38补vsmul和vnclip[u] | 基础V定点族已覆盖目标ELEN范围，仍需完整架构差分 |
| 访存 | 单位步长vle/vse、M43跨步vlse/vsse、M44索引vluxei/vloxei/vsuxei/vsoxei，EEW8/16/32/64，独立EMUL、mask、物理故障/停止/vstart前缀 | M45新增20种whole-register与2种mask load/store；M46新增56种单位步长segment编码；M47新增168种跨步/索引segments；M48新增32种FOF单位步长/分段load；仅物理普通RAM |
| CPU/SoC | SpinorVpu顶层、TL物理主端、monitor从端、独立VpuHostBoundary | 尚未接Orbital；需VM/PMP/一致性、精确异常和上下文集成 |
| Linux监控 | ABI1.0，UIO用户态工具 | 未作真实内核/上板测试；不是计算作业驱动 |
| 双发射/乱序 | 独立8项实验窗口 | 不属于当前Spinor执行数据通路 |

完整性计划见[目标与验收清单](rvv-completion-plan.md)。分段/FOF已有定向回归，M49已有编译器程序闭环；M50覆盖314种算术编码的独立模型差分，接下来推进访存架构差分与系统异常；Zvfhmin等RVA23额外要求另行补齐，每轮核对资源和云端条件时序；Orbital程序闭环另行推进。只有指令、异常、上下文和内存模型都满足目标配置并完成架构测试后，才能宣称完整目标ISA支持。

M26已统一执行mask（EEW1）与v0数据源（SEW≥8）的保留编码检查，覆盖普通INT/FP、乘除、归约seed、滑移、gather及masked store/load v0。VL0、全mask关闭和vstart越过VL也先检查。EEW1的vcpop/vfirst、前缀mask、viota源可合法使用v0；FP单目selector0、标量寄存器编号0不是向量数据源。EI16仍独立检查不同EEW的数据/索引物理组重叠。新检查修复已知缺口，回归仍不构成完整架构合规证明。

M27的vcompress仅vm=1且vstart=0；目的不得重叠源数据组或显式mask，mask与数据源不同EEW重叠也保留。压紧后tail选择保留；该模式复用已有RAM/计数/地址阶段，不是多指令并行。

M28单宽FP归约支持9种FP类型和5种合法frm。源组按LMUL对齐，seed和目的仅占单寄存器且可不对齐/重叠。VL0不写目的；VL>0但无有效元素时原位复制seed，不规范化NaN或新增异常。目的tail保留，完成握手才提交RF版本和fflags；flush取消私有结果。保留frm、非零vstart、masked源v0在VL0也检查。

M29宽化整数归约将源组几何保留为SEW/LMUL，seed、累加器、结果为2×SEW且EMUL=1。目的可与任意源及mask重叠；两个源seed/data因不同EEW不得共享物理寄存器。仅源SEW8/16/32合法；VL0、保留vstart和masked源v0规则同归约合同。

M30宽化FP归约仅源SEW32、LMUL m1/m2/m4/m8/mf2合法；seed/result为64位EMUL1，目的tail保留。seed与data因不同EEW不能共享物理寄存器。无有效元素时原样复制seed，VL0完全不写目的；frm保留、SEW不支持、非零vstart及masked源v0在VL0也检查。不对普通向量FP宽化转换作支持声明。

M36宽化乘加以旧vd为2×SEW累加源；即使窄源只位于目的组最高部分，仍因同一寄存器提供不同EEW源而保留。窄源之间可同宽别名。结果取2×SEW位，mask/prestart/tail保留，完成接受才发布候选组。`vwmaccus.vv`没有标准编码，不计为缺口。反减立即数及大于比较立即数均先符号扩展到SEW；`vmsgtu.vi`随后进行无符号比较。

M36整组搬运只允许vm=1、NREG=1/2/4/8及相应源/目的对齐；独立于当前VL、LMUL和vill。以evl=NREG×VLEN/SEW判断vstart是否越界，从vstart×SEW/8字节起复制，之前字节保留；vd=vs2为架构NOP。成功完成仍清零vstart。整组寄存器搬运不等于整组访存支持。

M37 carry的vm=0仍执行全部body元素，v0提供进位/借位数据。饱和私有累计只在完成握手时并入vxsat；平均与舍入右移实现全部四种vxrm模式，不设置vxsat。详见[M37说明](m37-fixed-point.md)。

M38 vsmul保留完整2×SEW乘积并按SEW-1舍入饱和；vnclip[u]先对2×SEW源舍入，再检查目标区间。默认IntegerMultiply接口不变，目标VPU使用可选分数配置共享原DSP。详见[M38说明](m38-fractional-and-clip.md)。

M39提供四个规模预设；VLEN/ELEN/lane仍128/64/1。整数配置删除FP硬件、FP CSR端口及对应monitor位。[配置与新增FP搬运](m39-configurations-and-fp-transfers.md)。

M40宽化FP的窄源/宽源/目的独立寻址，FMA旧vd按64位读取，标量源按32位检查NaN boxing。[宽化FP说明](m40-wide-floating-point.md)。

M41新增跨宽转换，目的/源EEW独立，RTZ与ROD忽略frm数值。[转换说明](m41-width-conversions.md)。

M42新增FP七位估算，归一化与查表分段；整数转换按字节跳过零高位。[估算与转换提速](m42-estimates-and-efficiency.md)。

M43支持正/负/零字节步长、rs2=x0、mask/vstart、全64位地址与回绕；无效frm的向量FP执行为规范保留行为，合法软件须设置frm。[跨步及效率说明](m43-strided-memory.md)。

M44新增16种索引访存：索引为零扩展字节偏移，数据按SEW/LMUL解释，支持标准合法重叠与有序形式；仅物理普通RAM。[实现说明](m44-indexed-memory.md)。

M45整组访存忽略VL/vtype/vill，EVL按NREG×VLEN/EEW计算，支持EEW8/16/32/64 load和EEW8 store；mask尊重vill、按ceil(VL/8)字节传送、vstart以字节计。M45的NF用于整组数量；单位步长分段另由M46实现。[规则和验证](m45-context-memory.md)。

M46单位步长分段支持2～8字段、EEW8/16/32/64、合法分数/整数EMUL及mask/vstart；故障或停止允许当前段留下字段前缀，重启从该段字段0重新执行。没有新增DSP或整组快照。[规则与验证](m46-segment-memory.md)。

M47跨步/索引分段支持2～8字段、数据/索引独立EEW与EMUL、逐段mask/vstart及正负/零步长。索引分段load的所有字段均不得与索引组重叠，同宽也保留；store继续允许同EEW源别名。FOF后由M48实现。[规则与验证](m47-addressed-segments.md)。

M48补单位步长/分段FOF：绝对元素0出错保留VL并报异常，后续元素出错抑制异常并缩短VL，停止保持VL。使用访存包装层原子提交VL/vstart；完整性仍需架构差分和程序/系统验收。[规则与验证](m48-fault-only-first.md)。

M50新增FP广播/合并，复用整数选择通路和版本化RAM；314种整数/浮点算术编码在Spike差分中各有合法执行点。该统计不包含访存，也不等于所有保留编码、异常/重启或操作数组合完整验收。见[M50范围](m50-spike-and-fp-select.md)。
