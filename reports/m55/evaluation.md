# M55：Zvbb 位操作实现与当前硬件回归

四种预设均实现 10 类操作、16 种 Zvbb 编码；VLEN128/ELEN64、单 lane、单指令在途。
循环移位和计数按三级寄存，ALU 的 6/7 拍、II=1 保持，RAM/TileLink/上下文 ABI 保持。
monitor 实现号 0x5501，生成 manifest 明确列出 zvbb。详见 [设计与边界](../../docs/m55-zvbb.md)。

## 功能证据

- 新增集合每预设 **7,108 条公共端口 Spike 差分命令**；四预设共 28,432 条。
  数字包含配置/CSR 命令。规范内 16 种编码均有成功样本：普通操作覆盖 22 种合法
  SEW/LMUL 几何，扩宽左移覆盖 ELEN64 下 15 种可执行几何；边界还有掩码、VL0、
  立即数 0/31/32/63、移位高位忽略、源/目的重叠、未对齐和非法目的 EMUL。
- 当前 M55 顶层重新执行基础算术/访存/扩展边界/half，加上新增 Zvbb，共
  **101,584 条 Spike 差分命令**。每条比较全部 32 个向量寄存器和 CSR，访存
  比较 8KiB RAM、TL 事务与故障信息。Deep 的基础算术/访存使用有界 compact 矩阵，
  edges、half、Zvbb 保持完整定义。391 种目录编码各有成功样本，非合规百分比。
- 每预设独立 Python 重启/规范策略：**1,448 场景、4,344 命令**，其中 1,408 个
  非零 vstart 场景和 40 个 v0 混合 EEW 源别名拒绝场景。该矩阵不标为 Spike 比较。
  同时重跑原有 mixed-EEW store 72 场景/216 命令每预设。
- 每预设公共顶层 **3,536 个 flush 时点**（16 编码×221 时点），每次比较全部
  64 个 RF 字、CSR、无过早/残留完成和无 TL 流量，含 held completion 阶段。
- 独立 Python 数值/精确周期模型：三种 ALU 各 18,969 拍，
  含每个新增 ALU 选择码全部 256 个字节输入，SEW8/16/32/64 和随机流、队列反压/flush。
  真实 Yosys 网表的两个分段 ALU 各 3,909 拍，字节穷举保留，
  其他边界/随机部分采用有界子集；不称为全操作数穷举。
- 局部 bit pipeline 对直接按位语义的 10 步 SAT 等价，任意 held 64 位输入、全部
  4 个 SEW、8 个旁路操作，拆成 32 个证明；每个单独证明第 8 步 done，避免空过。范围不包含
  整个 VPU、动态输入流或系统调度，andn/vwsll 另由数值/差分和网表测试覆盖。
- 浮点宽度控制前移后，两种分段顶层各执行 141 条独立 SV/SoftFloat 转换回归，
  含 nonzero vstart、half 和 flush。宽矩阵的旧单元证明保持历史版本，不冒充本轮重跑。
- 上下文 **2,212 场景、1,104 个前/后效果失败注入**，保留 ASan/UBSan
  校验和 576 字节 ABI；四预设监控 ID/反压、两个整数预设各 320 个禁用 FP 拒绝点。
  上述测试合计 **124 次比较器数据/标记/状态/上下文错误注入**均检出。

独立参考语料可以复用 M54 的不可变 Spike/SoftFloat 结果，DUT 模型/执行均是 M55；
不是旧硬件 trace replay。新增 Zvbb 启用字符串 rv64gcv_zvfhmin_zvbb_zvl128b，
上游语义和库未修改；原始编解码/语义文件核对 pinned Spike 源码散列。

首次把所有 SEW/操作合在一个 SAT 问题中，运行 180 秒超时，未计为通过；
改按固定 SEW/操作拆解，并用数学上的平衡逐位求和表达 popcount，32 个独立
有界问题全部通过。原超时脚本、wrapper 和日志在 proof-attempt 保留。

## 资源与时序

Yosys xcup 默认公共顶层：**24,184 逻辑 LUT、13,888 FF、9 DSP**，较 M54
+957 LUT/+529 FF；RAM64M8×32、RAM32M16×6 不变。完整 Integer/Deep 预设未据此
宣称独立器件 PPA，两个独立分段 ALU 有各自真实网表数值验证。

初次公共顶层固定预算 3.368ns 未过；寄存 FP 宽度/转换模式后重新综合：
公共顶层 **3.292ns**，计算/访存顶层 **3.232ns**，均≤3.333ns。失败诊断保留在
pre-width-stage-gate.txt；它不是最终通过证据，最终网表和固定门槛由 receipt 绑定。
预算权重与 M25 相同，100ps/link，DSP 影响端点排除、无布局布线、未按 -2 校准，
不是 STA/SDF。**M55 实际 300/500MHz 未知**，M53 本地 OOC 时序不自动适用新 RTL。

## 程序、缺口与复现

Clang19 汇编真实 strip-mining 位特征/扩宽移位例程，核对目标文件中 10 类实际
Zvbb match/mask 编码。固定 Clang19 未提供尝试的 C intrinsic 名称，固定 Binutils
也不识别全部新助记符，因此通过独立上游编码表核对机器字；不伪造编译器支持。
这是编译/编码检查，不是 Orbital/Linux 程序运行。

完整 V 的系统/异常审计、Zvkt、CPU 退休和 VS/FS/FCSR、地址保护/翻译、一致性和
Linux 驱动仍待推进；完整 Zvfh/BF16/crypto、多 lane/大 VLEN 不在当前声明范围。

变更前 M54 证据核验通过并冻结 50 个 Scala 文件及当时 README/CURRENT/.gitattributes。
旧源码按 archive/m53、archive/m54 精确散列核验，其余工具/产物保持；新产物位于
build/m55。已有 M54 工具和参考产物的环境中运行：

```bash
python3 scripts/verify_m55.py
python3 scripts/verify_m55.py --check-only
```

receipt 绑定当前源码、独立参考/语料、生成模型/RTL/网表、所有运行日志和固定预算。
没有部署、bitstream、板上运行、整核 difftest 或实际 Linux 上下文切换声明。
