#!/usr/bin/env python3
"""Close M54 evidence for new half conversions and current-hardware regression."""
import csv,hashlib,json
from collections import Counter
from pathlib import Path
from m54_baseline import ROOT,audit
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
TOPS=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']
def checked(d):
    assert d.get('status')=='PASS' or ('status' not in d and d.get('timing_status')=='NO_DEVICE_PLACE_ROUTE_OR_SIGNOFF' and d.get('mapped_cells'))
    for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_tool_dependency_sha256']:
        for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
def main():
    base=audit();out=ROOT/'reports/m54';out.mkdir(parents=True,exist_ok=True);sources={};artifacts={}
    def manifest(rel):
        path=ROOT/rel;d=json.loads(path.read_text());checked(d);artifacts[rel]=sha(path)
        for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256']:
            for p,h in d.get(key,{}).items():
                (sources if p.startswith(('src/','scripts/','tests/','software/')) else artifacts)[p]=h
        return d
    direct={};commands=0;negative=0
    for top in TOPS:
        manifest(f'build/m54/gsim/rtl/{top}/results.json')
        for suite in ['arithmetic','memory','edges']+(['half'] if 'Integer' not in top else []):
            compact='Deep' in top and suite in ['arithmetic','memory'];label=top+'-'+suite+('-compact' if compact else '-full')
            d=manifest('build/m54/gsim/'+label+'/results.json');assert not d['trace_replay'];commands+=d['commands'];negative+=len(d['negative_controls'])
            direct[label]={k:d[k] for k in ['commands','summary','negative_controls','coverage']}
        d=manifest('build/m54/reserved-eew/'+top+'/results.json');assert d['reserved_cases']==72 and d['commands']==216
        negative+=len(d['negative_controls'])
        d=manifest('build/m54/public-checks/'+top+'/results.json');assert d['monitor_implementation']=='0x5401'
    for p in sorted((ROOT/'build/m54/gsim/corpus').glob('*/results.json')):manifest(str(p.relative_to(ROOT)))
    assert commands==73152,commands
    unit=manifest('build/m54/half-unit/results.json');mapped=manifest('build/m54/half-unit-mapped-bounded/results.json')
    assert unit['vectors']==86136 and unit['half_inputs']==65536 and unit['exhaustive_half_inputs']
    assert mapped['vectors']==1930 and not mapped['exhaustive_half_inputs']
    assert unit['flush_phases']==mapped['flush_phases']==44
    proof=manifest('build/m54/half-round-proof/results.json')
    resize={}
    for label in ['RamVectorFp-full-rtl','RamVectorFp16-compact-rtl']:
        d=manifest('build/m54/fp-resize/'+label+'-results.json');resize[label]={k:d[k] for k in ['commands','summary','coverage']}
        artifacts['build/m54/fp-resize/'+label+'.log']=sha(ROOT/'build/m54/fp-resize'/(label+'.log'))
    assert resize['RamVectorFp-full-rtl']['commands']==11372
    contexts={};context_cases=0;callback_errors=0
    for top in TOPS:
        d=manifest('build/m54/context-image/'+top+'/results.json');contexts[top]=d['metrics'];context_cases+=d['metrics']['cases']
        callback_errors+=d['metrics']['restore_failures']+d['metrics']['save_failures'];negative+=len(d['negative_controls'])
    assert context_cases==2212 and callback_errors==1104
    manifest('build/m54/reference/results.json');manifest('build/m54/compiler/results.json')
    gate=manifest('build/m54/timing/gate/results.json');artifacts.update(gate['input_sha256'])
    assert gate['passes_300MHz'] is None and gate['passes_500MHz'] is None
    assert gate['results']['SpinorVpu']['budget_ns']==3.3 and gate['results']['LishiVpuMemory']['budget_ns']==3.232
    resources={}
    for top in ['SpinorVpu','LishiVpuMemory','FloatingPointConvertResize']:
        d=manifest('build/m54/synth/'+top+'/summary.json');c=d['mapped_cells']
        resources[top]=dict(logic_LUT=sum(v for k,v in c.items() if k.startswith('LUT')),FF=sum(c.get(k,0) for k in ['FDRE','FDSE','FDCE','FDPE']),DSP=c.get('DSP48E2',0),RAM={k:v for k,v in c.items() if k.startswith('RAM')})
    assert resources['SpinorVpu']['logic_LUT']==23227 and resources['SpinorVpu']['FF']==13359
    for top,fp in [('SpinorStandard',True),('SpinorInteger',False)]:
        p=ROOT/f'build/m54/configured/{top}.json';d=json.loads(p.read_text());assert d['fp16_min_conversions']==fp and d['monitor_implementation']=='0x5401';artifacts[str(p.relative_to(ROOT))]=sha(p)
    # Every baseline canonical encoding still has an independently successful sample.
    samples=Counter()
    for label in ['arithmetic-full-fp','memory-full','half-full-fp']:
        f=ROOT/'build/m54/gsim/corpus'/label;events=json.loads((f/'inputs.json').read_text());states=json.loads((f/'expected.json').read_text())
        for e in events:
            if e['kind']=='I' and not states[e['id']]['cause']:samples[e['name']]+=1
    original=list(csv.DictReader((ROOT/'reports/m52/canonical-coverage.csv').open()));rows=[]
    for row in original:
        assert samples[row['name']]>0,row['name'];row['successful_direct_samples']=samples[row['name']];rows.append(row)
    table=out/'canonical-coverage.csv'
    with table.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    assert len(rows)==375
    # Collect exact new source and documentation, retaining historical files separately.
    src=[*sorted((ROOT/'src/main/scala').rglob('*.scala')),
         *sorted((ROOT/'scripts').glob('*m54*.py')),ROOT/'scripts/prove_half_round.py',
         *sorted((ROOT/'tests').glob('*m54*.py')),*sorted((ROOT/'tests').glob('m54*')),
         ROOT/'tests/fp16_reference.c',ROOT/'tests/spike_half_adapter.cc',ROOT/'tests/test_m54_half_unit.py',
         ROOT/'tests/fp_resize_reference_m54.c',ROOT/'software/programs/half-conversions.c',ROOT/'docs/m54-half-conversions.md',ROOT/'CURRENT.md',ROOT/'.gitattributes']
    for p in src:sources[str(p.relative_to(ROOT))]=sha(p)
    for p in [ROOT/'archive/m53/baseline.json',*sorted((ROOT/'archive/m53/source').rglob('*.scala')),
              *sorted((ROOT/'docs/references').glob('m54-*')),ROOT/'build/m54/reference/libresize.so',
              out/'mapped-exhaustive-attempt.json',out/'mapped-exhaustive-attempt-script.py',table]:artifacts[str(p.relative_to(ROOT))]=sha(p)
    for m in [50,51,52,53]:
        p=f'reports/m{m}/receipt.json';artifacts[p]=sha(ROOT/p)
    text=f'''# M54：FP16 最小转换已实现

新增 SEW16 的 vfwcvt.f.f.v / vfncvt.f.f.w，对应 Zvfhmin 的 FP16↔FP32 转换定义。
复用原 RAM、调度和扩缩宽状态机，新增半精度解码/舍入路径；单 lane、单指令在途。
monitor 实现号 0x5401，ABI1、能力位布局及 576 字节上下文格式保持。Orbital 未修改。
具体 ISA 支持/缺口、规范来源和运行条件见 [设计说明](../../docs/m54-half-conversions.md)。

## 新功能的独立证据

- SoftFloat RTL：{unit['vectors']:,} 个向量，穷举全部 65,536 个 FP16 编码扩宽；
  FP32→FP16 覆盖 5 个舍入模式、边界/特殊值及随机数，另检查非法模式和 44 个 flush 时点。
- 真实综合网表：{mapped['vectors']:,} 个代表数值样本和 44 个 flush 时点。是有界子集，
  不称为全部 half 编码的网表覆盖。一次重复的完整网表数值矩阵因运行预算主动停止，
  不计入通过；改以完整 RTL 穷举及代表网表验证收尾，attempt 记录保留。
- 新 half rounder 对 pinned HardFloat 的 10 步 SAT 等价：任意 held raw bits、所有模式/
  特殊标志与 done 非空见证；局部证明，不是整个 VPU 的证明。
- Standard / Deep 真实公共顶层分别完成 4,611 条新增几何/模式/重叠/非法边界命令，
  对照未修改上游 Spike，ISA 明确启用 Zvfhmin。没有把完整 Zvfh 或 SEW16 round-to-odd 放开。
- 独立 SV/SoftFloat 的完整宽度转换回归：{resize['RamVectorFp-full-rtl']['commands']:,} 条命令；
  Deep 代表矩阵 {resize['RamVectorFp16-compact-rtl']['commands']} 条，包含半精度非零 vstart、掩码及 flush。

## 当前硬件回归

四预设的基础算术/访存/扩展访存边界全部在 M54 公共 GSim 顶层重跑；Deep 的基础
算术/访存采用已界定 compact 矩阵。加上半精度矩阵，共 **{commands:,} 条 Spike 差分命令**。
完整 RF/CSR 检查，访存还比较 8KiB RAM、故障/重试和 TL 事务。375 种原有基础编码均有
成功执行点，见 [逐项目录](canonical-coverage.csv)；新增的是两条已有编码的 SEW16 定义，
不是把编码数加二，也不是合规百分比。

保留混合 EEW store 独立拒绝策略每预设 72 场景/216 命令，明确不标为 Spike 一致性。
两个整数预设各检查 320 个浮点/CSR 拒绝点；四预设读取 monitor ID 0x5401 并检查反压。
上下文回归共 **{context_cases:,} 场景、{callback_errors:,} 个前/后效果失败注入**，加损坏镜像
及 ASan/UBSan 校验，原 C ABI 在新硬件保持可用。上述矩阵共 **{negative} 次比较器错误注入**
均检出，包括 token、RF、CSR、RAM、访存故障地址和上下文恢复/所有权。

LLVM19 为真实 FP16↔FP32 strip-mining intrinsic 示例生成目标转换和向量 load/store。
本轮是编译检查，尚未在真实 Orbital/Linux 执行该示例。

## 资源与时序

默认公共顶层 Yosys xcup：**23,227 逻辑 LUT、13,359 FF、9 DSP**；较 M53 同工具
基线 +21 LUT/+155 FF，RAM64M8×32、RAM32M16×6 不变，没有新增 RF 快照或 DSP。
固定 M25 权重和 100ps/link 门槛重跑：公共顶层 **3.300ns**，计算/访存顶层
**3.232ns**，均≤3.333ns。

该模型仍排除 DSP 影响端点、未布局布线/按 ZU15EG-2 校准，不是 STA/SDF。M53 的
实际 Vivado +0.090/+0.042ns 结果仅适用旧 RTL；M54 的器件 300/500MHz 仍未知。
本轮没有要求再跑本地 Vivado。实际 DSP 表不能移用于当前无内部寄存器的 Yosys DSP。

基础 V 的操作数/异常审计、真实退休、VS/FS/FCSR、地址保护/翻译、一致性和驱动
仍有系统工作。Zvbb 尚未实现，Zvkt 尚未完成专门审计；不能声明完整 V/RVA23。

## 基线和复现

变更前 M53 全部证据已验证，48 个 Scala 文件冻结到 archive/m53/source。变更的
4 个历史文件按旧副本核验，其余历史源码/工具/产物严格原散列；新硬件全部产物位于
build/m54，旧 RTL/网表和本地报告保持版本。历史检查通过不计作 M54 硬件回归通过。

在已有 M53 工具及产物的环境运行：

```bash
python3 scripts/verify_m54.py
python3 scripts/verify_m54.py --check-only
```

receipt 绑定源码、独立模型、原始语料、生成 RTL/网表、运行日志、局部证明和条件预算。
没有部署、bitstream、板上运行、整核 difftest 或实际 Linux 上下文切换声明。
'''
    doc=out/'evaluation.md';doc.write_text(text);artifacts[str(doc.relative_to(ROOT))]=sha(doc)
    result=dict(project='Spinor',milestone='M54',status='PASS',hardware_changed=True,feature='SEW16_FP16_FP32_MINIMAL_CONVERSIONS',
        baseline=base,direct_commands=commands,direct_results=direct,canonical_encodings_with_success=375,
        unit_RTL_vectors=unit['vectors'],unit_mapped_bounded_vectors=mapped['vectors'],rounder_bounded_SAT=True,
        resize=resize,context_cases=context_cases,context_callback_failures=callback_errors,negative_controls=negative,
        monitor_implementation='0x5401',full_V=False,full_RVA23=False,actual_Orbital_integrated=False,
        resources=resources,conditional_reference_gate=gate,passes_300MHz=None,passes_500MHz=None,
        source_sha256=sources,artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS M54',commands,'direct Spike commands;',unit['vectors'],'RTL /',mapped['vectors'],'mapped samples;',negative,'negative controls;',len(artifacts),'artifacts')
if __name__=='__main__':main()
