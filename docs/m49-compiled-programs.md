# M49：编译器程序执行验证

本轮把逐条RVV测试推进到真实编译程序：固定LLVM/Clang 19.1.7将无运行库C代码编译成RV64GV ELF，仿真器实际取指、执行标量分支和地址计算，把向量指令及向量CSR交给公开Spinor预设顶层。循环使用DUT实际返回的标量结果和VL，未预先生成向量命令轨迹，也没有用Python代执行向量运算。

新增的是编译、程序执行和回归入口；Chisel硬件、指令集、接口与M48一致，monitor实现ID保持0x4801。

## 程序范围

13个普通C函数由编译器自动向量化，没有手写RVV或intrinsics：u8/u16/u32/u64加法、u32乘加、i32限幅、条件选择、u32求和、i16点积、索引gather、双字段AoS求和，以及有符号右移、商余组合。产物包含整组加载/存储、掩码计算、宽化乘加、除法与负乘减组合、归约、索引及分段访存，也包含标量短数组/余数处理。商余输入排除C的除零与INT_MIN/-1未定义行为；DUT这些指令的架构特殊情况仍由原定向回归覆盖。

另外5个标准RVV intrinsics函数验证动态VL strip-mining：u32加法、e8/m8加法、FP32和FP64加法，以及在配置RAM窗口尾部执行FOF、读取实际缩短VL并只存有效元素。FP函数只在两个浮点预设运行；数值选择有限、可精确表示的数据，并检查fflags/frm保持零，不替代已有SoftFloat边界回归。FOF覆盖VL0、完整加载和截短到1/8/64/128个元素。

完整矩阵使用20种长度0～129，含多个VLMAX前后边界；四预设定向矩阵逐函数使用空数组、单元素及一个完整向量加尾部，并单独保留5个FOF场景。每次函数调用独立复位、重装ELF与输入，初始GPR有污染值；不依赖其他函数留下的向量状态。源数据包含零、最大值、符号边界和混合数值。

## 参考、接口与限制

Python按C函数语义计算期望RAM和返回值；13个普通C函数还由本机GCC生成标量共享库独立执行，先与Python检查整块RAM，再启动RTL。每次DUT返回后逐字节检查代码、输入、输出及保护区域，栈区域不纳入比较。TL检查地址范围、自然对齐、opcode、size和字节mask，加入请求反压、注册响应及完成背压；RTL执行原有RF所有权、写回排空和FOF原子提交断言。

共享标量适配器另用264条直接指令检查32/64位有符号右移、除法和余数，包括负数、最大移位、除零及MIN/-1。修正了Verilog条件表达式隐式无符号化的问题；这项检查不代表CPU完整合规。

四个预设分别执行RTL和Yosys映射网表，相同输入逐调用比较最终RAM、标量返回、动态向量指令/VL轨迹、总线次数和周期。负对照故意破坏TL返回数据，要求正常运行结束且RAM参考必须检出差异；不能把工具编译失败算作检错成功。

标量执行器是测试专用的RV64子集适配器，只处理这些ELF实际需要的整数控制流、地址运算和访存。它不是Orbital，没有核级退休、VS/FS、特权、MMU/PMP、缓存一致性或中断；未运行Linux，也不是Spike/Sail逐指令差分。普通C程序的最终结果验证不能替代完整ISA合规和独立架构模型审计。单VPU指令在途和物理普通RAM限制保持。

## 复现

Linux x86-64需要Python、GCC、dpkg-deb及LLVM运行所需的系统库（libstdc++、libffi、libedit、libz3、zlib/zstd、libxml2、libtinfo）。编译器、intrinsics头文件、LLD和LLVM库的五个Debian包由独立toolchain.lock.json固定URL和SHA，解包到tools/llvm-program，不安装系统包、不修改HOME。

```bash
python3 scripts/verify_m49.py
make package-m49
```

暖环境对M48硬件源码、原执行依赖及全部证据逐项核对后复用原矩阵；仅允许明确列出的交付说明文件变化，不能以文档例外跳过RTL/测试/模型依赖。缺失或不匹配时先完整执行M48前置验证，再执行本轮程序矩阵。新程序、重生成和固定预算均本轮执行。代码与四预设重新生成比较，确保复用的映射网表对应当前Chisel。

开发时可单独运行：

```bash
python3 scripts/bootstrap_program.py
python3 tests/test_compiled_programs.py --build-only
python3 tests/test_compiled_programs.py --top SpinorStandard --compact
python3 tests/test_compiled_programs.py --top SpinorStandard --compact --mapped
```

--only仅供调试；最终报告拒绝任何仅包含部分函数的结果。build/programs保存ELF、汇编、逐调用输入/实际RAM、轨迹、参考散列、日志和工具参数。程序周期反映测试适配器及总线服务假设，不代表Orbital性能；云端条件时序仍使用原M25权重、100ps/link和3.333ns门槛，DSP及物理实现时序尚未签核。

交付包包含源码、程序和验证证据，不包含已安装工具。Yosys单元仿真库与编译器等由固定版本bootstrap提供；M49 receipt的external_tool_dependency_sha256保留该库的实际输入SHA，生成报告前仍逐项校验。嵌套程序结果中相应tools路径是外部工具依赖，不能当作ZIP内文件。
