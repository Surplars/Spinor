# Orbital—Spinor 单指令提交协议 v1

本协议针对同一时钟域，先让部分RVV原型安全接入；不是完整Orbital集成或Linux支持声明。新VpuHostBoundary与公开顶层SpinorVpu配合使用，均为可综合Chisel模块。旧ValenceBoundary是早期算术边界，flush会直接丢弃所有者，不适用于当前LSU的延迟停止，不应当作访存SoC适配器。

## 连接

```scala
val spinor = Module(new SpinorVpu(monitorBase))
val boundary = Module(new VpuHostBoundary)
spinor.io.core.command <> boundary.io.command
boundary.io.completion <> spinor.io.core.completion
boundary.io.memoryStatus := spinor.io.memoryStatus
spinor.io.core.flush := boundary.io.vpuFlush
// Orbital/宿主驱动 boundary.io.offer/reply/head*/older*Drained/stop。
// SoC另接context/contextResult、物理RAM tl及monitor从端。
```

io.core的配置输出提供已提交CSR状态和访存前缀vstart，不能代替CPU的VS/FS/异常管理。跨时钟域必须另加完整异步事务桥。

## 接收与退休

1. offer携带原始32位instruction、64位scalar/scalar2/avl及80位token。CPU自己定义ROB索引、分配tag、epoch的打包，所有80位原样比较与返回，不能截断为旧Valence默认的69位。
2. 只有headValid、headToken完整匹配、旧标量访存与FP工作排空、边界空闲且无stop/协议错误时才转发command。CPU还必须先完成指令权限/VS/FS、源操作数和标量结果端口检查；这些由CPU负责，适配器无法推断。
3. command.fire后容量1，边界持有token/instruction/访存类别，直到reply.fire或算术取消。CPU即使进行前端恢复，也必须保留这个不可撤销所有者和PC/异常信息，不得把ROB槽复用于另一条指令。
4. reply.ready是最后提交授权，直接控制VPU completion.ready。普通算术/VSET/CSR的向量版本、CSR及标量结果必须与CPU同一握手边沿发布。completion.valid被阻塞时保持结果，不能先更新CPU寄存器再丢弃VPU结果。
5. reply带原Completion、memory、stopped、exception、cause、tval、原始LSU cause和element。它不是CPU独立退休器：最终异常优先级、PC、中断cause和全局退休由Orbital决定。host.head输入用于接收许可；接受后身份由内部owner保存。

## stop、访存和异常

stop直接传到Spinor flush。算术所有者被取消时，canceled.valid提供原80位token；该指令不产生reply，不提交候选结果。取消通知仅对本时钟域立即冲刷的当前算术流水有效；不能据此清尚在外部总线的store。

访存stop必须保留active，等待已发布的A/D排空以及memoryStatus/completion。当前LSU逐元素提交前缀和vstart，发出的store不可撤销。边界不会在stop时释放访存token，也不把stopped自动当作成功退休。stopped回复要求CPU保存原PC、前缀状态并决定中断/恢复；只有同意处理该返回时才能拉高reply.ready。stop恰逢已完全完成的指令可以得到普通完成，不能凭stop电平伪造interrupted状态。

非法指令映射exception cause=2、tval为零扩展原instruction；load原始LSU cause=4、store原始cause=6分别映射地址不对齐cause=4/6，其余当前LSU fault映射物理访问错误5/7（旧cause=1不再识别为不对齐）、tval为LSU地址。stopped没有伪造的中断cause，由CPU根据实际中断源决定。当前没有页故障/虚拟tval映射。异常/停止时禁止标量结果写回。vstart非零的归约非法，vstart保持原值。

completion必须与拥有的完整token和instruction匹配，访存必须同时提供memoryStatus，算术必须没有memoryStatus。无所有者、身份错误或元数据错位会置粘滞protocolError，阻止消费completion及接收新命令；不能通过“丢弃不匹配完成”来意外触发VPU版本提交。此错误属于集成协议错误，不是可向应用报告的正常非法指令。恢复需协调CPU/VPU/总线的停止、排空和联合复位，不能只重置适配器并重用token。

## context与Linux

context是独立调试/保存恢复端口，只能在CPU已排空且边界无所有者、VPU完全空闲后使用。不得与正常命令、恢复或monitor clear混为同一授权。monitor清零只清统计，不影响寄存器、CPU owner和总线。

原生RISC-V Linux还需VS/FS脏状态、向量CSR、512字节向量状态保存恢复、异常与保护/翻译/一致性，以及缺失ISA。ARM Linux若执行作业，需要另外的队列/代理，不能把monitor UIO当作计算驱动。实际Orbital仓库仍未被修改或联编。

## 已验证范围

tests/test_host_boundary.py使用模拟CPU/VPU对端，RTL和映射网表各验证256次事务：240次返回、16次算术取消；含128种原始cause/访存方向组合、6类失败关闭检查，以及错误head、标量访存/FP未排空、VPU反压、回复反压、访存stop、fault/illegal原因与80位高位身份。不是实际CPU数值程序或中断软件测试。`test_memory_boundary.py`另将真实LSU和真实宿主边界连接，RTL/网表各验证106例访问前故障、完整tval/身份和回复保持；不含RAM响应或实际Orbital。Spinor实际数值/访存由独立顶层回归覆盖。

M39增加vfmv.f.s标量FPR结果。成功Completion.writesScalar对f0也为真；CPU必须根据回显原指令解码FPR/GPR目标，不能直接将所有标量结果送入整数RF。SEW32结果已NaN-box为FLEN64。参数化整数配置移除FP CSR端口并拒绝FP指令；完整配置对外布局不变。

## M43访存操作数

单位步长与跨步指令均用`Command.scalar`传递解析后的rs1物理基址。跨步`vlse/vsse`用既有`scalar2`传递解析后的rs2有符号字节步长，完整64位捕获，元素地址按模2^64计算；指令rs2=x0时VPU强制零步长并忽略scalar2。rs2非零但值为零仍逐有效元素访问；当前x0也选择逐元素访问。标量寄存器依赖须由CPU先解决，不能在command握手后改变操作数。vsetvl原有scalar2传递vtype的用途保持，按原指令分别解释。

跨步与单位步长适用同一物理普通RAM、单事务和不可撤销所有者规则。vstart恢复仍传原基址而非已偏移地址；CPU需保留原PC/操作数直至故障或停止处理完成。未增加MMIO、VM/PMP或一致性能力。[实现和验证范围](m43-strided-memory.md)。

## M44索引访存

`vluxei/vloxei/vsuxei/vsoxei`用`scalar`传rs1基址，从指令vs2指定的向量组读取索引，忽略`scalar2`。vs2=v0是向量源，不是标量x0；无掩码时可以合法使用。索引EEW取指令编码，数据EEW=SEW；索引为零扩展字节偏移，不乘数据宽度，完整64位加法回绕。ordered和unordered在当前实现均按元素序发出/排空，保留单事务和前缀停止合同。仍不支持MMIO、VM/PMP或一致性。[范围和重叠规则](m44-indexed-memory.md)。

## M45整组与mask访存

整组`vl<n>re<eew>/vs<n>r`忽略当前VL和全部vtype（包括vill），按NREG×VLEN/EEW作为EVL；vstart按编码EEW的元素数解释，store编码EEW固定8。mask`vlm/vsm`仍尊重vill，传ceil(VL/8)个字节，vstart按字节解释。两者均vm1，允许v0作为普通数据，使用原始`scalar`基址并忽略scalar2，完成仅清零vstart而不改变VL/vtype/flags。错误/停止返回的element和vstart须按当前指令单位解释，不能一律当当前SEW元素。

保存完整上下文仍需CPU/驱动先排空并处理VS/FS、VL/vtype/vstart、FCSR和vcsr。保存或恢复VRF前须先在标量侧保存原vstart并清零，避免跳过头部；可用4组vs8r保存512字节VRF，再用4组vl8re64恢复；恢复原vstart应放在恢复指令完成之后。访存期间必须保留owner和PC直到completion，仍仅物理普通RAM，无VM/PMP/一致性。[M45规则](m45-context-memory.md)。

## M46分段访存

单位步长分段的VL/vstart以整段为单位；仅当该段全部字段完成才推进vstart。fault/stop允许当前段有字段前缀已写回，宿主须保留原PC和基址，从vstart对应段的字段0重启；已发store不可撤销，不能套用算术取消。当前仍只访问物理普通RAM。上下文保存/恢复和CPU异常处理不能丢弃部分段，见[M46规则](m46-segment-memory.md)。

## M47跨步/索引分段

沿用M46的整段vstart和部分字段重启策略。跨步的scalar2传完整有符号步长位模式，rs2=x0时忽略；索引形式忽略scalar2。索引分段load所有目标字段组都不得与vs2索引组重叠，同宽也保留，且VL0不能绕过检查。store可有同EEW源别名。旧NF0索引load合法重叠不受影响。仍由宿主保证物理普通RAM及不可撤销指令所有权，见[M47说明](m47-addressed-segments.md)。

## M48 FOF与VL

FOF元素0错误按原异常处理，原VL保持；后续元素错误则正常完成并缩短VL、清零vstart。CPU不能仅根据总线错误判断该指令要重试，须使用最终completion/status；FOF后的CSR读取和后续算术必须看到已提交的新VL。即使没有RF写回，VL缩短也改变向量架构状态，宿主仍须正确处理VS dirty。分段被截短的当前段可以保留已加载字段；不应把这些字段算入新的VL。停止保持原VL；同拍同步错误按FOF规则优先处理。调试watchpoint不能当作可截短的普通访问错误交给此接口。见[M48](m48-fault-only-first.md)。

## M49程序适配器

新增ELF测试执行器直接驱动公共VPU命令端，动态取指并使用实际VL/标量返回执行循环；它不经过真实Orbital，也未替代CPU退休边界、VS/FS或异常管理。程序回归通过不能作为本合同的整核集成验收。见[M49验证范围](m49-compiled-programs.md)。

## M50浮点广播与合并

`vfmv.v.f`及`vfmerge.vfm`使用`Command.scalar`接收FPR的完整FLEN64位模式，f0是有效源，不能套用x0取零。SEW32检查NaN boxing：高32位非全1时使用规范NaN；合法sNaN位模式按数据复制，不quiet、不增加fflags。合并的v0是选择数据，vm=0时全部body元素执行，非普通写掩码。仍在completion握手时发布候选RF版本，flush撤销；CPU负责FP权限/FS与向量脏状态。monitor实现ID更新为0x5001，ABI1和能力布局不变。

## M56 宿主管理 FCSR

原默认 standalone 接口保持；接入原生 Orbital 标量/向量共享 FCSR 时，选择
`SpinorParams(hostFcsr=true)` 或生成参数 `--fcsr-owner host`。此模式增加
`io.core.fcsrHost`，由 CPU 提供已提交 frm/fflags；VPU 锁存执行用 frm，返回当前
成功 FP 完成的逐指令 flags。CPU 只在 completion.fire 同边沿合并，不能在 valid
出现时提前合并。flags 更新与原 completion 使用同一 token/拥有者，不另发射或退休。

0x001/0x002/0x003 CSR 在宿主模式必须留在 CPU，转发到 VPU 会报非法，包括零源读。
上下文 helper 的 execute 回调也须相应路由；向量 CSR 与 VRF 仍由 VPU 负责。
权限、VS/FS dirty、全局退休和共享 FCSR 的顺序管理仍属于 CPU。monitor ID0x5602
标识宿主版，默认独立版保持0x5501。详细端口及验证限制见 [M56](m56-host-fcsr.md)。
