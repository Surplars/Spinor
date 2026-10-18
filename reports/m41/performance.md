# M41 性能与预设参考

以下为SEW32、LMUL m1、frm=RNE的定向输入样例，包含完成，不含配置和context检查。整数归一化为串行且数据相关，表中周期不是固定指令延迟，不能直接用不同输入的两行比较吞吐。当前仍单条指令在途。

| 指令 | VL | 观察周期 |
|---|---:|---:|
| vfwcvt.xu.f.v | 4 | 80 |
| vfwcvt.x.f.v | 4 | 80 |
| vfwcvt.f.xu.v | 4 | 247 |
| vfwcvt.f.x.v | 4 | 220 |
| vfwcvt.f.f.v | 4 | 84 |
| vfwcvt.rtz.xu.f.v | 4 | 80 |
| vfwcvt.rtz.x.f.v | 4 | 80 |
| vfncvt.xu.f.w | 4 | 74 |
| vfncvt.x.f.w | 4 | 74 |
| vfncvt.f.xu.w | 4 | 90 |
| vfncvt.f.x.w | 4 | 152 |
| vfncvt.f.f.w | 4 | 82 |
| vfncvt.rod.f.f.w | 4 | 82 |
| vfncvt.rtz.xu.f.w | 4 | 74 |
| vfncvt.rtz.x.f.w | 4 | 74 |

旧220组基准与冻结M40逐项相同，既有算术、排列、归约和LSU/公共访存性能记录也相同。共享转换器的FP32同宽浮点→整数现在省去64位高半字等待，单元延迟减少1周期；其余同宽和M40宽化算术延迟保持，已用当前FP实例验证。完整逐输入延迟见receipt.resize_wide_unit，整核周期矩阵见receipt.resize_fp。

| 预设顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
| SpinorStandard | FP32/64 | 32 | 21706 | 12907 | 9 | 3.300 |
| SpinorDeep | FP32/64 | 16 | 21627 | 13124 | 9 | 3.232 |
| SpinorInteger | 整数 | 32 | 11934 | 6179 | 1 | 3.292 |
| SpinorIntegerDeep | 整数 | 16 | 11864 | 6396 | 1 | 3.042 |

四个预设的定向公共接口RTL/网表测试及固定100ps/段预算均通过。VLEN128、ELEN64、单lane、容量1、512架构字节VRF保留；整数预设不含FP。映射与预算未经过器件布局布线。
