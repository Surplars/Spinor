# M50 程序周期参考

沿用M49标量测试适配器与单事务TileLink反压模型，全部在M50硬件上重跑。不是Orbital IPC或实际应用性能。

| 矩阵 | 调用 | VPU命令 | TL请求 | 适配器周期 |
|---|---:|---:|---:|---:|
| SpinorStandard-compact-rtl | 56 | 184 | 1314 | 25637 |
| SpinorStandard-compact-mapped | 56 | 184 | 1314 | 25637 |
| SpinorDeep-compact-rtl | 56 | 184 | 1314 | 25712 |
| SpinorDeep-compact-mapped | 56 | 184 | 1314 | 25712 |
| SpinorInteger-compact-rtl | 50 | 154 | 1284 | 24505 |
| SpinorInteger-compact-mapped | 50 | 154 | 1284 | 24505 |
| SpinorIntegerDeep-compact-rtl | 50 | 154 | 1284 | 24580 |
| SpinorIntegerDeep-compact-mapped | 50 | 154 | 1284 | 24580 |
| SpinorStandard-full-rtl | 349 | 9459 | 56330 | 1229544 |
| SpinorInteger-full-rtl | 309 | 6569 | 51806 | 1076747 |
