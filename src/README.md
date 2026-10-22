# 源码导航

所有 Chisel 源码按职责放在 `main/scala/vpu/`。Scala 包名仍为 `vpu`，所以既有 `vpu.SpinorVpu`、`vpu.SpinorIsolated` 和 Mill `runMain` 命令继续有效。目录分类不改变生成的硬件层次。

```text
main/scala/vpu/
  top/                 公共顶层与核心组合
  config/              规模预设、固定参数、配置译码
  interface/           命令/完成/context协议与直接提交边界
  core/                向量指令控制、元素调度、提交
  memory/              LSU、寄存器RAM、几何与元素选择
  bus/                 TileLink字段与单事务桥
  monitor/             独立MMIO观测端口
  execute/
    integer/           整数ALU、乘除法、位操作、掩码扫描
    fixed/             定点、舍入与饱和运算
    fp/                浮点、格式转换及分段HardFloat运算
  util/                组合算术辅助函数
  generate/            当前公开RTL生成入口
    sim/               FIRRTL/GSim导出
    proof/             等价性验证顶层
    legacy/            历史里程碑与多顶层导出
  experimental/        未接入公共顶层的历史原型与调度实验
```

建议先读 [SpinorIsolated](main/scala/vpu/top/SpinorIsolated.scala) 和 [Protocol](main/scala/vpu/interface/Protocol.scala)，再看 [RamVector](main/scala/vpu/core/RamVector.scala)、[VectorMemoryEngine](main/scala/vpu/memory/VectorMemoryEngine.scala) 与具体执行单元。直接接入顶层为 [SpinorVpu](main/scala/vpu/top/SpinorVpu.scala)。

`generate/proof/`、`generate/legacy/`、`experimental/` 参与 Scala 编译，只有被所选顶层实例化的模块才进入生成 RTL。不能从文件存在推断该功能已接入生产顶层。

新增或移动源码时更新[目录映射](../scripts/maintenance/source-layout.json)，运行 `make check`。注释和评审约定见[开发规范](../docs/development.md)，时序、接口与验证范围见[验证说明](../docs/validation.md)。
