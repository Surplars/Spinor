# Spinor 指令覆盖矩阵（M27）

实现范围以解码器和回归为准；本表不构成RVV/RVA23合规或misa.V发布依据。VLEN128、ELEN64，整数SEW8/16/32/64，浮点SEW32/64，LMUL m1/m2/m4/m8及合法分数LMUL。真实指令容量1，整数元素可流水重叠，归约为串行反馈。实验OoO模块未接入。

| 分组 | 当前状态 | 边界或下一步 |
|---|---|---|
| 配置/CSR | vsetvli、vsetivli、vsetvl；vstart/vxrm/vxsat/vcsr/vl/vtype/vlenb；FP配置与flags | CPU仍需实现权限及VS/FS管理 |
| 基本整数 | add/sub、逻辑、移位、min/max、比较、merge/move的已实现vv/vx/vi编码 | 不是所有整数编码，详见RamVector解码 |
| 整数乘除 | vmul、vmulh、vmulhu、vmulhsu、vdiv[u]、vrem[u] vv/vx | 迭代单元，容量1 |
| 单宽整数归约 | M18新增vredsum/and/or/xor/min[u]/max[u].vs | seed/目的可不按LMUL对齐；合法源重叠；非零vstart非法 |
| 宽化整数归约 | 未实现 | vwredsum[u].vs |
| 基本FP | 加减/反减、乘除/反除、sqrt、FMA系列、min/max、比较、sign注入、分类 | FP32/64，回归对照固定SoftFloat；非完整FP向量集合 |
| FP转换 | 6种同宽整数/浮点及RTZ转换 | 宽化/窄化、FP16、Zvfhmin/Zvfh未实现 |
| FP归约 | 未实现 | ordered/unordered sum、min/max及宽化归约 |
| 排列/索引生成 | vid.v、viota.m；M24新增整数slideup/down vx/vi、slide1up/down vx；mask、22种SEW/LMUL、除viota外可vstart恢复；M25新增vrgather vv/vx/vi、vrgatherei16 vv；M27新增vcompress.vm | vfslide1等未实现 |
| 显式mask运算 | 8种mask逻辑.mm、vcpop.m/vfirst.m，M22新增vmsbf/vmsif/vmsof | 8位通路；viota使用独立元素结果路径 |
| 标量/整组搬运 | M19新增vmv.x.s和vmv.s.x | FP标量搬运及整组寄存器搬运未实现 |
| 定点/宽窄/进位 | 未实现 | 饱和、平均、clip、宽化/窄化算术及扩展、carry/borrow等 |
| 访存 | 单位步长vle/vse，EEW8/16/32/64，独立EMUL、mask、物理故障/停止/vstart前缀 | 无strided/indexed/segments/FOF/whole-register/mask load-store；仅物理普通RAM |
| CPU/SoC | SpinorVpu顶层、TL物理主端、monitor从端、独立VpuHostBoundary | 尚未接Orbital；需VM/PMP/一致性、精确异常和上下文集成 |
| Linux监控 | ABI1.0，UIO用户态工具 | 未作真实内核/上板测试；不是计算作业驱动 |
| 双发射/乱序 | 独立8项实验窗口 | 不属于当前Spinor执行数据通路 |

近期优先继续补齐VPU排列、宽窄整数、FP归约及访存模式，每轮核对资源和云端条件时序；Orbital程序闭环另行推进。只有指令、异常、上下文和内存模型都满足目标配置并完成架构测试后，才能宣称完整目标ISA支持。

M26已统一执行mask（EEW1）与v0数据源（SEW≥8）的保留编码检查，覆盖普通INT/FP、乘除、归约seed、滑移、gather及masked store/load v0。VL0、全mask关闭和vstart越过VL也先检查。EEW1的vcpop/vfirst、前缀mask、viota源可合法使用v0；FP单目selector0、标量寄存器编号0不是向量数据源。EI16仍独立检查不同EEW的数据/索引物理组重叠。新检查修复已知缺口，回归仍不构成完整架构合规证明。

M27的vcompress仅vm=1且vstart=0；目的不得重叠源数据组或显式mask，mask与数据源不同EEW重叠也保留。压紧后tail选择保留；该模式复用已有RAM/计数/地址阶段，不是多指令并行。
