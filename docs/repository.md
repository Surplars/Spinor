# 构建与仓库说明

公开硬件入口为 `vpu.SpinorVpu` 和寄存隔离顶层 `vpu.SpinorIsolated`，工程使用 Mill；构建定义见 [build.mill](../build.mill)，固定工程工具见 [tools.lock.json](../tools.lock.json)。

## 开发环境

准备Linux x86-64、JDK21、Python3.12+、GCC和Make。Windows可使用WSL2完成Chisel构建，生成的SV可交给Windows Vivado。Python版本须支持bootstrap使用的安全tar解包接口。

```bash
make bootstrap
./mill Vpu.compile
./mill Vpu.runMain vpu.GenerateConfigured --out build/configured --name SpinorVpu --preset standard
```

bootstrap下载并核验固定Mill和OSS CAD Suite；首次构建还会解析Maven/Chisel依赖。依赖包和解压结果需要额外磁盘空间。生成配置、RAM窗口与host FCSR参数见[接入指南](integration.md)。

需要单独的CPU提交边界时生成：

```bash
./mill Vpu.runMain vpu.GenerateHostBoundary build/configured/VpuHostBoundary.sv
```

生成器可拆分辅助文件；将所选输出目录的相关SV一并加入工程，核对顶层名和JSON清单。`make -f scripts/legacy.mk rtl`是历史多顶层/验证层生成入口，普通接入优先使用上面的单配置入口。

## 目录

| 路径 | 内容 |
|---|---|
| `src/main/scala/vpu/` | 按功能分类的硬件、接口、生成器和实验模块；见[源码导航](../src/README.md) |
| `third_party/` | 固定硬件依赖及许可证 |
| `software/context/` | 可移植上下文镜像helper |
| `software/monitor/` | MMIO定义、设备树示例和Linux UIO观测工具 |
| `software/programs/` | C/intrinsics、汇编和链接示例 |
| `tests/` | 独立参考、公共端口功能及程序测试；见[测试导航](../tests/README.md) |
| `scripts/` | 工具准备、验证、综合、条件时序；维护工具集中在`maintenance/`，见[工具导航](../scripts/README.md) |
| `docs/` | [当前文档导航](README.md)和按版本保存的设计记录 |
| `reports/m61/` / `reports/repository-layout/` | 最新硬件验证、源码整理报告和精确证据清单 |
| `archive/` | 历史源码、文档及小型验证输入；展开产物见[保留规则](artifacts.md) |
| `tools/` / `build/` | 本地工具、RTL、模型、日志与网表；不入Git |

## 新环境与已有验证工作区

Git保留源码、报告与指定历史输入，不包含安装后的工具、完整仿真模型、所有build日志、Vivado DCP或bitstream。新clone可以按上文生成硬件；不能直接核对另一工作区中尚未下载/生成的全部历史产物SHA。

M60验证依赖固定Spike、SoftFloat、既有公共端口GSim模型及历史基线，完整步骤和范围见[M60报告](../reports/m60/evaluation.md)。这些里程碑脚本属于相应源码快照；不要将`verify_m18.py`、`verify_m48.py`等旧入口当成“当前全功能测试”运行。

根Makefile默认显示帮助；当前入口为`make compile`、`make rtl-direct`、`make rtl-isolated`和`make check`。原里程碑配方在`scripts/legacy.mk`，显式使用`make -f scripts/legacy.mk <target>`。

报告按[产物保留规则](artifacts.md)简化保存：大型receipt的JSON为精简索引，原文为同目录gzip；完整旧日志、展开网表和重复归档可从固定Git对象恢复。`make audit-retention`验证这些原文；浅克隆或源码ZIP不包含全部历史对象。

本次目录与注释整理通过Scala token和8个完整RTL顶层对照，不重写历史receipt。原M61完整回归在提交`f8df80e`及匹配工具/build产物上复现；原M60使用`0790a6e`。已有工作区的保留证据可通过`make audit-evidence`核对，细节见[验证说明](validation.md)。

## 历史记录

各`m*.md`、`reports/m*/`说明当时的实现、缓存复用、打包和测试范围。旧名称、旧实现ID和“尚未实现”列表均不能直接解释当前硬件。

本次整理前的长篇仓库记录保存在[文档快照](../archive/docs-m60/source/docs/repository.md)，保留M18导入、M25/M40时序基线和后续打包/复现说明。当前使用顺序为[项目首页](../README.md)→[接入指南](integration.md)→对应协议/验证文档。
