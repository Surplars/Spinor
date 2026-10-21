# MMIO monitor 接入与 ABI

`SpinorVpu.io.monitor` 是独立的4 KiB TileLink A/D 从端，用来读取能力、忙闲状态、计数器和错误记录；`io.tl` 则是 RAM 访问主端。monitor 轮询不计入向量数据流量，两个端口各自处理反压。

monitor 与 VPU 共用时钟/复位，无中断。跨时钟或其他总线协议需要系统桥接。它不包含计算提交入口、向量寄存器读写接口或作业驱动。

使用[M61寄存隔离顶层](m61-isolation.md)时，monitor的ABI和ID保留，但A/D多了寄存缓冲。计数器仍记录内层核心事件，`completed`不等于外部`done.fire`或CPU退休；外层`busy`不包含独立monitor事务。复位前须排空所有接口，不能只看其中一个busy位。

## 地址和标识

生成时通过 `--monitor-base` 指定4 KiB对齐地址。若互连保留完整物理地址，使用实际基址；若互连减去窗口基址，生成基址用0。设备树和软件映射必须匹配。

| 偏移 | 当前内容 |
|---|---|
| `0x00` | Magic `0x4c495348`，保留兼容的 LISH 标识 |
| `0x08` | ABI `0x00010000`，major 1、minor 0 |
| `0x10` | standalone ID `0x5501`；host FCSR ID `0x5602` |
| `0x18` | 完整浮点配置 caps=`0xffffffff`；整数配置=`0xfffd7ff3` |
| `0x20` | [15:0] VLEN128、[31:16] ELEN64、[47:32]32个寄存器、[63:48]指令容量1 |
| `0x28` | [31:0]架构 VRF 字节数512、[39:32]最大 LMUL8 |
| `0x30` | 生产计数器宽度32位 |
| `0x38` | 实时 status |
| `0x40` | control：写1快照、写2清统计、写0无操作；读0 |
| `0x48` | 快照序号；每次快照加1，clear不改变序号 |
| `0x50/58/60/68` | 实时错误 cause+element、address、token低64/高16 |
| `0x70/78` | 实时 vtype/config |
| `0x100+8*i` | i=0..12 的计数器快照 |
| `0x180/188/190` | 同次快照 status/vtype/config |
| `0x198/1a0/1a8/1b0` | 同次快照错误 cause+element/address/token低64/高16 |

以生成 JSON 和当前 [VpuMonitor.scala](../src/main/scala/vpu/VpuMonitor.scala) 为准。caps bit5保留“部分ISA”标记；能力位不等同于完整 V/RVA23/Zvkt 合规。整数配置清除 FP32、FP64、单宽FP归约及宽化FP归约位。最小FP16转换/Zvbb等细分范围另见[ISA表](isa-coverage.md)，不能只由32个旧能力位推断。

caps位0..31依次为：monitor、物理LSU、FP32、FP64、context、部分ISA、整数归约、mask逻辑、整数标量搬运、mask计数/首置位、prefix、iota/vid、整数slide、gather/EI16、compress、FP归约、宽化整数归约、宽化FP归约、整数扩展、窄化移位、宽化加减、宽化乘法、单宽乘加、宽化乘加、反减/大于比较、整组搬运、carry/borrow、饱和加减、平均加减、舍入右移、vsmul、vnclip。

## 访问与快照

寄存器小端、每项8字节。Get支持自然对齐的8/16/32/64位读取；control仅支持从低半部开始、覆盖全部访问字节的32/64位PutFull/PutPartial。param必须0、corrupt必须false；非法地址、mask、原子操作或只读项写入返回denied且无副作用。一次一个D响应，反压时保持全部字段。

快照在control A握手边沿捕获该边沿前的状态；之后实时计数继续。软件读取序号和snapshot-valid，读取快照数据后再次核对，避免被其他写者覆盖。clear只清monitor统计/错误，不清VRF、CPU owner、总线事务或快照序号。

status bit0..7依次为busy、访存指令拥有者、已发A尚未收到D、指令拥有者、快照有效、计数器存在、计数回绕粘滞、错误粘滞。

config位：[7:0]VL、[14:8]vstart、[16:15]vxrm、bit17 vxsat、[20:18]frm、[25:21]fflags。错误字：[15:0]cause、[23:16]element；非法指令cause=`0x100`，访存错误沿用LSU cause。错误仅在消费Completion时记录。

计数器顺序：cycles、busy_cycles、memory_owned_cycles、accepted、completed、canceled、illegal、memory_fault、memory_stop、tl_a、tl_d、command_stall、completion_stall。completed表示VPU完成握手，包含非法/fault/stopped，不等于CPU成功退休数；busy也不是算术利用率。512字节指架构VRF，不是DMA缓冲容量或所有物理候选副本总量。

32位cycles在300MHz约14.3秒回绕，建议每秒或更快采样，以模2^32计算差值。详细定义见[软件头文件](../software/monitor/lishi_monitor.h)。

## Linux UIO 观测

设备树例见 [lishi-monitor.dtsi](../software/monitor/lishi-monitor.dtsi)，地址需要按系统修改。配置通用UIO及 `UIO_PDRV_GENIRQ`；有些内核还需 `uio_pdrv_genirq.of_id=generic-uio`。MMIO映射为设备/非缓存内存，首版轮询，无中断。

在目标Linux或匹配的交叉编译环境中构建，确认 `/sys/class/uio/uioN/name`，再运行：

```bash
gcc -std=gnu11 -O2 -Wall -Wextra -Werror software/monitor/lishi_monitor.c -o lishi-monitor
sudo ./lishi-monitor /dev/uioN
```

工具触发快照并输出JSON；`--read-snapshot`只读取已有快照。它使用Linux通用UIO，尚不是专用计算驱动，没有submit ioctl、进程隔离或上下文调度。宿主可以是能访问此MMIO窗口的任一处理器。

同一硬件只应有一个快照/clear写入所有者。flock只协调同一内核下的合作进程，不能跨两个Linux内核互斥；多宿主须另设mailbox或所有权协议。只读观察者可核对序号后读取已有快照。平台负责时钟门控、复位与设备移除期间的访问协调。

历史ID和能力演进保存在[整理前说明](../archive/docs-m60/source/docs/monitor-soc.md)，不作为当前配置检测依据。
