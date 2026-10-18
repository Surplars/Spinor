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

非法指令映射exception cause=2、tval为零扩展原instruction；原始LSU cause=1映射load/store地址不对齐cause=4/6，其余当前LSU fault映射物理访问错误5/7、tval为LSU地址。stopped没有伪造的中断cause，由CPU根据实际中断源决定。当前没有页故障/虚拟tval映射。异常/停止时禁止标量结果写回。vstart非零的归约非法，vstart保持原值。

completion必须与拥有的完整token和instruction匹配，访存必须同时提供memoryStatus，算术必须没有memoryStatus。无所有者、身份错误或元数据错位会置粘滞protocolError，阻止消费completion及接收新命令；不能通过“丢弃不匹配完成”来意外触发VPU版本提交。此错误属于集成协议错误，不是可向应用报告的正常非法指令。恢复需协调CPU/VPU/总线的停止、排空和联合复位，不能只重置适配器并重用token。

## context与Linux

context是独立调试/保存恢复端口，只能在CPU已排空且边界无所有者、VPU完全空闲后使用。不得与正常命令、恢复或monitor clear混为同一授权。monitor清零只清统计，不影响寄存器、CPU owner和总线。

原生RISC-V Linux还需VS/FS脏状态、向量CSR、512字节向量状态保存恢复、异常与保护/翻译/一致性，以及缺失ISA。ARM Linux若执行作业，需要另外的队列/代理，不能把monitor UIO当作计算驱动。实际Orbital仓库仍未被修改或联编。

## 已验证范围

tests/test_host_boundary.py使用模拟CPU/VPU对端，RTL和映射网表各验证128次事务：112次返回、16次算术取消、6类失败关闭检查，以及错误head、标量访存/FP未排空、VPU反压、回复反压、访存stop、fault/illegal原因与80位高位身份。不是实际CPU数值程序或中断软件测试。Spinor实际数值/访存由独立顶层回归覆盖。

M39增加vfmv.f.s标量FPR结果。成功Completion.writesScalar对f0也为真；CPU必须根据回显原指令解码FPR/GPR目标，不能直接将所有标量结果送入整数RF。SEW32结果已NaN-box为FLEN64。参数化整数配置移除FP CSR端口并拒绝FP指令；完整配置对外布局不变。
