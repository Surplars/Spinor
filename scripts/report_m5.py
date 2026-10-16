#!/usr/bin/env python3
"""M5 write-stage evidence, with the user-supplied M4 implementation kept distinct."""
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/m5'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def cells(folder):
    c=read(folder/'summary.json')['mapped_cells']
    return {'logic_LUT':sum(v for k,v in c.items() if k.startswith('LUT')),
            'FF':sum(v for k,v in c.items() if k.startswith('FD')),
            'DSP48E2':c.get('DSP48E2',0),'RAM64M8':c.get('RAM64M8',0),
            'RAM32M16':c.get('RAM32M16',0),
            'storage_LUT':8*(c.get('RAM64M8',0)+c.get('RAM32M16',0))}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Manual report generation must not accept previous results while a newer
    # RTL or mapped design is awaiting verification.
    freshness=[('build/test/fp-vector-results.json','build/rtl/RamVectorFp.sv'),
               ('build/test/fp-vector-mapped-results.json','build/synth/RamVectorFp/mapped.v'),
               ('build/test/write-cone.json','build/synth/RamVectorFp/mapped.json'),
               ('build/synth/RamVectorFp/paths.json','build/synth/RamVectorFp/mapped.json')]
    for result,source in freshness:
        assert (ROOT/result).stat().st_mtime_ns >= (ROOT/source).stat().st_mtime_ns, f'Stale result: {result}'
    vector=read(ROOT/'build/test/fp-vector-results.json')
    mapped=read(ROOT/'build/test/fp-vector-mapped-results.json')
    integer=read(ROOT/'build/test/fp-integer-results.json')
    other=read(ROOT/'build/test/ram-vector-results.json')
    assert vector['status']==mapped['status']=='PASS'
    assert vector['commands']==mapped['commands']==1649
    assert vector['coverage']==mapped['coverage'] and vector['coverage']['flushes']==102
    assert vector['coverage']['context_write_flush']==2 and vector['write_stage_assertions_enabled']
    cycles=lambda s:int(re.search(r'cycles=(\d+)',s)[1])
    assert cycles(vector['test_summary'])==cycles(mapped['test_summary'])
    assert 'commands=789 reads=2968' in integer['models']['RamVectorFp']
    for top in ['RamVector','RamVector16','RamVectorFlops']:
        assert 'commands=789 reads=2968' in other['models'][top]
    for rel,h in read(ROOT/'tools/m5-tested-rtl-sha256.json').items():assert sha(ROOT/rel)==h,rel
    m4=read(ROOT/'archive/m4/reports/receipt.json')
    assert sha(ROOT/'build/rtl/FloatingPointLane.sv')==m4['artifact_sha256']['build/rtl/FloatingPointLane.sv']
    lane=read(ROOT/'archive/m4/reports/fp-lane-results.json')
    assert lane['status']=='PASS' and lane['vectors']==6811
    deps=read(ROOT/'third_party/fp-dependencies.json')
    for name,h in deps['local_sources_sha256'].items():
        assert sha(ROOT/'third_party/berkeley-hardfloat/src/main/scala'/name)==h,name
    folder=ROOT/'build/synth/RamVectorFp'
    current=cells(folder);old=cells(ROOT/'archive/m4/reports/RamVectorFp')
    paths=read(folder/'paths.json');oldpaths=read(ROOT/'archive/m4/reports/RamVectorFp/paths.json')
    cone=read(ROOT/'build/test/write-cone.json');assert cone['status']=='PASS'
    assert current['DSP48E2']==8 and current['RAM64M8']==32 and current['RAM32M16']==5
    local=Path('/workspace/zu15-vpu-local-results')
    first=local/'m4-300MHz-20261016-092014/assessment.json'
    resume=local/'m4-300MHz-resume-20261016-094747/assessment.json'
    baseline=None
    if first.exists() and resume.exists():
        f=read(first);r=read(resume)
        baseline={'scope':'M4_ONLY_USER_VIVADO_2025_1_OOC','resources':f['resources'],
                  'timing':r['timing'],'limitations':r['limitations'],
                  'DSP_export_completed':r['DSP_export_completed'],'DSP_arc_rows':r['DSP_arc_rows'],
                  'routed_dcp_sha256':r['artifact_sha256']['routed.dcp'],
                  'source_assessments_sha256':{str(p):sha(p) for p in [first,resume]}}
        (OUT/'vivado-m4-baseline.json').write_text(json.dumps(baseline,indent=2)+'\n')
    elif (OUT/'vivado-m4-baseline.json').exists():baseline=read(OUT/'vivado-m4-baseline.json')
    reference=None
    probe=ROOT/'build/rapidwright/m4-timing/probe.json'
    if probe.exists():
        reference=read(probe)
        for path,h in reference['source_or_artifact_sha256'].items():assert sha(Path(path))==h,path
        shutil.copyfile(probe,OUT/'rapidwright-m4-reference.json')
        shutil.copyfile(probe.with_name('probe.log'),OUT/'rapidwright-m4-reference.log')
    artifacts=[]
    for name in ['summary.json','stat.json','synth.ys','paths.json']:
        shutil.copyfile(folder/name,OUT/name)
    artifacts += [folder/n for n in ['summary.json','stat.json','synth.ys','paths.json','mapped.v','mapped.json','synth.log']]
    for rel in ['build/test/fp-vector-results.json','build/test/fp-vector-mapped-results.json',
                'build/test/fp-integer-results.json','build/test/ram-vector-results.json',
                'build/test/write-cone.json',
                'tools/m5-tested-rtl-sha256.json','tools/mill-generate.log']:
        shutil.copyfile(ROOT/rel,OUT/Path(rel).name);artifacts.append(ROOT/rel)
    shutil.copyfile(ROOT/'archive/m4/reports/fp-lane-results.json',OUT/'unchanged-lane-M4-results.json')
    artifacts += [ROOT/'build/test'/n for n in ['fp-vector.log','fp-vector-mapped.log','RamVectorFp.log',
                    'fp_vector_tb.sv','ram_vector_fp_integer_tb.sv','ram_vector_tb.sv',
                    'fp-vector-write-stage-assertions.sv','fp-vector.compile.log','fp-vector-mapped.compile.log']]
    artifacts += list((ROOT/'build/rtl').rglob('*.sv'))
    sources=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','README.md','tools.lock.json']]
    sources += [p for d in ['src','scripts','tests','docs','third_party'] for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    text=['# ZU15EG-2 M5：候选 RAM 写回流水','',
          '本轮针对用户 M4 实现中 FP 状态→BRAM 写地址及 BRAM 读改写路径增加寄存器边界。',
          '**M5 尚未运行 Vivado 布局布线，300/500 MHz 均未验证；本轮 ISA 覆盖保持 M4 子集。**','',
          '## 写入与提交','',
          '- 仅在 RamVectorFp 中寄存候选地址 5-bit、字节使能 16-bit、数据 128-bit，加有效位，共 150 个 FF。',
          '- 候选写入下一拍进入 RAM；该级可连续每拍接收一个写请求。完成、上下文访问及下一条指令等待它排空。',
          '- flush 同拍禁止候选写入 RAM，并清除有效位；版本表和 FP flags 仍只在完成接受时提交。',
          '- 上下文写入直接旁路，保持 context.fire 当拍生效，后续 flush 不丢弃已经接受的架构写入。',
          '- 上下文旁路直接使用 IO 地址/数据/掩码，避免通过汇总请求选择器重新引入执行状态依赖。',
          '- 数据阵列仍在 RAM；没有恢复整组源/目的 FF 快照。当前执行器仍是单元素在途。','',
          '## 检查结果','',
          f"- 向量 RTL 与含 DSP 的映射网表：各 1649 条命令、7358 次读取，均 {cycles(vector['test_summary'])} 周期。",
          '- 102 次指令撤销，覆盖连续 0..95 周期及后续窗口；另有 2 次上下文写入后 flush。',
          '- RTL 仿真实际加载 Chisel 7 的独立断言层，检查候选未排空时没有上下文写冲突或版本提交。',
          '- [映射网表组合锥检查](write-cone.json)：RAM 写地址、数据、使能均不再直接依赖 FP 单元状态寄存器。',
          '- FP 开启的整数回归：789 条命令、2968 次读取、73298 周期，与 M4 相同。',
          '- 纯整数 RAM、16-bit 切分和 FF 对照三个顶层各通过 789 条命令。',
          '- FP lane RTL 与 M4 逐字节相同，复用其 6811 组 SoftFloat 差分、52 个锚点和 205 个撤销/复位检查；本轮未重复运行该 lane 检查。',
          '- 新增撤销和上下文检查改变了总测试负载，不能用 166204 与 M4 的 160130 直接比较硬件性能。','',
          '## Yosys 映射','',
          '| 阶段 | 逻辑 LUT | FF | DSP48E2 | 存储 LUT | 数据跳数 | 控制跳数 | 最大扇出 |',
          '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,r,p in [('M4',old,oldpaths),('M5',current,paths)]:
        text.append(f"| {name} | {r['logic_LUT']} | {r['FF']} | {r['DSP48E2']} | {r['storage_LUT']} | {p['longest_data']['hops']} | {p['longest_control']['hops']} | {p['fanout'][0]['loads']} |")
    text += ['', 'RAM 映射保持 32 RAM64M8 + 5 RAM32M16。全局最长数据链仍在浮点输入重编码附近；',
             '控制扇出上升也需要关注，不能凭增加流水或无时间跳数就宣称实际频率提高。',
             '新的写回寄存器边界切断了执行握手直接进入 RAM 端口的依赖，但最终关键路径是否转移须用 M5 实现验证。','',
             '## 本地 M4 物理基线与 RapidWright','',
             '- 用户 Vivado 2025.1：7754 总 LUT、6309 FF、6 DSP、2 BRAM36；11953 条应布线网络全部完成。',
             '- 3.333 ns 下 setup +0.346 ns、hold +0.042 ns；HD.CLK_SRC 未指定，宿主 IO 未约束。',
             '- 六个 DSP 边界表共 546 条记录已匹配到 DCP/EDIF；Vivado 将 A/B/P 寄存器吸收进 DSP。',
             '- [基线记录](vivado-m4-baseline.json)只对应 M4，不能套用到 M5 或 Yosys 网表。']
    if reference:
        text += ['- [RapidWright 参考图实验](rapidwright-m4-reference.json)：'+reference['status']+'。',
                 '- DSP 文件夹构造参数在固定版本中需要兼容处理，已记录是否应用；没有修改上游 JAR。',
                 '- 参考图不包含完整时钟树/hold/速度等级校准，也未证明 DSP 内部所有路径覆盖；图权重不转换为 Fmax。']
    text += ['', '## 复现','',
             '`make bootstrap` → `make verify-m5` → `make package-m5`。本轮已逐项运行必要检查。',
             '可选 RapidWright 实验需要用户提供匹配的 DCP、同名 EDIF 与 DSP 文件夹，命令见 [工具说明](../../docs/rapidwright.md)。',
             '[输入与产物散列](receipt.json)。下一次 Windows 评估必须使用 M5 RTL 重新实现，不能使用 M4 的 -Checkpoint 续跑来评估 M5。','',
             'LSU、完整整数/浮点指令、Valence 及统一 FCSR 接入仍未完成，本轮没有新增指令或发布完整 RVV/RVA23 声明。','']
    (OUT/'evaluation.md').write_text('\n'.join(text))
    receipt={'scope':'M5_CANDIDATE_RAM_WRITE_STAGE','target':'xczu15eg-ffvb1156-2-i',
             'full_RVV_implemented':False,'Valence_core_integrated':False,'vector_LSU_implemented':False,
             'M5_device_place_route_performed':False,'M5_passes_300MHz':None,'M5_passes_500MHz':None,'bitstream_generated':False,
             'resources':current,'M4_Yosys_resources':old,'vector_test':vector,'DSP_mapped_test':mapped,
             'mapped_RAM_write_cone':cone,
             'integer_test':integer,'integer_only_test':other,'FP_lane_validation_reused_from_M4':True,
             'FP_lane_RTL_sha256':sha(ROOT/'build/rtl/FloatingPointLane.sv'),'M4_Vivado_baseline':baseline,
             'RapidWright_experiment_on_M4':reference,'tools':read(ROOT/'tools.lock.json'),
             'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(sources))},
             'artifact_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(artifacts))}}
    extra=[p for p in OUT.rglob('*') if p.is_file() and p.name!='receipt.json']
    extra += [p for m in ['m1','m2','m3','m4'] for p in (ROOT/f'archive/{m}/reports').rglob('*') if p.is_file()]
    receipt['artifact_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in sorted(extra)})
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Wrote M5 report: functional/mapping evidence; no M5 device-frequency qualification')

if __name__=='__main__':main()
