#!/usr/bin/env python3
"""Bind M2 sources, generated RTL, mapping and observed tests in one receipt."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/m2'
TOPS=['RamVector','RamVector16','RamVectorFlops','RamVectorBram','VersionedRegisterFileRam']
LANES=['IntegerLaneBaseline','IntegerLaneSplit','IntegerLaneSplit16']

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(rel):
    return json.loads((ROOT/rel).read_text())

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rf=read('build/test/versioned-rf.json')
    vectors=read('build/test/ram-vector-results.json')
    bench=read('build/test/ram-benchmark.json')
    timing=read('build/timing-reference/results.json')
    monitor=(ROOT/'build/timing-reference/model-check.log').read_text()
    assert rf['status']=='PASS'
    assert set(vectors['models'])=={'RamVector','RamVector16','RamVectorFlops','RamVector-mapped'}
    assert all('PASS ram-vector commands=789 reads=2968' in v for v in vectors['models'].values())
    assert set(bench)=={'RamVector','RamVector16','RamVectorFlops'}
    assert all(len(v)==4 and all(r['instructions']==64 for r in v) for v in bench.values())
    assert 'PASS reference checker deliberate setup=1 hold=1' in monitor
    assert len(timing['results'])==15
    expected={(t,s,f) for t in LANES for s in ['assumption_A','assumption_B'] for f in [300,500]}
    expected|={(t,'zero',300) for t in LANES}
    assert {(r['top'],r['scenario'],r['clock_MHz']) for r in timing['results']}==expected
    assert all(r['functional_trace_matches'] and r['setup_violations']==r['hold_violations']==r['ram_write_violations']==0
               for r in timing['results'] if r['scenario']=='zero')
    assert sha(ROOT/'build/test/timing-reference.stim')==timing['stimulus_sha256']
    assert 'SUCCESS' in (ROOT/'tools/mill-generate.log').read_text()
    resources=[];paths={};artifacts=[]
    for top in TOPS+LANES:
        folder=ROOT/'build/synth'/top
        summary=read(str(folder.relative_to(ROOT)/'summary.json'))
        c=summary['mapped_cells']
        row={'top':top,'logic_LUT':sum(v for k,v in c.items() if k.startswith('LUT')),
             'FF':sum(v for k,v in c.items() if k.startswith('FD')),
             'RAM32M16':c.get('RAM32M16',0),'RAM64M8':c.get('RAM64M8',0),
             'RAMB36E2':c.get('RAMB36E2',0),'CARRY4_logical':c.get('CARRY4',0)}
        row['storage_LUT']=8*(row['RAM32M16']+row['RAM64M8'])
        row['unpacked_LUT_sum']=row['logic_LUT']+row['storage_LUT']
        resources.append(row)
        dest=OUT/top;dest.mkdir(exist_ok=True)
        for name in ['summary.json','stat.json','synth.ys']:
            shutil.copyfile(folder/name,dest/name)
        if (folder/'paths.json').exists():
            paths[top]=read(str(folder.relative_to(ROOT)/'paths.json'))
            shutil.copyfile(folder/'paths.json',dest/'paths.json')
        artifacts += [folder/n for n in ['mapped.json','mapped.v','synth.log','summary.json','stat.json']]
    test_files=['build/test/versioned-rf.json','build/test/ram-vector-results.json','build/test/ram-benchmark.json',
                'build/timing-reference/results.json','build/timing-reference/model-check.log','tools/mill-generate.log']
    for rel in test_files:
        # Keep the timing sweep distinct from the functional test results.
        name='timing-reference.json' if rel.endswith('/results.json') else Path(rel).name
        shutil.copyfile(ROOT/rel,OUT/name)
    sources=[ROOT/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
    sources += [p for d in ['src','scripts','tests','docs'] for p in (ROOT/d).rglob('*')
                if p.is_file() and '__pycache__' not in str(p)]
    artifacts += list((ROOT/'build/rtl').glob('*.sv'))+[ROOT/n for n in test_files]
    artifacts += list((ROOT/'build/timing-reference').glob('*.log'))
    artifacts += [ROOT/'build/test/timing-reference.stim',ROOT/'build/test/ram_vector_tb.sv']
    receipt={'scope':'M2_RAM_FIRST_INTEGER_VECTOR_SUBSET_ONLY','target':'xczu15eg-ffvb1156-2-i',
             'design_targets_MHz':[300,500],'full_RVV_implemented':False,'Valence_core_integrated':False,
             'device_place_route_performed':False,'passes_300MHz':None,'passes_500MHz':None,'bitstream_generated':False,
             'tools':read('tools.lock.json'),'resources':resources,'versioned_rf_tests':rf,'vector_tests':vectors,
             'dependent_vadd_benchmark':bench,'reference_timing':timing,'reference_checker_test':monitor,
             'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)},
             'artifact_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(set(artifacts))}}
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    ram=next(r for r in resources if r['top']=='RamVector')
    ff=next(r for r in resources if r['top']=='RamVectorFlops')
    text=['# ZU15EG-2 M2：RAM 寄存器组与参考延迟仿真','',
          '**当前为整数向量子集。未完成完整 RVV/RVA23、Valence 整核接入、真实器件时序和 bitstream。**','',
          'Mill 1.1.7 / Scala 2.13.18 / Chisel 7.16.0 / firtool 1.160.0；Yosys 0.70+16 和 Icarus 14.0。','',
          '## 本轮设计','',
          '- VLEN128、ELEN64；m1/m2/m4/m8/mf2/mf4/mf8，22 种合法 SEW/LMUL 组合。',
          '- vstart、vxrm、vxsat、vcsr，以及只读 vl/vtype/vlenb；真实 vset* 编码及 x0 特殊规则。',
          '- 每个架构寄存器有两个 RAM 版本，源读已提交版，结果写候选版；完成被接受时翻转 32-bit 版本表。',
          '- 不保存整个 LMUL 寄存器组的 FF 快照；仅缓存 v0 和当前元素，撤销不清空 RAM。',
          '- 当前单元素在途，是存储/提交正确性基线；整数乘除、浮点和 LSU 等仍待实现。','',
          '## 资源','',
          'Yosys `synth_xilinx -family xcup` 的 OOC 映射，无 IOB/时钟缓冲；不是 Vivado 布局后资源。','',
          '| 候选 | 逻辑 LUT | FF | 存储 LUT | RAM32M16 | RAM64M8 | RAMB36E2 |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for r in resources:
        if r['top'] not in TOPS:continue
        text.append('| '+r['top']+' | '+' | '.join(str(r[k]) for k in ['logic_LUT','FF','storage_LUT','RAM32M16','RAM64M8','RAMB36E2'])+' |')
    text += ['',f"同接口、同周期的 RAM/FF 对照：RAM 减少 {100*(1-ram['logic_LUT']/ff['logic_LUT']):.1f}% 逻辑 LUT、{100*(1-ram['FF']/ff['FF']):.1f}% FF。",
             f"RAM32M16、RAM64M8 各占 8 个存储 LUT；自动 RAM 总计 {ram['unpacked_LUT_sum']} 个未打包逻辑+存储 LUT 位置。",
             '这不含 slice 打包、双输出 LUT 合并或布线成本；CARRY4 是逻辑映射，不代表原生 CARRY8 打包。',
             '强制 BRAM 只改变寄存器堆存储提示；该候选尚未做原生 RAMB36E2 模型的网表功能验证。','',
             '## 功能证据','',
             f"- 双版本寄存器堆：{rf['transactions']} 次事务、{rf['reads_checked']} 次读检查、{rf['random_atomic_commits']} 次随机原子提交。",
             '- 三种 M2 RTL 和自动 LUTRAM 映射网表：各 789 条命令、2968 次上下文读检查。',
             '- 覆盖 553 次向量运算、137 次 CSR、99 次配置、7 次撤销和 26 次非法操作。',
             '- 每拍检查版本表在完成接受前保持不变；覆盖目的/源别名、mask/tail/prestart、分数组、完成背压及部分写后撤销。',
             '- 独立 Python 算术/架构状态模型；属于原型子集检查，未做完整 ISA 合规或 Valence 核级仿真。','',
             '## 周期与代价','',
             '每项为 VL=VLMAX、LMUL1 的 64 条依赖 vadd.vv，无完成背压，包含接口/复制/提交开销。','',
             '| 候选 | SEW8 周期/条 | SEW16 | SEW32 | SEW64 |','|---|---:|---:|---:|---:|']
    for top,rows in bench.items():text.append('| '+top+' | '+' | '.join(str(r['cycles_per_instruction']) for r in rows)+' |')
    text += ['', 'M1 的 32-bit 切分原型对应为 51/35/27/23 周期；M2 当前为单元素在途，因此更慢。',
             '节省存储资源不代表提高吞吐；后续需重叠 RAM 访问、执行和候选写回，并保持同一提交协议。','',
             '## 参考时序仿真','',
             '**以下是未校准的假设延迟实验，仅覆盖整数 lane，不是整个 VPU 的时序仿真，也不是 AMD SDF/器件 STA。**',
             '输入在时钟沿后 0.25 ns 发出；Icarus 事件仿真计入自定义 LUT/连线/CARRY/触发器/队列 RAM 延迟，',
             '手工监视 setup/hold 和 RAM 写 setup。未包含位置、实际扇出、PVT、时钟树/偏差和器件速度文件。',
             '时序违规只计数，不向寄存器注入 X；因此结果匹配且所有计数为零才记为该场景通过。','',
             '三个零延迟对照都通过；另用故意缩短 setup/hold 的独立刺激验证监视器能报错。',
             f"每个场景 {timing['stimulus_cycles']} 周期，含四种 SEW、20 种已实现运算、随机停顿和撤销。",'',
             '| 假设（ns） | LUT | 连线 | 每 bit carry | CQ | setup | hold | RAM 读 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for s in ['assumption_A','assumption_B']:
        a=timing['assumptions_ns'][s]
        text.append('| '+s+' | '+' | '.join(str(a[k]) for k in ['LUT','LINK','CARRY','CQ','SETUP','HOLD','RAM'])+' |')
    text += ['', '| 场景 | MHz | 候选 | 结果匹配 | setup / hold / RAM 写违规 |',
             '|---|---:|---|---|---|']
    for r in timing['results']:
        if r['scenario']=='zero':continue
        text.append(f"| {r['scenario']} | {r['clock_MHz']} | {r['top']} | {'是' if r['functional_trace_matches'] else '否'} | {r['setup_violations']} / {r['hold_violations']} / {r['ram_write_violations']} |")
    text += ['', '在 A 假设下，两种切分都通过 300/500 MHz；在 B 假设下，两种切分通过 300 MHz、500 MHz 出现违规及数据错误。',
             '这说明结论依赖延迟假设；支持把 300 MHz 留作基线、继续优化 500 MHz 候选，不能推导真实 ZU15EG 的 Fmax。','',
             '## 映射路径（不带时间）','',
             '| 候选 | 数据路径单元跳数 | 控制路径跳数 | 最大非时钟扇出 |','|---|---:|---:|---:|']
    for top,p in paths.items():
        if top not in TOPS:continue
        ctrl=p['longest_control']['hops'] if p['longest_control'] else '—'
        text.append(f"| {top} | {p['longest_data']['hops']} | {ctrl} | {p['fanout'][0]['loads']} |")
    text += ['', '这些仅为逻辑图跳数；RAM 读和逻辑 CARRY 都按单元计数，不能换算 ns/MHz。',
             '整机 RAM 选择、CSR/地址控制路径尚未做参考延迟仿真。','',
             '## 复现与证据','',
             '- `make bootstrap`；`make verify-m2`；`make package-m2`。',
             '- [机器可读证据与源/产物 SHA-256](receipt.json)',
             '- [原始参考仿真结果](timing-reference.json)、[检查器故意违规对照](model-check.log)',
             '- [设计合同](../../docs/architecture.md)、[M1 原始报告](../../archive/m1/reports/evaluation.md)',
             '- 真实时序、最终 bitstream 仍需支持 XCZU15EG 的 AMD 实现工具；开源结果用于推进设计。','']
    (OUT/'evaluation.md').write_text('\n'.join(text))
    print('Wrote reports/m2/evaluation.md and receipt.json; real-device 300/500 MHz remain unqualified')

if __name__=='__main__':main()
