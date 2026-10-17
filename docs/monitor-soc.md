# SoC monitor ABI v1 与接入边界

当前公开顶层为SpinorVpu（兼容类LishiVpuMonitored），将M18数值/访存数据通路与VpuMonitor连接起来。它保留core命令、context、completion及memoryStatus，另有两个方向不同的TL接口：tl是访问物理RAM的主端；monitor是Linux可读写的4KiB监控从端。两者不共享背压。实验乱序窗口不在此顶层内，真实指令容量仍为1。

## Linux能做什么

通过MMIO读取能力、忙闲状态、运行计数、错误记录和原子快照。software/monitor提供寄存器头文件、设备树示例和Linux UIO用户态工具。这里使用Linux现有通用UIO驱动，不是已完成的专用内核驱动，也不提供submit ioctl、进程隔离、向量上下文切换或Linux用户态RVV执行支持。宿主可以是能访问该MMIO区域的ARM PS或RISC-V Linux，前提是SoC总线桥已正确连接。

容量指架构向量寄存器文件：32×128bit=512字节，ELEN64，最大LMUL8；不是DMA缓冲区/显存，也不是所有物理候选副本的RAM资源总量。caps明确标记部分ISA，禁止据此发布misa.V/RVA23合规。busy并不等于实际算术利用率，completed是VPU完成握手，不是CPU架构退休；不能据此直接推算GFLOPS。

## 寄存器

小端，每项8字节；只读项支持自然对齐的8/16/32/64位Get。控制寄存器仅支持对齐到低半部的32/64位PutFull/PutPartial，mask必须覆盖该访问全部字节。32位写的未选中高32位被忽略。所有请求必须param=0、corrupt=0。非法地址/大小/mask/写只读/原子操作返回denied，不产生副作用。一次一个响应，D背压时全部响应字段保持稳定。

| 偏移 | 内容 |
|---|---|
| 0x00 | Magic 0x4c495348 |
| 0x08 | ABI 0x00010000，major=1 |
| 0x10 | 实现ID 0x3601：M36整数乘加/比较/整组搬运数据通路加monitor ABI1 |
| 0x18 | caps=0x3ffffff：bit0 monitor、1物理LSU、2 FP32、3 FP64、4 context端口、5部分ISA、6单宽整数归约、7掩码逻辑、8整数标量搬运、9掩码计数/首置位、10前缀掩码、11 viota/vid索引生成、12整数滑移、13 gather（含EI16）、14 compress、15单宽FP归约、16宽化整数归约、17宽化FP归约、18整数零/符号扩展、19窄化整数移位、20宽化整数加减、21宽化整数乘法、22单宽整数乘加、23宽化整数乘加、24反减/大于比较、25整组搬运；没有完整RVV/乱序/一致性声明 |
| 0x20 | [15:0] VLEN128、[31:16] ELEN64、[47:32]寄存器32、[63:48]真实指令容量1 |
| 0x28 | [31:0]架构VRF字节512、[39:32]最大LMUL8；其余保留 |
| 0x30 | 计数宽度32；Tiny验证模块为8，非生产接口 |
| 0x38 | 实时状态：bit0 busy、1拥有访存指令、2已接受TL A尚未收到D、3拥有指令、4快照有效、5计数器存在、6任一计数回绕粘滞、7错误粘滞 |
| 0x40 | 写1原子快照，写2仅清monitor，写0无操作；其他值denied；读0 |
| 0x48 | 32位快照序号，每次快照加1；monitor清零不改序号 |
| 0x50/58/60/68 | 实时最后错误：[15:0]cause、[23:16]element；地址；token低64/高16。非法指令cause=0x100，访存cause沿用LSU |
| 0x70/78 | 实时vtype/config |
| 0x100+8*i | 第i个计数器的快照，32位零扩展为64 |
| 0x180/188/190 | 同一次快照的status/vtype/config |
| 0x198/1a0/1a8/1b0 | 同一次快照的错误cause+element/address/token低64/高16 |

config位布局：[7:0]vl、[14:8]vstart、[16:15]vxrm、bit17 vxsat、[20:18]frm、[25:21]fflags。错误记录仅在消费completion时更新；完成端口被阻塞期间不会重复累计错误。

计数器i=0..12依次为：cycles、busy_cycles、memory_owned_cycles、accepted、completed、canceled、illegal、memory_fault、memory_stop、tl_a、tl_d、command_stall、completion_stall。A/D计数只统计向量数据访存端口，不把monitor轮询算作向量流量。memory_owned_cycles含访存completion等待软件接收的时间；busy含context访问等核心占用，并非只计执行单元活跃。

算术flush取消拥有的指令且只计一次；访存flush是延迟停止，要排空已发布的请求并返回completion，计作memory_stop而不是canceled。completed包含非法、fault和停止返回，不直接等于成功指令数。

快照在控制A握手边沿捕获该边沿之前的所有计数、状态与错误，之后计数继续。对应边沿新发生的事件进入下一快照；snapshot status中的bit4反映采样前有效位，因此首个快照可能为0，软件应检查实时0x38的有效位及序号。读不清零。写2同时清实时/快照计数和错误，置快照无效，但不会停止VPU、撤销store或清向量状态；清零优先于同一边沿的计数/错误事件。这是有意的统计区间边界。

32位计数按模2^32回绕，软件差值用uint32_t减法，并在驱动中累计成64位。300MHz下cycles约14.3秒回绕；建议每秒采样，实际允许间隔取决于真实时钟，不能跨过一整圈。monitor和VPU时钟关闭时不计数，睡眠/时钟门控期间不能简单用墙钟作忙闲百分比分母。利用率用相邻快照delta_busy/delta_cycles，分母为0时报告不可用。硬件不报告未经测量的“300MHz实际运行频率”。

## 接线与软件

monitor与VPU共用时钟/复位。跨时钟必须经过正规的TL异步桥，不能直接接引脚。仅实现TL-UL A/D单拍，source宽4位；SoC互连需适配source ID和总线宽度。默认monitor基址为0，要求互连提供相对地址；若互连保留完整物理地址，请按实际基址重新生成，例如：

```bash
./mill Vpu.runMain vpu.GenerateMonitor build/monitor/rtl 0xa0010000
```

设备树示例的地址不是最终分配，必须与TL解码和生成参数一致。该MMIO区域必须映射为设备/非缓存内存。需要CONFIG_UIO、CONFIG_UIO_PDRV_GENIRQ，某些内核需要uio_pdrv_genirq.of_id=generic-uio启动参数。首版没有中断，使用轮询。确认/sys/class/uio/uioN/name为lishi-vpu-monitor，而不是假定固定uio0。

```bash
gcc -std=gnu11 -O2 -Wall -Wextra -Werror software/monitor/lishi_monitor.c -o lishi-monitor
sudo ./lishi-monitor /dev/uioN
```

工具以volatile 32位设备访问和内存屏障触发快照、验证有效位/序号、读取JSON；--read-snapshot读取已有快照，用于离线夹具或独占的已冻结快照。flock仅约束合作访问者；同一硬件必须只由一个驱动/监控服务拥有，不能同时用/dev/mem或另一内核驱动更改快照。重置、热拔出、时钟门控由SoC平台负责，UIO工具不提供运行时电源管理。对Linux用户授权前应限制设备节点权限；当前错误token与地址属于调试信息。

PS ARM与PL RISC-V可以复用同一ABI及工具。若两个Linux同时运行，能力和实时只读状态可并行读取，但快照/clear应只有一个写入所有者；flock不能跨两个内核互斥。v1没有硬件锁，需要SoC mailbox/所有权协议或单一监控服务来协调；另一侧可用--read-snapshot并核对序号，快照被覆盖时重试。两边的计算提交入口不同：PL RISC-V未来接原生向量指令；ARM未来需要命令队列或PL RISC-V代理。当前monitor不包含这些计算入口。

## 离“完整、可跑Linux向量程序”还差什么

1. ISA仍缺完整整数分组、归约/排列/宽窄运算及完整访存模式等，须按指令矩阵补齐并做架构差分；monitor不改变这个范围。
2. 当前core命令只能由CPU的不可撤销ROB队头提交，旧标量访存已排空；80位token必须原样保留，访存stop期间不能丢失所有权。现有Valence仓库尚未接入。
3. 访存只支持固定物理普通RAM窗口，默认0x80000000起256MiB，没有地址翻译/PMP/缓存一致性。不能把Linux用户虚拟地址直接送入该LSU。CPU和SoC必须补齐保护、翻译、栅栏与精确异常，或者明确采用受限的物理缓冲区加速器协议；后者当前也没有作业提交驱动。
4. CPU需实现向量CSR和VS/FS状态处理、上下文保存恢复、异常/中断、指令退休授权。monitor不是向量寄存器访问端口，不解决这些事项。

近期优先单指令SoC接入闭环和ISA功能，OoO/双发射继续留在独立实验中。物理时序仍需要后续Vivado确认，云端预算仅作参考。
