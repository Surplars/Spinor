# M50：独立Spike差分与FP广播/合并

本轮将算术验证接到未修改指令语义的上游Spike，并由覆盖审计发现、补上`vfmerge.vfm`和`vfmv.v.f`。维持VLEN128、ELEN64、单lane和单指令容量；没有增加多发射或乱序执行。

## 硬件

两条指令复用整数move/merge选择通路、同步版本化RAM、原候选版本提交与flush撤销机制。FP32标量按FLEN64检查NaN boxing；未boxing使用规范NaN，合法sNaN仅复制位模式，不quiet也不产生NV。FP64复制完整64位。f0是有效FPR源。

`vfmerge`的v0为选择数据：全部body元素在向量源与标量间选择，不按普通mask关闭写入。`vfmv`须vm=1、vs2=0；只支持SEW32/64及合法组对齐。prestart/tail保留，整数预设拒绝FP指令。共享原数据通路，没有新增RAM端口、整组FF快照或DSP。

monitor实现ID为`0x5001`，ABI1、容量和能力位布局保持。实现ID不代表RVV合规等级。

## 独立模型

固定Spike提交`5a760667bf0d0ab893173b9eeff9c109c8d7dd9a`，源码归档和本地依赖包SHA记录于`third_party/spike-reference.json`。适配器只装入RF/标量测试操作数、调用Spike实际解码与指令执行、读取架构状态；不复制DUT的运算实现，不使用DUT输出生成期望值。全部上游指令源码构建，模型语义未修改。

从上游MATCH/MASK自动提取213种整数、101种浮点、3种配置指令编码。标准RTL遍历22种合法SEW/LMUL配置；每种算术编码至少有合法执行点，宽度超界形式检查非法返回。整数预设检查213种；深流水预设使用紧凑矩阵；网表检查代表性编码子集及新增FP选择专项，没有把子集结果称为全指令网表差分。

每次完成都比较全部32行VRF、VL/vtype/vstart/vxrm/vxsat，以及FP预设的frm/fflags；标量结果只在架构写回有效时比较。测试通过真实context口初始化/读取RAM，施加completion反压并检查提交前状态不提前发布。配置包含三种VSET、x0规则、vill；CSR包含零源和只读写入。普通C/intrinsics的M49程序矩阵在新硬件上重跑，程序适配器仍不是Orbital整核。

另运行差分检查器负控制：仅将一次合法vadd后的vd8期望值翻转bit0，要求原比较逻辑明确报RF不匹配并使仿真失败。该故意失败单独记录为负控制成功，不计为正常指令通过。

范围限制：Spike默认`vstart_alu=false`，本轮算术差分使用vstart=0；非零重启、flush和新指令的别名/boxing边界由独立Python位模式参考与原有定向回归覆盖。模型比较使用TU/MU保留策略及合法frm；各指令未穷举全部数据、舍入、重叠和策略组合。保留frm上Spike选择报非法，当前VPU数据搬运选择忽略；该项单列为实现选择，合法软件必须设置有效frm。没有绕过合法模式下的差异。

本轮尚未进行Spike向量访存差分、VM/PMP/一致性或特权/VS/FS系统验证，不构成完整V、RVA23或misa.V发布依据。下一步优先扩展独立模型访存、故障前缀与恢复闭环，再推进FP16转换和实际CPU接入。

## 复现和时序

```bash
make bootstrap
make verify-m50
make package-m50
```

Linux x86-64需Java21、Python3.12+、GCC/G++、Make及dpkg-deb。依赖只解包到工程`tools/`，不安装系统包；Spike构建使用`-Wno-error`容许新编译器的上游警告，日志保留，未修改模型。首次构建可需十余分钟。固定版本工具由bootstrap获取，ZIP不包含工具二进制与缓存，receipt另绑定外部工具SHA。

时序仍采用M25冻结权重、100ps/link、≤3.333ns的固定云端条件门槛，检查默认公共顶层、计算/访存及四预设。模型不含布局布线和完整DSP时序，不进行ZU15EG-2物理签核。网表仿真是功能/周期一致性检查，没有SDF；本轮没有实际300/500MHz通过结论。结果、资源和逐项输入散列见[M50报告](../reports/m50/evaluation.md)。
