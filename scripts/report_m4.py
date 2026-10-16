#!/usr/bin/env python3
"""M4 pipeline/reference-tool evidence; no physical frequency claim."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/m4'
TOPS=['FloatingPointLane','RamVectorFp']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
def cycles(test):return int(re.search(r'cycles=(\d+)',test['test_summary'])[1])
def resource(folder,top):
    c=read(str(folder/'summary.json'))['mapped_cells']
    row={'top':top,'logic_LUT':sum(v for k,v in c.items() if k.startswith('LUT')),
         'FF':sum(v for k,v in c.items() if k.startswith('FD')),'DSP48E2':c.get('DSP48E2',0),
         'RAM64M8':c.get('RAM64M8',0),'RAM32M16':c.get('RAM32M16',0),'CARRY4_logical':c.get('CARRY4',0)}
    row['storage_LUT']=8*(row['RAM64M8']+row['RAM32M16'])
    return row

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lane=read('build/test/fp-lane-results.json');vector=read('build/test/fp-vector-results.json')
    mapped=read('build/test/fp-vector-mapped-results.json');integer=read('build/test/fp-integer-results.json')
    integer_base=read('build/test/ram-vector-results.json')
    probe=read('build/rapidwright/probe.json')
    assert lane['status']=='PASS' and lane['vectors']==6811 and lane['known_answer_anchors']==52
    assert lane['corrupt_result_rejected'] and lane['flush_reset_cases']==205
    assert vector['status']==mapped['status']=='PASS' and vector['mapped'] is False and mapped['mapped'] is True
    assert vector['commands']==mapped['commands']==1649 and vector['coverage']==mapped['coverage']
    assert cycles(vector)==cycles(mapped)
    assert 'PASS ram-vector commands=789 reads=2968' in integer['models']['RamVectorFp']
    for top in ['RamVector','RamVector16','RamVectorFlops']:
        assert 'PASS ram-vector commands=789 reads=2968' in integer_base['models'][top]
    assert probe['status']=='PASS_CAPABILITY_PROBE' and probe['device_loaded'] and not probe['placed_or_routed_VPU']
    for rel,h in probe['input_sha256'].items():assert sha(ROOT/rel)==h,rel
    assert 'SUCCESS' in (ROOT/'tools/mill-generate.log').read_text()
    for rel,h in read('tools/m4-tested-rtl-sha256.json').items():assert sha(ROOT/rel)==h,rel
    deps=read('third_party/fp-dependencies.json')
    for name,h in deps['local_sources_sha256'].items():
        assert sha(ROOT/'third_party/berkeley-hardfloat/src/main/scala'/name)==h,name
    unisim=read('third_party/xilinx-unisim/manifest.json')
    for name,h in unisim['sha256'].items():assert sha(ROOT/'third_party/xilinx-unisim'/name)==h,name
    for rel,h in read('tools/fp/oracle-source-hashes.json').items():assert sha(ROOT/'tools/fp/softfloat'/rel)==h,rel
    assert sha(ROOT/'archive/m3/zu15-vpu-m3.zip')=='9ba7a9ee38e6d800807ed1e17f42bbffca75a5037377cc40cb66e3a27d565aca'
    resources=[];baseline=[];paths={};oldpaths={};artifacts=[]
    for top in TOPS:
        folder=Path('build/synth')/top
        resources.append(resource(folder,top));baseline.append(resource(Path('archive/m3/reports')/top,top))
        paths[top]=read(str(folder/'paths.json'))
        oldpaths[top]=read(f'archive/m3/reports/{top}/paths.json')
        assert paths[top]['unregistered_DSP48E2_counted_as_one_uncalibrated_hop']==8
        dest=OUT/top;dest.mkdir(exist_ok=True)
        for name in ['summary.json','stat.json','synth.ys','paths.json']:shutil.copyfile(ROOT/folder/name,dest/name)
        artifacts += [ROOT/folder/n for n in ['mapped.v','mapped.json','summary.json','stat.json','synth.log','paths.json']]
    copied=['build/test/fp-lane-results.json','build/test/fp-vector-results.json','build/test/fp-vector-mapped-results.json',
            'build/test/fp-integer-results.json','build/test/ram-vector-results.json','build/rapidwright/probe.json','build/rapidwright/probe.log',
            'tools/mill-generate.log','tools/fp/oracle-source-hashes.json','tools/m4-tested-rtl-sha256.json']
    for rel in copied:shutil.copyfile(ROOT/rel,OUT/Path(rel).name)
    artifacts += [ROOT/p for p in copied]
    artifacts += [ROOT/'build/test'/n for n in ['fp-lane.log','fp-vector.log','fp-vector-mapped.log','RamVectorFp.log',
                   'fp_lane_tb.sv','fp_vector_tb.sv','ram_vector_tb.sv','fp-vector-mapped.compile.log']]
    artifacts += [ROOT/'tools/fp/libfp-reference.so',ROOT/'tools/fp/softfloat/build/Linux-x86_64-GCC/softfloat.a']
    artifacts += list((ROOT/'build/rtl').rglob('*.sv'))
    sources=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','README.md','tools.lock.json']]
    sources += [p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*')
                if p.is_file() and '__pycache__' not in str(p)]
    receipt={'scope':'M4_TIMING_PIPELINE_SPLITS_AND_RAPIDWRIGHT_CAPABILITY_PROBE','target':'xczu15eg-ffvb1156-2-i',
             'full_RVV_implemented':False,'Valence_core_integrated':False,'vector_LSU_implemented':False,
             'scalar_vector_FCSR_unified_in_Valence':False,'device_place_route_performed':False,
             'passes_300MHz':None,'passes_500MHz':None,'FP_device_timing_simulation_performed':False,
             'bitstream_generated':False,'tools':read('tools.lock.json'),'HardFloat_and_SoftFloat':deps,'DSP_model':unisim,
             'baseline_M3_resources':baseline,'resources':resources,'RapidWright_probe':probe,
             'lane_test':lane,'vector_test':vector,'DSP_mapped_test':mapped,'integer_regression':integer,
             'integer_only_regression':integer_base,
             'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(sources))},
             'artifact_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(artifacts))}}
    text=['# ZU15EG-2 M4：优先切分组合路径','',
          '本轮保持 M3 同宽 FP32/FP64 子集，集中拆分组合链，并实测 RapidWright 的目标器件与模型接口。',
          '**300 MHz / 500 MHz 均未完成器件时序验证；没有 VPU 布局布线、SDF、WNS/TNS 或 bitstream。**','',
          '## 硬件改动','',
          '- FMA 前处理：操作数、指数、对齐距离和两级移位分别寄存。',
          '- 53×53 无符号乘法分成 26×17 小乘法，部分积寄存；13 项通过三级 carry-save 压缩后用四段 32-bit 加法合并。',
          '- FMA 后处理：幅值、前导零计数、两级规格化分开；宽递增改成显式平衡前缀。',
          '- 舍入：调整量、掩码、舍入有效数和编码输出分级，宽递增使用前缀结构。',
          '- 除法/开方：每次递推拆成调度、准备、低 32-bit 减法、高位减法和状态提交五拍。',
          '- 比较结果先寄存，再进入结果选择；FP 顶层的译码与合法性检查分级。',
          '- 原始 HardFloat 固定源文件未改；四个派生模块保留 BSD 版权及修改说明。','',
          '## 映射资源对照','',
          'Yosys 0.70+16，`synth_xilinx -family xcup`；逻辑 LUT 与存储 LUT 分列，不等于布局后 slice 数。','',
          '| 阶段/顶层 | 逻辑 LUT | FF | DSP48E2 | 存储 LUT |',
          '|---|---:|---:|---:|---:|']
    for stage,rows in [('M3',baseline),('M4',resources)]:
        for r in rows:text.append(f"| {stage} {r['top']} | {r['logic_LUT']} | {r['FF']} | {r['DSP48E2']} | {r['storage_LUT']} |")
    text += ['', 'RamVectorFp 的 RAM 映射仍是 32×RAM64M8 与 5×RAM32M16，按完整单元计 296 个存储 LUT。',
             '数据阵列继续使用 RAM，新增 FF 主要是浮点运算流水寄存器；没有恢复整组向量寄存器快照。','',
             '## 结构路径对照','',
             '| 阶段/顶层 | 最长数据单元跳数 | 最长控制单元跳数 | 最大非时钟扇出 |',
             '|---|---:|---:|---:|']
    for stage,rows in [('M3',oldpaths),('M4',paths)]:
        for top,p in rows.items():text.append(f"| {stage} {top} | {p['longest_data']['hops']} | {p['longest_control']['hops']} | {p['fanout'][0]['loads']} |")
    text += ['', '这些是无时间的映射图分析。组合 DSP 和 RAM 读各计一个未校准跳数；原生 CARRY8 打包、',
             '单元位置、连线、负载、时钟偏差与 setup/hold 均不包含，不能把跳数换算为 MHz。',
             '最长数据链已经从后处理长进位转移到输入重编码等逻辑；控制扇出仍需物理实现评估。',
             '新增阶段也增加了控制/使能负载，不能仅凭数据跳数断言整体时序改善幅度。','',
             '## 功能及周期代价','',
             f"- FP lane：{lane['vectors']} 组、52 个独立已知答案锚点，逐位对照 SoftFloat 结果与 flags。",
             '- FP32/FP64 × 五种舍入模式；205 个撤销/复位情形；完成背压及错误结果负对照通过。',
             f"- 向量 RTL 和含 8 个 DSP 的映射网表均通过 1649 条命令、7176 次读取检查，均为 {cycles(vector)} 周期。",
             '- FP 开启的整数回归：789 条命令、2968 次读取检查。',
             '- 共享译码代码涉及的纯整数 RAM / 16-bit 切分 / FF 对照三个顶层也分别通过同一组 789 条命令。',
             '- DSP 使用公开 Apache-2.0 Unisim 功能模型，其他单元使用 Yosys 功能模型；没有器件速度注释。','',
             '| 测试驱动记录的 lane 周期数 | M3 | M4 |',
             '|---|---:|---:|',
             '| 合法加/减/乘/FMA | 10 | 30 |',
             '| min/max/比较/符号/class | 3 | 4 |',
             '| 除法（随特殊值与数值变化） | 5 / 58 / 59 | 13 / 278 / 283 |',
             '| 开方（随特殊值与数值变化） | 5 / 57 / 58 | 13 / 273 / 278 |','',
             f"同一向量测试 M3 为 95064 周期，M4 为 {cycles(vector)} 周期。lane 仍是容量一，", 
             '增加寄存器没有使其每拍接收一个新元素。在相同频率下本轮更慢；只有后续测得真实 Fmax，',
             '才能判断时间性能。这里保留单元素控制方便时序探索，后续吞吐率优化需独立设计。','',
             '## RapidWright：能用，但当前只验证工具能力','',
             '- 固定版本 v2026.1.1-beta，standalone JAR 约 110 MiB；按需加载约 6.5 MiB 的 ZU15EG 数据库。',
             '- 已成功识别目标 part/speed，加载 435×455 器件网格，查询 UltraScale+ 单元模型。',
             '- 示例 LUT A1→O6 为 150 ps、FF CLK→Q 为 77 ps；只是家族表值，未校准 -2 等级或设计负载。',
             '- 有 Yosys/EDIF 导入和 RWRoute，可辅助物理实现；当前尚未把 VPU 打包和布局布线。',
             '- DSPTimingData 通常需要 Vivado 脚本导出的 DSP 延迟。当前无此数据，不能声称得到完整 FP 路径时序。',
             '- [实际探针结果](probe.json)、[输出日志](probe.log)、[用途、缺口及上游依据](../../docs/rapidwright.md)。','',
             '## 复现和边界','',
             '`make bootstrap` → `make verify-m4` → `make package-m4`。首次运行需要网络获取固定工具与参考。',
             '本轮逐项运行了上述目标中的检查；报告使用实际生成的 RTL、网表、测试结果和探针输入散列。',
             '[完整输入/产物 SHA-256](receipt.json)。M3 原包保持不变，基线来自 [M3 归档](../../archive/m3/reports/evaluation.md)。','',
             '本轮没有增加 ISA 覆盖。完整 RVV/RVA23、LSU、Valence 核级连接及统一 FCSR 仍未完成，',
             '具体范围见 [架构合同](../../docs/architecture.md) 和 M3 归档。','']
    (OUT/'evaluation.md').write_text('\n'.join(text))
    handoff=[p for p in OUT.rglob('*') if p.is_file() and p.name!='receipt.json']
    handoff += [p for stage in ['m1','m2','m3'] for p in (ROOT/f'archive/{stage}/reports').rglob('*') if p.is_file()]
    receipt['artifact_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in sorted(handoff)})
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Wrote M4 report; 300/500 MHz remain unqualified')

if __name__=='__main__':main()
