#!/usr/bin/env python3
"""Bind current hardware, independent oracles and fixed conditional timing."""
import csv,hashlib,json,sys
from collections import Counter
from pathlib import Path
from m55_baseline import ROOT,audit,historical
sys.path.insert(0,str(ROOT/'tests'))
from m55_zvbb_events import catalog
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
TOPS=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']
def checked(d):
    assert d.get('status')=='PASS' or ('status' not in d and d.get('timing_status')=='NO_DEVICE_PLACE_ROUTE_OR_SIGNOFF' and d.get('mapped_cells')) or (d.get('scope')=='UNPLACED_FAMILY_MAX_CELL_AND_ASSUMED_LINK_BUDGET_NOT_STA' and d.get('passes_300MHz') is None)
    for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_source_sha256','external_tool_dependency_sha256']:
        for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
def main():
    base=audit();out=ROOT/'reports/m55';out.mkdir(parents=True,exist_ok=True);sources={};artifacts={}
    def bind(rel,h):
        target=sources if rel.startswith(('src/','scripts/','tests/','software/')) else artifacts
        if rel in target:assert target[rel]==h,(rel,'contradictory evidence')
        target[rel]=h
    def manifest(rel):
        p=ROOT/rel;d=json.loads(p.read_text());checked(d);artifacts[rel]=sha(p)
        for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_source_sha256','external_tool_dependency_sha256']:
            for rel,h in d.get(key,{}).items():bind(rel,h)
        return d
    manifest('build/m55/reference/results.json');manifest('build/m55/compiler/results.json')
    model=json.loads((ROOT/'build/spike-model/results.json').read_text());spike=next((ROOT/'tools/spike').glob('riscv-isa-sim-*'))/'riscv'
    upstream=[spike/'encoding.h',spike/'riscv.mk.in',spike/'v_ext_macros.h',spike/'zvk_ext_macros.h',*[spike/'insns'/(e['name']+'.h') for e in catalog()]]
    for p in upstream:
        rel=str(p.relative_to(ROOT));h=sha(p);assert h==model['model_source_sha256'][rel];artifacts[rel]=h
    direct={};commands=0;negative=0;restarts={};flushes={};contexts={};context_cases=0;errors=0
    for top in TOPS:
        manifest(f'build/m55/gsim/rtl/{top}/results.json')
        for suite in ['arithmetic','memory','edges']+(['half'] if 'Integer' not in top else [])+['zvbb']:
            compact='Deep' in top and suite in ['arithmetic','memory'];label=top+'-'+suite+('-compact' if compact else '-full')
            d=manifest('build/m55/gsim/'+label+'/results.json');assert not d['trace_replay'];commands+=d['commands'];negative+=len(d['negative_controls'])
            assert d['checked_registers_per_command']==32
            direct[label]={k:d[k] for k in ['commands','summary','negative_controls','coverage']}
        d=manifest(f'build/m55/restart/{top}/results.json');assert d['cases']==1448 and d['reserved_alias_cases']==40 and d['nonzero_vstart_cases']==1408
        restarts[top]={k:d[k] for k in ['commands','cases','reserved_alias_cases','nonzero_vstart_cases']};negative+=len(d['negative_controls'])
        d=manifest(f'build/m55/flush/{top}/results.json');assert d['aborted']==3536
        flushes[top]={k:d[k] for k in ['aborted','summary']};negative+=len(d['negative_controls'])
        d=manifest(f'build/m55/public-checks/{top}/results.json');assert d['monitor_implementation']=='0x5501'
        d=manifest(f'build/m55/reserved-eew/{top}/results.json');assert d['reserved_cases']==72;negative+=len(d['negative_controls'])
        d=manifest(f'build/m55/context-image/{top}/results.json');contexts[top]=d['metrics'];context_cases+=d['metrics']['cases'];errors+=d['metrics']['restore_failures']+d['metrics']['save_failures'];negative+=len(d['negative_controls'])
    assert commands==101584 and context_cases==2212 and errors==1104
    for p in sorted((ROOT/'build/m55/gsim/corpus').glob('*/results.json')):manifest(str(p.relative_to(ROOT)))
    for p in sorted((ROOT/'build/m54/gsim/corpus').glob('*/results.json')):manifest(str(p.relative_to(ROOT)))
    units={}
    for label in ['lane','lane-mapped']:
        d=manifest(f'build/m55/{label}/results.json');units[label]={k:d[k] for k in ['mapped','cycles_per_top','exhaustive_byte_inputs','results']}
        assert d['exhaustive_byte_inputs'];negative+=2*len(d['results'])
    assert negative==124,negative
    proof=manifest('build/m55/bit-proof/results.json')
    resize={}
    for top in ['RamVectorFp','RamVectorFp16']:
        label=top+'-compact-rtl';d=manifest(f'build/m55/fp-resize/{label}-results.json');assert d['commands']==141
        resize[top]={k:d[k] for k in ['commands','summary','coverage']}
        for suffix in ['.log','-compile.log']:p=ROOT/'build/m55/fp-resize'/(label+suffix);artifacts[str(p.relative_to(ROOT))]=sha(p)
    gate=manifest('build/m55/timing/gate/results.json');artifacts.update(gate['input_sha256'])
    for label in ['spinor','compute']:manifest(f'build/m55/timing/{label}/budget.json')
    assert gate['passes_300MHz'] is None and gate['results']['SpinorVpu']['budget_ns']==3.292 and gate['results']['LishiVpuMemory']['budget_ns']==3.232
    resources={}
    for top in ['SpinorVpu','LishiVpuMemory','IntegerLaneSplit','IntegerLaneSplit16']:
        d=manifest(f'build/m55/synth/{top}/summary.json');c=d['mapped_cells']
        resources[top]=dict(logic_LUT=sum(v for k,v in c.items() if k.startswith('LUT')),FF=sum(c.get(k,0) for k in ['FDRE','FDSE','FDCE','FDPE']),DSP=c.get('DSP48E2',0),RAM={k:v for k,v in c.items() if k.startswith('RAM')})
    assert resources['SpinorVpu']==dict(logic_LUT=24184,FF=13888,DSP=9,RAM={'RAM32M16':6,'RAM64M8':32})
    for top,fp in [('SpinorStandard',True),('SpinorInteger',False)]:
        p=ROOT/f'build/m55/configured/{top}.json';d=json.loads(p.read_text());assert d['zvbb'] and d['fp16_min_conversions']==fp and d['monitor_implementation']=='0x5501';artifacts[str(p.relative_to(ROOT))]=sha(p)
    samples=Counter();geometry={e['name']:set() for e in catalog()}
    for folder in [ROOT/'build/m54/gsim/corpus'/l for l in ['arithmetic-full-fp','memory-full','half-full-fp']]+[ROOT/'build/m55/gsim/corpus/zvbb']:
        events=json.loads((folder/'inputs.json').read_text());states=json.loads((folder/'expected.json').read_text())
        for e in events:
            if e['kind']=='I' and not states[e['id']]['cause']:
                samples[e['name']]+=1
                if e['name'] in geometry:geometry[e['name']].add((e['sew'],e['lmul']))
    rows=list(csv.DictReader((ROOT/'reports/m54/canonical-coverage.csv').open()))
    for e in catalog():rows.append(dict(family='zvbb',name=e['name'],match=f'0x{e["match"]:08x}',mask=f'0x{e["mask"]:08x}',successful_direct_samples=0))
    for row in rows:assert samples[row['name']]>0,row['name'];row['successful_direct_samples']=samples[row['name']]
    assert len(rows)==391 and len({r['name'] for r in rows})==391
    for e in catalog():assert len(geometry[e['name']])==(15 if e['name'].startswith('vwsll') else 22),(e['name'],geometry[e['name']])
    table=out/'canonical-coverage.csv'
    with table.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    cat=out/'zvbb-catalog.json';cat.write_text(json.dumps([dict(e,successful_samples=samples[e['name']],successful_sew_lmul=sorted(geometry[e['name']])) for e in catalog()],indent=2)+'\n')
    sourcefiles=[*sorted((ROOT/'src/main/scala').rglob('*.scala')),*sorted((ROOT/'scripts').glob('*m55*.py')),*sorted((ROOT/'tests').glob('*m55*')),
        ROOT/'tests/spike_zvbb_adapter.cc',ROOT/'software/programs/bit-features.S',ROOT/'software/programs/bit-features.h',ROOT/'docs/m55-zvbb.md',ROOT/'README.md',ROOT/'CURRENT.md',ROOT/'.gitattributes']
    for p in sourcefiles:bind(str(p.relative_to(ROOT)),sha(p))
    for p in [table,cat,*sorted((out/'proof-attempt').glob('*')),out/'pre-width-stage-gate.txt',ROOT/'archive/m54/baseline.json',*sorted((ROOT/'archive/m54/source').rglob('*')),*sorted((ROOT/'docs/references').glob('m55-*'))]:
        if p.is_file():artifacts[str(p.relative_to(ROOT))]=sha(p)
    for rel,h in json.loads((ROOT/'archive/m54/baseline.json').read_text())['reports'].items():artifacts[rel]=h
    text=f'''# M55：Zvbb 位操作实现与当前硬件回归

四种预设均实现 10 类操作、16 种 Zvbb 编码；VLEN128/ELEN64、单 lane、单指令在途。
循环移位和计数按三级寄存，ALU 的 6/7 拍、II=1 保持，RAM/TileLink/上下文 ABI 保持。
monitor 实现号 0x5501，生成 manifest 明确列出 zvbb。详见 [设计与边界](../../docs/m55-zvbb.md)。

## 功能证据

- 新增集合每预设 **7,108 条公共端口 Spike 差分命令**；四预设共 28,432 条。
  数字包含配置/CSR 命令。规范内 16 种编码均有成功样本：普通操作覆盖 22 种合法
  SEW/LMUL 几何，扩宽左移覆盖 ELEN64 下 15 种可执行几何；边界还有掩码、VL0、
  立即数 0/31/32/63、移位高位忽略、源/目的重叠、未对齐和非法目的 EMUL。
- 当前 M55 顶层重新执行基础算术/访存/扩展边界/half，加上新增 Zvbb，共
  **{commands:,} 条 Spike 差分命令**。每条比较全部 32 个向量寄存器和 CSR，访存
  比较 8KiB RAM、TL 事务与故障信息。Deep 的基础算术/访存使用有界 compact 矩阵，
  edges、half、Zvbb 保持完整定义。391 种目录编码各有成功样本，非合规百分比。
- 每预设独立 Python 重启/规范策略：**1,448 场景、4,344 命令**，其中 1,408 个
  非零 vstart 场景和 40 个 v0 混合 EEW 源别名拒绝场景。该矩阵不标为 Spike 比较。
  同时重跑原有 mixed-EEW store 72 场景/216 命令每预设。
- 每预设公共顶层 **3,536 个 flush 时点**（16 编码×221 时点），每次比较全部
  64 个 RF 字、CSR、无过早/残留完成和无 TL 流量，含 held completion 阶段。
- 独立 Python 数值/精确周期模型：三种 ALU 各 {units['lane']['cycles_per_top']:,} 拍，
  含每个新增 ALU 选择码全部 256 个字节输入，SEW8/16/32/64 和随机流、队列反压/flush。
  真实 Yosys 网表的两个分段 ALU 各 {units['lane-mapped']['cycles_per_top']:,} 拍，字节穷举保留，
  其他边界/随机部分采用有界子集；不称为全操作数穷举。
- 局部 bit pipeline 对直接按位语义的 10 步 SAT 等价，任意 held 64 位输入、全部
  4 个 SEW、8 个旁路操作，拆成 32 个证明；每个单独证明第 8 步 done，避免空过。范围不包含
  整个 VPU、动态输入流或系统调度，andn/vwsll 另由数值/差分和网表测试覆盖。
- 浮点宽度控制前移后，两种分段顶层各执行 141 条独立 SV/SoftFloat 转换回归，
  含 nonzero vstart、half 和 flush。宽矩阵的旧单元证明保持历史版本，不冒充本轮重跑。
- 上下文 **{context_cases:,} 场景、{errors:,} 个前/后效果失败注入**，保留 ASan/UBSan
  校验和 576 字节 ABI；四预设监控 ID/反压、两个整数预设各 320 个禁用 FP 拒绝点。
  上述测试合计 **{negative} 次比较器数据/标记/状态/上下文错误注入**均检出。

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
'''
    (out/'evaluation.md').write_text(text);sources['reports/m55/evaluation.md']=sha(out/'evaluation.md')
    result=dict(status='PASS',milestone=55,name='Spinor',historical_audit=base,monitor_implementation='0x5501',zvbb_encodings=16,canonical_encodings=391,
       spike_commands=commands,direct=direct,restarts=restarts,flushes=flushes,contexts=contexts,unit_checks=units,bit_proof=proof['scope'],resize_checks=resize,negative_controls=negative,
       mapped_resources=resources,conditional_gate=gate['results'],passes_300MHz=None,passes_500MHz=None,full_rvv=False,full_rva23=False,zvkt_claimed=False,
       source_sha256=sources,artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS M55 evidence',commands,'Spike commands',len(artifacts),'artifacts')
if __name__=='__main__':main()
