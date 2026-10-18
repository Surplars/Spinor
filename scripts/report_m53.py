#!/usr/bin/env python3
"""Audit independent context images, error recovery and frozen hardware."""
import hashlib,json,re,shutil,subprocess
from pathlib import Path
from report_m52 import ROOT,TOPS,baseline_check as older_baseline
from report_m51 import check
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def baseline_check():
    old,base=older_baseline();path=ROOT/'reports/m52/receipt.json';d=json.loads(path.read_text());check(d)
    assert d['hardware_changed'] is False and d['direct_commands']==64270
    base.update(m52_receipt_sha256=sha(path),m52_checked_bindings=sum(len(d.get(k,{})) for k in
                ['source_sha256','artifact_sha256','external_tool_dependency_sha256']),
                reused_direct_GSIM_Spike_commands=d['direct_commands'])
    return old,base

def main():
    old,base=baseline_check();out=ROOT/'reports/m53';out.mkdir(parents=True,exist_ok=True)
    sources={};artifacts={};external={}
    def manifest(path):
        path=ROOT/path;d=json.loads(path.read_text());check(d)
        artifacts[str(path.relative_to(ROOT))]=sha(path)
        sources.update(d.get('source_sha256',{}));artifacts.update(d.get('artifact_sha256',{}))
        external.update(d.get('external_tool_dependency_sha256',{}));return d
    results={};totals=dict(cases=0,restore_failures=0,save_failures=0,busy_memory=0,geometry_guards=0,
                         bit_flips=0,malformed_headers=0,truncated_sizes=0,negative_controls=0)
    rows=[]
    for top in TOPS:
        d=manifest('build/context-image/'+top+'/results.json');fp='Integer' not in top;m=d['metrics']
        assert d['top']==top and not d['hardware_changed'] and d['abi']==1 and d['image_bytes']==576
        assert m['cases']==(726 if fp else 380) and m['restore_failures']==(138 if fp else 136)
        assert m['save_failures']==(140 if fp else 138) and m['busy_memory']==3 and m['geometry_guards']==2
        assert d['negative_controls']=={'skip-vstart':'REJECTED','unlock-on-error':'REJECTED'}
        validation={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',d['validation_summary'])}
        assert validation==dict(bit_flips=4608,malformed_headers=19 if fp else 20,truncated_sizes=576)
        for k in ['cases','restore_failures','save_failures','busy_memory','geometry_guards']:totals[k]+=m[k]
        for k,v in validation.items():totals[k]+=v
        totals['negative_controls']+=len(d['negative_controls'])
        results[top]={k:d[k] for k in ['metrics','summary','validation_summary','run_wall_seconds','negative_controls']}
        rows.append(f"| {top} | {m['cases']} | {m['restore_failures']} | {m['save_failures']} | {m['total_cycles']:,} |")
        # Audit generated production models themselves, not only their receipt.
        manifest('build/gsim-direct/rtl/'+top+'/results.json')
    cross=manifest('build/context-cross/results.json')
    assert cross['scope']=='FREESTANDING_COMPILE_ONLY_NOT_TARGET_EXECUTION'
    for name,machine in [('riscv64',243),('aarch64',183)]:
        assert cross['targets'][name]['machine']==machine and not cross['targets'][name]['undefined_symbols']
    compiler=ROOT/'tools/llvm-program/usr/bin/clang-19';assert sha(compiler)==cross['compiler_sha256']
    tool_paths=[compiler,ROOT/'tools/llvm-program/usr/bin/clang++-19',Path(shutil.which('gcc')).resolve()]
    for query in ['-print-prog-name=cc1','-print-file-name=libasan.so','-print-file-name=libubsan.so']:
        tool_paths.append(Path(subprocess.check_output(['gcc',query],text=True).strip()).resolve())
    for path in tool_paths:
        external[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)]=sha(path)
    gate=manifest('build/timing-budget/m53-gate/results.json');artifacts.update(gate['input_sha256'])
    assert gate['passes_300MHz'] is None and gate['passes_500MHz'] is None
    assert all(d['budget_ns']==3.292 for d in gate['results'].values())
    text='''# M53：CPU 独立的上下文镜像与恢复接口

新增可移植 C11 库，通过现有 Command/context 端口保存和恢复 VPU 自身状态。
镜像固定为 576 字节，包含 32 个向量寄存器、VL/vtype/vstart、vcsr 和可选 fcsr；
64 字节小端元数据加 512 字节寄存器内容，带版本、配置校验和 CRC32。
不依赖 libc、动态分配、原生结构体布局或宿主向量指令。
接口契约、字节表和编译命令见 [context README](../../software/context/README.md)。

本轮未修改 Orbital/Valence，未绑定其不稳定的内部流水线。宿主只需实现端口传输和
互斥回调。硬件数据通路、ISA、RAM、接口、monitor 实现 0x5001 均未改变；
这是上下文软件功能及独立验证的进展，没有新增硬件上下文控制器或 Linux 作业驱动。

## 四预设实际执行

测试将实际 C 库链接到公共端口适配器，直接驱动四个生产 GSim 顶层。独立 Python
使用 struct/zlib 构造期望镜像和运算结果，不以 DUT 输出或 C 序列化结果生成期望。
保存后模拟另一任务覆盖所有寄存器和 CSR，再恢复独立镜像，逐字节核对，继续执行
真正的向量指令，并比较完整寄存器、CSR 和 8 KiB 普通 RAM。

| 预设 | 镜像/继续执行场景 | 恢复失败注入 | 保存失败注入 | DUT 总周期 |
|---|---:|---:|---:|---:|
'''+ '\n'.join(rows)+f'''

共 **{totals['cases']:,} 个场景**，另有 **{totals['restore_failures']+totals['save_failures']:,} 个失败注入点**。
每个保存/恢复回调位置分别在硬件操作生效前和生效后报错；错误后必须继续阻止执行，
拒绝保存，完整重试恢复后方可释放。覆盖所有 22 种合法 SEW/LMUL、VL0/1/VLMAX、
vstart0/1/127、TA/MA、vill，以及全部 256 种 fcsr 位模式（浮点预设）。

继续执行包含掩码整数加法；浮点预设在 9 种合法 FP32/64 几何上执行正负半 ULP
加法，覆盖 5 种合法 frm 并检查 NX/已有异常标志；四预设执行全部 4 种 vxrm 的
定点舍入并保留 vxsat。保留 frm5..7 只验证上下文位保存，不执行非法浮点算术。

每预设还有 3 个真实访存故障前缀：普通 load、NF3 segment load 的中间字段故障、
普通 store。先让 DUT 实际执行到访问错误，保存其部分进度，恢复并重试；store
已经写出的前缀保留在普通 RAM，镜像不试图回滚它。访存忙时共 {totals['busy_memory']} 次保存请求必须拒绝。
另检验空闲/已毒化状态下设备几何不匹配，以及恢复期间损坏镜像不会解除既有锁定。

周期只统计测试台推进的 DUT 时钟边沿，包含初始化、校验、背压和失败重试；
未模拟宿主 C 指令、CRC/内存复制、真实总线/锁开销，不作为 SoC 切换延迟或性能承诺。

## 拒绝与恢复边界

原生 C 校验测试在 ASan/UBSan 下完成：{totals['bit_flips']:,} 个逐位损坏、
{totals['malformed_headers']} 个重算 CRC 的非法元数据、{totals['truncated_sizes']:,} 个截断长度，
另检查超长、空指针、缺失回调、缓冲区哨兵和输入不变。无效镜像均须在设备访问前拒绝。
每预设故意省略 vstart 恢复、故意在失败时释放所有权，两类错误共 {totals['negative_controls']} 次均被检测。

恢复依次写 RF、通过 VSETVL 恢复只读 VL/vtype、写 vcsr/fcsr、最后写 vstart。
任何 I/O 错误或目标几何不匹配都保留恢复锁定；无效源镜像也不能清除已有锁定。
没有原子整体回滚；应用须持有独立、已提交的恢复镜像。CRC 是意外损坏检测，不是认证。

**互斥由宿主适配层实现**：必须排除 CPU/debug/其他上下文提交并排空事务。
release(valid=0) 必须持续阻止执行，只允许完整恢复重试或平台协调复位。
仿真验证了这个适配器模型的行为，尚未证明未来真实 CPU/OS 实现符合契约。
镜像不包含 CPU 的 PC/GPR、VS/FS、权限、RAM、缓存/TLB 或监控计数。

## 双宿主构建与时序

Clang19.1.7 分别以 RV64IMAC/LP64 和 ARMv8-A general-regs-only 编译；ELF 机器
类型正确，均无未解析运行库符号。库必须保持标量编译，避免保存期间自身使用所保存的
向量/浮点状态。这是独立交叉编译检查，未运行 ARM/RISC-V 实机或 Linux 程序。

M50/M51/M52 的旧源码、工具、RTL、网表与执行证据重新核对散列，硬件 Scala 文件集合
及内容保持一致；因此复用此前 64,270 条直接 GSim/Spike 命令、SoftFloat、局部证明、
综合网表及 LLVM 程序证据，未重复整轮无关长回归。上下文 ABI 期望来自独立 Python，
本轮上下文测试不冒称新增 Spike 差分覆盖。

固定 M25 权重和 100ps/link 条件门槛重新执行，默认公共顶层及计算/访存顶层仍为
**3.292ns ≤ 3.333ns**。标准配置资源仍为 23,206 逻辑 LUT、13,204 FF、9 DSP；
整数配置 12,737 LUT、6,322 FF、1 DSP。本轮没有增加硬件快照寄存器或 RAM。
模型排除 DSP 影响端点，未布局布线、未校准 ZU15EG-2，不是 STA/SDF；
实际 300/500MHz 均未知，旧 M31 结果不能签核当前版本。

仍是 VLEN128/ELEN64、单 lane、单向量指令在途，未接入 Orbital 真实退休或共享 FCSR，
未接入 VS/FS、VM/PMP、缓存一致性或 Linux 作业提交。当前库也不消除 FP16/Zvfhmin、
Zvbb/Zvkt 等待办；尚不能声明完整 V/RVA23。

## 复现

在已建立 M52 锁定工具/生产导出/证据的环境运行：

```bash
python3 scripts/verify_m53.py
python3 scripts/verify_m53.py --check-only
```

可单独运行 `python3 tests/test_context_image.py --top SpinorStandard` 和
`python3 scripts/check_context_cross_compile.py`。四预设使用独立目录，不改写 M52
参考语料或模型；最终 receipt 绑定新源码、镜像、C/C++ 二进制、日志、工具和旧证据。
'''
    doc=out/'evaluation.md';doc.write_text(text);artifacts[str(doc.relative_to(ROOT))]=sha(doc)
    for rel in ['software/context/README.md','software/context/spinor_context.c','software/context/spinor_context.h',
                'tests/context_gsim.cc','tests/context_validation.c','tests/test_context_image.py',
                'scripts/check_context_cross_compile.py','scripts/report_m53.py','scripts/verify_m53.py']:
        sources[rel]=sha(ROOT/rel)
    for m in [50,51,52]:
        rel=f'reports/m{m}/receipt.json';artifacts[rel]=sha(ROOT/rel)
    result=dict(project='Spinor',milestone='M53',status='PASS',hardware_changed=False,base_evidence=base,
                scope='PORTABLE_CONTEXT_LIBRARY_WITH_PUBLIC_PORT_ADAPTER_CONTRACT',abi=1,image_bytes=576,
                context_results=results,totals=totals,cross_compile=cross['targets'],target_execution=False,
                hardware_context_lock_added=False,linux_job_driver=False,actual_Orbital_integrated=False,
                full_V=False,full_RVA23=False,monitor_implementation='0x5001',resources=old['resources'],
                conditional_reference_gate=gate,passes_300MHz=None,passes_500MHz=None,
                source_sha256=sources,artifact_sha256=artifacts,external_tool_dependency_sha256=external)
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS M53',totals['cases'],'context cases',totals['restore_failures']+totals['save_failures'],
          'callback failures',len(artifacts),'bound artifacts')
if __name__=='__main__':main()
