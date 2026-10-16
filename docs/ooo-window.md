# 砺矢多指令调度实验 v1

当前生产原型仍为M17，RamVector一次拥有一条向量指令；整数元素可以重叠，尚不能让不同向量指令在真实执行单元中同时执行。这里新增独立VectorIssueWindow基础模块，不替换现有顶层。

## 当前实现

顺序接收指令，最多8项。四种执行类别共享一个发射口，每次选择最老且依赖已解除、单元可用的指令。选择经过寄存器，因此当前最大每2周期发射1条，不是双发射超标量。多个单元可以同时在途，完成可以乱序，只有队头完成才能退休。

入队时比较完整32个架构向量寄存器的读写集合，记录8位依赖表。RAW、WAR、WAW均保守等待较老指令退休，不需要寄存器重命名或结果前递。退休时清除所有指向该槽的依赖位，避免槽位复用产生错误依赖。配置、CSR、访存全部作为屏障，只能在队头执行，并阻止年轻指令越过。

128位指令描述符及8位外部tag保存在8项Mem中，本次Yosys映射11个RAM32M16；它们是分布式RAM，不是BRAM。每条指令的读写集合、依赖表、就绪状态保存在FF中，没有向量数据的整组FF副本。

完成接口只携带槽号和fault。真实结果、FP flags等需要后续由执行上下文保存；当前模块没有实际向量运算。complete只能在issue握手后的后续周期返回，且必须表示该指令所有候选写回已完成，retire才允许发布架构状态。fault只能按顺序退休，之后清除年轻项并进入drain。显式flush也进入drain；flushAck必须表示所有旧执行和访存副作用已取消或排空，ack后禁止再返回旧槽号的完成通知。模块没有CPU异常、PMP、VM、一致性或TL访存集成。

依赖输入由未来适配器负责正确解码：LMUL/EMUL每个组成员、掩码v0、旧vd读改写和所有第三源都必须纳入掩码。非法指令和影响配置/CSR的操作必须序列化。unitReady是可选择提示，执行通道最终以issue的ready/valid握手为准；反压期间issue保持槽号和描述符，flush/异常取消除外。复位必须同时复位所有外部执行单元。

## 测量范围

10000周期独立Python顺序列表参考模型，含随机单元延迟、反压、队列回绕、同时退休/入队、RAW/WAR/WAW、屏障、flush及fault。RTL及映射网表测试逐周期核对握手、发射描述符、队头退休及占用，均通过。该模型记录925条接收、515条发射、290次退休（含6次fault）、342次非队头发射、146次乱序完成、79次flush、6次fault退休，最多4个模拟执行单元同时在途。被flush/fault取消的指令不应计作退休。

这不等于实际VPU的性能基准，也没有证明完整OoO机器的精确异常。当前只是调度器的有限随机验证，未作调度器全状态形式化证明。M17的数值单元、RF、LSU及其所有既有源码/证据保持原散列。

初版发射时重复比较依赖，4000 LUT、589 FF；改为入队记录依赖后972 LUT、653 FF，RAM32M16仍11个。独立调度器条件预算由3.609/4.459/6.159ns降至2.809/3.459/4.759ns（假设每段连线50/100/200ps）。这不是与M17全VPU的直接比较，也不能把两个独立预算相加当成集成后的时序。没有器件布局布线或-2速度校准，不能确认300MHz。

## 复现

在M17工程根目录应用实验附加包，使用相同工具缓存和Java21：

```bash
./mill Vpu.runMain vpu.GenerateIssueWindow build/rtl/VectorIssueWindow.sv
python3 tests/test_issue_window.py
python3 scripts/synth.py VectorIssueWindow
python3 tests/test_issue_window.py --mapped
python3 scripts/path_depth.py VectorIssueWindow
python3 scripts/cloud_budget.py --top VectorIssueWindow --netlist build/synth/VectorIssueWindow/mapped.json --output build/timing-budget/issue-window
python3 scripts/report_issue_window.py
```

## 接入顺序

1. 从单条指令FSM拆出每条指令的元素进度和提交上下文，保存在小型RAM表。增加slot到执行、读操作数和写回仲裁的所有权关联。
2. 保留共享向量RF，实现读写端口仲裁和候选区域独占；保持依赖指令等待退休。先演示真实FP与独立整数指令重叠，并验证数值、flags、别名和flush。
3. 将真实完成接到顺序退休，只有队头发布版本/CSR。访存继续使用屏障和现有延迟停止合同，不能推测发布store。
4. 优化选择/扇出，再评估2路发射。双发射需要额外仲裁和带宽；同时评估寄存器重命名是否值得，而不是直接复制多份完整VPU和RF。

现阶段优先第1、2项；FP64舍入优化仍是后续独立工作。
