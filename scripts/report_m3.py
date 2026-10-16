#!/usr/bin/env python3
"""M3 FP integration evidence, with explicit numerical/ISA/device boundaries."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m3'
TOPS=['FloatingPointLane','RamVectorFp','RamVectorFpNoDsp']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lane=read('build/test/fp-lane-results.json')
    vector=read('build/test/fp-vector-results.json')
    mapped=read('build/test/fp-vector-mapped-results.json')
    integer=read('build/test/fp-integer-results.json')
    if lane['flush_reset_cases']!=85 or 'cycles=95064' not in vector['test_summary']:
        raise SystemExit('M3 is frozen in archive/m3; current timing-split hardware must use report_m4.py')
    assert lane['status']=='PASS' and lane['corrupt_result_rejected'] and lane['known_answer_anchors']==52
    assert vector['status']==mapped['status']=='PASS'
    assert vector['commands']==mapped['commands']==1649
    assert vector['coverage']==mapped['coverage']
    assert 'PASS ram-vector commands=789 reads=2968' in integer['models']['RamVectorFp']
    assert 'SUCCESS' in (ROOT/'tools/mill-generate.log').read_text()
    # Fresh elaboration after final comment changes must reproduce tested RTL.
    for rel,h in read('tools/m3-tested-rtl-sha256.json').items():assert sha(ROOT/rel)==h,rel
    deps=read('third_party/fp-dependencies.json')
    for name,h in deps['local_sources_sha256'].items():
        assert sha(ROOT/'third_party/berkeley-hardfloat/src/main/scala'/name)==h,name
    unisim=read('third_party/xilinx-unisim/manifest.json')
    for name,h in unisim['sha256'].items():assert sha(ROOT/'third_party/xilinx-unisim'/name)==h,name
    oracle=read('tools/fp/oracle-source-hashes.json')
    for rel,h in oracle.items():assert sha(ROOT/'tools/fp/softfloat'/rel)==h,rel
    resources=[];paths={};artifacts=[]
    for top in TOPS:
        folder=ROOT/'build/synth'/top;c=read(str(folder.relative_to(ROOT)/'summary.json'))['mapped_cells']
        row={'top':top,'logic_LUT':sum(v for k,v in c.items() if k.startswith('LUT')),
             'FF':sum(v for k,v in c.items() if k.startswith('FD')),'DSP48E2':c.get('DSP48E2',0),
             'RAM64M8':c.get('RAM64M8',0),'RAM32M16':c.get('RAM32M16',0),'CARRY4_logical':c.get('CARRY4',0)}
        row['storage_LUT']=8*(row['RAM64M8']+row['RAM32M16']);resources.append(row)
        dest=OUT/top;dest.mkdir(exist_ok=True)
        for name in ['summary.json','stat.json','synth.ys','paths.json']:
            shutil.copyfile(folder/name,dest/name)
        paths[top]=read(str(folder.relative_to(ROOT)/'paths.json'))
        artifacts += [folder/n for n in ['mapped.v','mapped.json','summary.json','stat.json','synth.log','paths.json']]
    files=['build/test/fp-lane-results.json','build/test/fp-vector-results.json','build/test/fp-vector-mapped-results.json',
           'build/test/fp-integer-results.json','tools/mill-generate.log','tools/fp/oracle-source-hashes.json',
           'tools/m3-tested-rtl-sha256.json']
    for rel in files:shutil.copyfile(ROOT/rel,OUT/Path(rel).name)
    artifacts += [ROOT/p for p in files]
    artifacts += [ROOT/'build/test'/n for n in ['fp-lane.log','fp-vector.log','fp-vector-mapped.log','RamVectorFp.log',
                    'fp_lane_tb.sv','fp_vector_tb.sv','fp-vector-mapped.compile.log']]
    artifacts += [ROOT/'tools/fp/libfp-reference.so',ROOT/'tools/fp/softfloat/build/Linux-x86_64-GCC/softfloat.a']
    artifacts += list((ROOT/'build/rtl').rglob('*.sv'))
    sources=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','README.md','tools.lock.json']]
    sources += [p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*')
                if p.is_file() and '__pycache__' not in str(p)]
    receipt={'scope':'M3_SAME_WIDTH_FP32_FP64_VECTOR_SUBSET','target':'xczu15eg-ffvb1156-2-i',
             'full_RVV_implemented':False,'Valence_core_integrated':False,'vector_LSU_implemented':False,
             'scalar_vector_FCSR_unified_in_Valence':False,
             'device_place_route_performed':False,'passes_300MHz':None,'passes_500MHz':None,
             'FP_device_timing_simulation_performed':False,'bitstream_generated':False,
             'tools':read('tools.lock.json'),'HardFloat_and_SoftFloat':deps,'DSP_model':unisim,
             'resources':resources,'lane_test':lane,'vector_test':vector,'DSP_mapped_test':mapped,'integer_regression':integer,
             'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(sources))},
             'artifact_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(artifacts))}}
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    text=['# ZU15EG-2 M3：共享 FP32/FP64 接入','',
          '**已将第一组同宽浮点运算接入 RAM 向量引擎；完整 RVV/RVA23、Valence 整核接入、真实器件时序和 bitstream 仍未完成。**','',
          '构建仍为 Mill 1.1.7、Scala 2.13.18、Chisel 7.16.0 / firtool 1.160.0。',
          '开源评估使用 Yosys 0.70+16、Icarus 14.0；独立数值参考使用固定版本 Berkeley SoftFloat。','',
          '## 实现范围','',
          '- FP32/FP64：vfadd/vfsub/vfmul/vfdiv、反向 vfsub/vfdiv、vfsqrt。',
          '- 八种融合操作：vfmadd/vfnmadd/vfmsub/vfnmsub，以及 vfmacc/vfnmacc/vfmsac/vfnmsac。',
          '- vfmin/vfmax、vfsgnj/vfsgnjn/vfsgnjx、vmfeq/vmfne/vmflt/vmfle、标量形式 vmfgt/vmfge、vfclass。',
          '- 支持对应的 vv/vf 形式；sqrt/class 为一元 .v，总计 48 种合法编码形式。',
          '- frm/fflags/fcsr CSR、五种舍入模式、RISC-V canonical NaN、非规格化数与异常标志。',
          '- 复用原来的 LMUL、mask/tail/prestart、版本表和完成背压；标量 vf 的 FP32 操作数按 FLEN64 检查 NaN-boxing。','',
          '## 资源共享与提交','',
          '一个 53-bit FMA 通路同时处理两种精度；FP32 在输入侧精确扩展并保留 signaling NaN，',
          '原始结果直接舍入到目标精度，避免先舍入到 FP64 再转 FP32。加减用乘数 1，',
          '乘法加一个与乘积同号的零以保留 -0；除法与开方共用一个迭代单元。',
          '乘积、四段 32-bit 对齐加法、规格化、舍入均有寄存器边界；单元素在途。','',
          '融合操作的旧 vd 从已提交 RAM 读取；候选结果写入另一版本。',
          '元素产生的 flags 先在指令内 OR 累积，只有 completion.fire 才与寄存器版本一起提交。',
          'mask 跳过、tail、prestart 元素不参与运算；flush 同时丢弃候选结果、待提交 flags 和迭代状态。','',
          '当前独立原型持有一份 FCSR 并支持相应 CSR 指令。整核接入时必须与 Valence 标量 FP 的',
          '**同一份架构 FCSR** 协调，接入其 VS/FS、dirty、权限及退休流程；当前尚未实现这些核级连接。','',
          '## 资源映射','',
          'Yosys `synth_xilinx -family xcup`，OOC，无 IOB/时钟缓冲。以下不是 Vivado 布局后占用。','',
          '| 候选 | 逻辑 LUT | FF | DSP48E2 | 存储 LUT | RAM64M8 | RAM32M16 |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for r in resources:
        text.append('| '+r['top']+' | '+' | '.join(str(r[k]) for k in ['logic_LUT','FF','DSP48E2','storage_LUT','RAM64M8','RAM32M16'])+' |')
    native=next(r for r in resources if r['top']=='RamVectorFp')
    lut=next(r for r in resources if r['top']=='RamVectorFpNoDsp')
    text += ['',f"DSP 候选较全 LUT 乘法候选减少 {lut['logic_LUT']-native['logic_LUT']} 个逻辑 LUT，保留 {native['DSP48E2']} 个 DSP48E2。",
             '两者的数据阵列继续映射到 RAM，没有恢复整组 FF 快照。',
             '存储 LUT 已单列；RAM64M8/RAM32M16 每个按完整单元 8 个 LUT 位置计数。',
             '全 LUT 候选仅作资源对照；本轮映射后功能检查覆盖的是原生 DSP 候选。','',
             '## 独立检查','',
             f"- 数值单元：{lane['vectors']} 组，FP32/FP64 × 五种舍入模式 × 全部已实现数值操作，52 个已知答案锚点。",
             '- 逐位对照数据与 NV/DZ/OF/UF/NX，含 NaN、±0、subnormal、overflow、融合抵消和半 ULP。',
             '- 任意完成背压；85 个阶段撤销/复位情形；注入错误结果的负对照被拒绝。',
             '- RAM 向量引擎：1649 条命令、7176 次寄存器读检查，含 219 次 CSR、9 种合法 FP SEW/LMUL 组合。',
             '- 指令级检查源/目的别名、八种融合操作、NaN-boxing、mask/tail/vstart 不产生多余 flags、非法舍入/SEW/编码、12 次撤销。',
             '- FP 开启时的整数回归：789 条命令、2968 次读检查。',
             '- **含 12 个 DSP48E2 的映射网表通过同一组 1649 条命令，仿真周期数与 RTL 同为 95064。**',
             '- DSP 单元使用公开的 Apache-2.0 Xilinx Unisim DSP48E2 功能模型，未修改模型；其余映射单元使用 Yosys 功能模型。',
             '- 数值参考是独立 SoftFloat；HardFloat 自身及其上游 testbench 没有被当作黄金模型。','',
             '## 时序评估及限制','',
             '**FP 的 300/500 MHz 均未验证。映射后功能仿真不是 SDF/器件速度仿真；M2 的整数参考延迟结果不能套到 FP。**','',
             '| 候选 | 最长数据单元跳数 | 最长控制单元跳数 | 最大非时钟扇出 |',
             '|---|---:|---:|---:|']
    for t,p in paths.items():
        text.append(f"| {t} | {p['longest_data']['hops']} | {p['longest_control']['hops']} | {p['fanout'][0]['loads']} |")
    text += ['', '跳数不是 ns/MHz。DSP 内部寄存器参数均为 0 才允许进入该组合图；DSP 和 RAM 读各按一个未校准单元计数。',
             '目前最长数据链起于 FMA 后处理的 doSubMags，包含 28 个逻辑 CARRY4 和后续规格化逻辑。',
             '这明确指出了继续分割的重点；已有乘加外部流水并没有消除 HardFloat 后处理内部的长链。',
             '迭代除法/开方、规格化、舍入及控制路径也须在真实器件实现中继续评估，不能据本报告宣布 300 MHz 已关闭时序。','',
             '## LSU 结构选择','',
             'LSU 是 Load/Store Unit。计划让 VPU 具有独立向量 LSU 前端，负责元素地址、mask、',
             '请求拆分和故障元素定位；通过宿主接口共用 CPU 的地址翻译/权限、缓存和总线，协调访问顺序。',
             '当前未实现向量 LSU、访存故障/FOF 和可重启的部分提交。非故障算术的整条原子翻转不能替代这些语义。','',
             '## 尚未完成','',
             '浮点/整数转换、FP 宽化/窄化、归约、估算指令、FP16/Zvfhmin；剩余整数操作、向量 LSU、',
             '标量/向量 FCSR 统一、精确异常及 Valence 核级验证、CDC、器件布线和板测。',
             '当前不能发布完整 V/RVA23 合规声明。','',
             '## 复现','',
             '- `make bootstrap`；`make verify-m3`；`make package-m3`。首次另下载并校验固定版本 SoftFloat。',
             '- [源代码/RTL/网表/工具参考 SHA-256 与结果](receipt.json)',
             '- [数值单元结果](fp-lane-results.json)、[向量 RTL](fp-vector-results.json)、[DSP 网表](fp-vector-mapped-results.json)',
             '- [架构合同](../../docs/architecture.md)、[归档 M2 报告](../../archive/m2/reports/evaluation.md)','']
    (OUT/'evaluation.md').write_text('\n'.join(text))
    print('Wrote reports/m3/evaluation.md and receipt.json; FP device timing remains unqualified')

if __name__=='__main__':main()
