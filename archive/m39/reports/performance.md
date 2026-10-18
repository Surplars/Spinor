# M39 性能与预设参考

新增指令为无外部阻塞RTL周期，包含完成，不含配置和context检查。仍单条指令在途。

| 操作 | SEW | VL | 周期 |
|---|---:|---:|---:|
| read | 32 | 4 | 7 |
| read | 64 | 2 | 7 |
| write | 32 | 4 | 9 |
| write | 64 | 2 | 9 |
| up | 32 | 4 | 35 |
| up | 64 | 2 | 25 |
| down | 32 | 4 | 35 |
| down | 64 | 2 | 25 |

read/write为vfmv.f.s/vfmv.s.f，up/down为vfslide1up/down.vf。搬运复用既有RAM、slide地址与整数move；不调用FP计算单元。完整周期矩阵含type、vstart及frm，见receipt.fp_transfers。

旧220组基准与冻结M38逐项相同；包括M38分数乘法/裁剪、M37定点、旧整数/浮点族的性能记录也相同。LSU与公共顶层旧访存用例周期、请求数和RF读取计数相同。

下表为未布局的Yosys xcup映射与固定100ps/段条件预算。更深流水不等于更大吞吐；整数预设不包含FP，VLEN与VRF容量相同。

| 预设顶层 | FP | ALU分段 | LUT | FF | DSP | 条件ns |
|---|---|---:|---:|---:|---:|---:|
| SpinorStandard | FP32/64 | 32 | 21145 | 12734 | 9 | 3.292 |
| SpinorDeep | FP32/64 | 16 | 21070 | 12951 | 9 | 3.050 |
| SpinorInteger | 整数 | 32 | 11812 | 6179 | 1 | 3.292 |
| SpinorIntegerDeep | 整数 | 16 | 11845 | 6396 | 1 | 3.292 |

四个预设均通过定向公共接口RTL/网表测试；这不是各自完整ISA合规或器件300MHz签核。
