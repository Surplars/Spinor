# M40 性能与预设参考

新增指令为无外部阻塞RTL周期：SEW32、LMUL m1、frm=RNE，包含完成，不含配置与context检查。仍单条指令在途，不能把指令延迟视作多lane吞吐。

| 指令 | VL | 周期 |
|---|---:|---:|
| vfwadd.vv | 4 | 172 |
| vfwadd.vf | 4 | 164 |
| vfwsub.vv | 4 | 172 |
| vfwsub.vf | 4 | 164 |
| vfwadd.wv | 4 | 172 |
| vfwadd.wf | 4 | 164 |
| vfwsub.wv | 4 | 172 |
| vfwsub.wf | 4 | 164 |
| vfwmul.vv | 4 | 172 |
| vfwmul.vf | 4 | 164 |
| vfwmacc.vv | 4 | 180 |
| vfwmacc.vf | 4 | 172 |
| vfwnmacc.vv | 4 | 180 |
| vfwnmacc.vf | 4 | 172 |
| vfwmsac.vv | 4 | 180 |
| vfwmsac.vf | 4 | 172 |
| vfwnmsac.vv | 4 | 180 |
| vfwnmsac.vf | 4 | 172 |

FP32源经精确扩展后复用FP64计算通路；FMA最终舍入一次。完整含四种合法类型、五种frm、mask及vstart的周期矩阵见receipt.wide_fp。

旧220组基准与冻结M39逐项相同；其余既有族性能记录也相同。LSU与公共顶层旧访存用例周期、请求数和RF读取计数相同。两组旧整数宽化测试中合计四个FP负例现为合法新指令，负例改用保留编码0x39；仅FP配置的bad_opcode计数各增2，命令数、非法总数、整数结果和性能均保持。

下表为未布局的Yosys xcup映射与固定100ps/段条件预算。

| 预设顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
| SpinorStandard | FP32/64 | 32 | 21155 | 12736 | 9 | 3.050 |
| SpinorDeep | FP32/64 | 16 | 21165 | 12953 | 9 | 3.141 |
| SpinorInteger | 整数 | 32 | 11945 | 6179 | 1 | 3.292 |
| SpinorIntegerDeep | 整数 | 16 | 11866 | 6396 | 1 | 3.042 |

四个预设均通过定向公共接口RTL/网表测试；这不是各自完整ISA合规或器件300MHz签核。VLEN128、ELEN64、单lane、512架构字节VRF固定，整数预设不含FP。
