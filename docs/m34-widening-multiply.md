# M34：宽化整数乘法

新增`vwmulu/vwmulsu/vwmul.vv/vx`共6种编码，返回完整2×SEW积：无符号×无符号、signed(vs2)×unsigned(vs1/rs1)、有符号×有符号。支持源SEW8/16/32、目的16/32/64位，共15种合法SEW/LMUL组合；源SEW64或目的EMUL>8保留非法。标量先截取低SEW位再按该操作所需符号扩展，特别是vwmulsu的标量源为无符号。

复用原容量一的16×16分时乘法器、RAM端口和64位操作数暂存，乘法器RTL与M33逐字节一致，不增加DSP、整组寄存器快照、RAM端口或流水级。窄输入先分别扩展为目的位宽，利用原低积路径取得完整2×SEW积。源SEW32会按64位低积执行16个部分积，周期代价较高，后续可优化。当前是逐元素等待乘法返回，不是每拍一元素乘法，也不是多指令并发。

沿用M33的双宽目的组几何与最高部分重叠规则。源组按LMUL对齐，目的按2×LMUL对齐；只有源EMUL≥1且窄源位于目的最高部分时允许重叠，分数窄源不能与目的共享物理寄存器。两个SEW源可合法互相重叠。mask/tail/prestart保留、合法vstart、VL0检查、完成端背压和flush均覆盖。完成握手后才切换目的版本，CSR与FP状态保持不变。

读源按源EEW寻址，目的按2×SEW生成地址与字节mask；乘法走原串行返回路径，在captureA标量形式或captureB向量形式读完窄输入后，恢复目的bitOffset，避免用窄源偏移移位双宽结果。没有增加新状态或模式寄存器。Yosys映射较M33增加3个FF，架构状态和流水级保持不变；最终资源以报告为准。

独立Python参考用不可变源快照、字节数量和寄存器区间处理组几何/重叠，并用任意精度有符号整数相乘后截取2×SEW。逐条核对全部32个寄存器、版本、配置和sticky状态；覆盖双宽高半部、负积、混合符号高位、标量高位截断、同源、最高部分重叠、v24..v31、掩码、空向量、非零vstart、乘法部分积阶段与停顿完成的取消。无FP及16位切分版本也有smoke。69条混合序列覆盖新乘法与宽化加减、窄化、普通乘法和FP切换。

保留旧向量族完整RTL回归及220组旧性能对比。本轮当前顶层网表重点验证新宽化乘法、混合序列、公共顶层/LSU/monitor接口；未改动数值单元按原RTL/输入散列复用证据，冷启动verify重跑单元数值测试。局部SAT证明按输入SHA核验；增量/地址证明随控制器输入更新重新运行，其余未变证明复用。Monitor ABI仍1.0，ID0x3401、caps0x3fffff，新bit21表示宽化整数乘法；Command/Completion及TileLink端口不变。

云端工具为Yosys映射、Icarus功能/网表仿真、SAT和RapidWright家族延迟参考。冻结M25权重和100ps/段假设不变，两个顶层预算均须≤3.333ns。该模型排除DSP相关端点，无器件布局布线、速度档校准、hold、时钟树、RAM写、外部IO或SDF检查。实际ZU15EG-2的300/500MHz尚未知；不能继承M31本地OOC通过结论。

仍为部分RVV、指令容量1，未接实际Orbital/Linux，不能发布完整V/RVA23或misa.V声明。后续继续整数乘加、定点饱和/clip、FP宽窄转换与访存模式，并推进Orbital异常/上下文/内存模型集成。

复现：

```sh
make bootstrap
python3 scripts/verify_m34.py
python3 scripts/package.py --milestone m34
```

项目包包含当前源码/RTL/测试与网表、冻结M25/M33比较图和M31本地基线记录。本轮继续云端推进，无新的Windows执行包；旧M31包只对应M31。规则和编码摘录见`docs/references/widening-multiply-v1.0.txt`及`widening-add-sub-v1.0.txt`。
