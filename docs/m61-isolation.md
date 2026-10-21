# 寄存隔离顶层接入（M61）

`SpinorIsolated` 在原有 `SpinorVpu` 外增加同一时钟域的寄存边界，目标是阻断CPU、VPU和总线之间贯穿的组合路径。旧顶层与旧提交协议保留；两种接口不能直接混接。

## 生成

```bash
./mill Vpu.runMain vpu.GenerateIsolated --out build/isolated --name SpinorIsolated --preset standard --fcsr-owner host --monitor-base 0xa0010000
```

支持standard/deep/integer/integer-deep，VLEN128/ELEN64和单lane保持。整数预设使用standalone FCSR选项。RAM窗口参数与旧生成器相同。SV和JSON清单标明 `interface=preview-grant-done-v1`，不能仅用monitor实现ID判断提交协议。

## 对外端口

| 端口 | 规则 |
|---|---|
| `offer: Decoupled[Command]` | CPU只提供已获资格的不可撤销队头指令；原80位token和操作数字段不变 |
| `preview: Valid[IsolatedResult]` | 已计算的结果预览，含VpuHostReply和逐指令FP flags；不是架构完成 |
| `grant: Decoupled[UInt80]` | 对当前preview的不可撤销发布授权，必须携带完整token |
| `done: Decoupled[IsolatedDone]` | 发布完成确认；含原预览包和发布后状态采样 |
| `stop` / `canceled` | stop先寄存；授权前算术可取消并返回token，memory仍排空并返回stopped结果 |
| `contextMode` | 寄存的仲裁模式：0允许offer，1允许context；切换不取消已接受操作 |
| `context` / `contextResult` | 64位块访问；结果改为可反压Decoupled，不能沿用旧Valid端口的握手代码 |
| `fcsrHost` | 仅host配置存在，输入CPU的frm/fflags；执行frm在外部offer.fire时采样 |
| `status` | 寄存后的状态观察，复位后valid才有效；不能代替done |
| `busy` / `protocolError` | busy覆盖指令/授权/完成保持/context；protocolError为封锁状态，需协调复位 |
| `tl` / `monitor` | 原A/D字段不变，四个方向分别通过非直通寄存切片 |

CPU侧不再连接旧`VpuHostBoundary`的reply握手。队头匹配、旧标量访存/FP排空、VS/FS和写回资源资格须在CPU发offer前检查；新顶层不实现CPU退休器。

## 发布协议

1. **offer.fire**：接收一条指令和操作数，host模式同时采样执行frm。
2. 核心执行；普通算术/VSET/CSR的候选状态仍未发布。捕获结果后输出稳定preview，此时核心completion.ready仍为0。
3. CPU检查结果及异常处理资源，发送匹配80位token的grant。授权之前可以等待或请求取消；授权之后保留PC、owner及退休槽，禁止年轻操作、上下文切换或恢复越过它。
4. grant token先寄存，再在本地比较身份；通过后执行核心completion握手，随后采样发布后的状态。
5. 输出done并在反压下保持。CPU在done.fire时消费标量结果、异常/停止状态与FP flags，随后才能复用owner。

从正确grant握手到最早done握手需4个周期，反压可延长。两次握手不是同一边沿；不能把grant当作旧reply.ready，或在看到preview时提前写CPU寄存器。

错误token或核心完成身份/元数据不一致会封锁，禁止错误发布。CPU不能凭预期拍数提前退休，必须等待实际done。正确授权后，stop不再撤销该指令；grant与stop同拍时grant优先。CPU若要处理取消，应在grant之前完成该决定。

## stop与访存

stop先经过寄存采样。未授权的普通算术可取消，候选版本不发布；canceled返回原token，随后不会再产生done。指令尚在输入寄存器时也可以按此规则取消。

访存已接受的A不能撤回，包括仍被fabric反压的寄存A。所有A/D缓冲均无flush丢弃路径；LSU先排空响应再返回preview，CPU仍须grant并消费stopped/fault的done来解除所有权。

待返回的load在stop后可以不写入该元素并保持原vstart；已发store的副作用则保留，推进前缀后从原基址恢复。分段、whole、mask和FOF的单位/错误规则沿用[访存协议](tilelink.md)。寄存隔离不提供回滚、MMU/PMP或缓存一致性。

## FCSR与上下文

host配置的逐指令flags随preview保存并随done返回；CPU只在done.fire且flagsValid时OR到自身fflags。不要用done.state.fflags覆盖CPU FCSR：该字段是在CPU合并本条flags之前的观察采样。status和done.state中的frm观察宿主已采样的frm，与offer时捕获、用于本条计算的执行frm分开；context期间也可正确观察宿主FCSR。FCSR CSR仍留在CPU，误转发会返回非法。

context前先排空owner和总线并获取软件独占；切换contextMode后等待实际ready。contextResult必须握手消费，不能只等待valid后立即复用设备。完整镜像仍为576字节，VRF仍为64个64位块。

移植portable helper时，保持软件独占覆盖整个操作：read/write块期间选contextMode=1；execute回调访问CSR/VSET时临时选0，完成preview/grant/done后再切换。contextMode是硬件端口仲裁，不代替软件锁；host模式的FCSR回调仍路由到CPU。

## 总线与monitor

每个方向使用容量1、非flow/非pipe寄存切片，支持任意反压，换取额外延迟与可能的空拍。当前单事务LSU保持，未增加指令并行度。

隔离顶层启用额外LSU几何译码寄存及短地址分段；整数隔离配置还在RAM窗口选择后增加操作数采样拍，将RAM读取与后续宽度掩码/符号扩展分开。指令结果和存储格式保持，执行延迟增加。版本化VRF继续使用RAM，不用全组触发器快照替代。

这些分级默认关闭：四种旧直接配置的完整生成SV与已验收版本逐字节相同。新增隔离配置单独重跑数值、分段故障、FOF和恢复测试，不能直接继承旧顶层的时序结论。

monitor A另有一拍控制值校验/规范化：有效control只有0/1/2，64位写入的高位非零仍拒绝，32位写入未使用的高32位仍忽略。校验发生在原始输入寄存之后，再把等价的小位宽控制送给旧monitor，避免64位比较成为新的寄存器间长链。

monitor内部ABI、地址和ID不变，外层A/D缓冲可暂存多条顺序请求，source随响应保留。monitor计数仍观察内层核心握手，completed不等于外部done或CPU退休；busy/status也需区分核心与外层owner。

复位须在全部接口静止或系统协调联合复位时进行。外层busy不包含独立monitor事务，不能仅据busy=0判断可以复位。跨CPU/总线时钟域仍须真正的异步事务桥，本顶层只做同频寄存隔离。

## 时序证据与边界

对四种生成配置的完整xcup映射网表，检查所有非clock/reset输入到全部输出的组合锥，并检查外部payload在输入寄存器之前没有进入组合逻辑。检查器包含故意旁路负控制；结果见[M61报告](../reports/m61/evaluation.md)。

这解决的是当前网表的结构隔离。CPU输出延迟、第一拍寄存器的建立时间、时钟不确定度、布局拥塞和器件布线仍需整机STA；不能承诺接入后物理Fmax完全不变。云端固定条件预算也不是实际300MHz签核。

原直接接口的连接步骤继续见[通用接入指南](integration.md)。
