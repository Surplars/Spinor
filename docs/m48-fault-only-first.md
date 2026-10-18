# M48：fault-only-first 加载

新增4种`vle8/16/32/64ff.v`和28种`vlseg2…8e8/16/32/64ff.v`，共32种编码。FOF只用于单位步长load；store的相同lumop仍为保留编码。跨步/索引寄存器号16仍是普通操作数，不会被误判为FOF。VLEN128、ELEN64、单lane、单指令/单事务在途以及物理普通RAM范围保持。当前主要基础V访存族已有实现，仍须完成编码审计、独立架构差分、编译器程序、异常与SoC集成验证，不能据此声明完整V或RVA23。

## 异常、掩码和重启

判断依据是**绝对元素编号**，并非第一个实际执行的元素。元素0任意字段发生同步访存错误时，原VL保持并报告原有异常、tval和vstart。元素大于0发生同步访存错误时，抑制该异常，将VL缩短为该元素编号，vstart清零，返回普通完成。mask关闭元素0或vstart非零也遵守这个规则。全部mask关闭、VL0和vstart≥VL时不访存，原VL保持。

分段FOF以整段计VL/vstart；同一段已完成字段保留，包括被截短段中的字段前缀，这是本实现选择的规范允许行为。错误字段和后续字段不写回。元素0中途出错可以从该段字段0重启；后续元素出错已正常完成，不应按普通fault重试。数据的prestart、masked和tail采用保留策略，截短段中已写入的字段除外。[规范摘录](references/m48-fof-v1.0.txt)。

停止/中断保留原VL，返回vstart供重启。已发请求先排空；同步响应错误优先于同拍停止。后续元素的错误若同拍遇到停止，选择FOF截短并正常完成，不输出interrupted；宿主仍可在指令之后处理待决中断。当前接口把denied/corrupt、错token和桥接协议/local错误统一映射为load访问错误；在该既有物理RAM错误契约下应用FOF。没有调试watchpoint异常输入，不能把调试事件编码成这些可被FOF抑制的访存错误。仍不支持非幂等MMIO、虚拟地址或PMP/缓存一致性。

## 原子VL提交和RAM

`MemoryRamVector`只包装访存专用的`RamVector`实例，在原`memoryCommit`握手上附带`memoryVl`的Valid元数据；同一次提交原子更新VL和vstart。公开SpinorVpu命令、context、monitor和TileLink接口不变。纯算术`RamVector.scala`及其生成接口不修改，算术证据仍按精确依赖与生成RTL散列核对。

LSU在终止错误后复用原length寄存器暂存缩短值，仅增加FOF/trim控制位，不增加8/64位数据银行、RAM、RF端口或DSP。单字段FOF也走一字段segment路径，共享EMUL、vtype和分段合法性检查。截短值与进度在背压下保持，VL在completion有效前已提交，completion背压期间也不能变化。现有非FOF单位步长、跨步、索引、整组/mask和分段指令继续回归。

## 验证与边界

独立LSU参考模型逐命令核对64个RF块、完整64位地址、错误字段前缀和精确trim握手。覆盖32编码、全部合法SEW/EMUL、分数/整数分组、v0/v31、mask关闭元素0、非零vstart、VL0、五类响应错误、物理窗口边界、首条冷启动、停止和错误竞争；完整/精简RTL及网表均保留独立oracle。

实际RAM/TileLink检查架构VL、VL CSR读取、截短后连续加载、元素0的字段故障重试、四类TL错误和两种ALU分段。完整RTL核对32寄存器，精简保留数据组、v0和保护寄存器，停止用例始终核对全部32寄存器。公共顶层以字面量验证三字段部分段截短和紧接的vadd、首段故障、masked元素0、非零vstart的本地故障，以及普通load不继承FOF模式。四预设使用物理RAM窗口尾部的单字段/两字段加载验证真实VL截短及其CSR读回；总线访问次数另行强制检查。真实LSU/宿主边界另覆盖全部32编码的元素0访问前错误。

monitor实现ID为0x4801，ABI1.0/能力位布局保持。工具为Mill/Chisel、Yosys xcup、Icarus和RapidWright固定家族表参考；M25的权重、100ps/link与3.333ns门槛保持。未布局布线、未按ZU15EG-2校准，排除DSP时序；未运行Vivado/SDF，实际300/500MHz未知。见[评估](../reports/m48/evaluation.md)、[性能](../reports/m48/performance.md)和[完整性计划](rvv-completion-plan.md)。
