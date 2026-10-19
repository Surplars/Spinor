#!/usr/bin/env python3
"""Current host ownership evidence, byte-identical defaults and bounded DIEL audit."""
import csv,gzip,hashlib,json,re,sys
from pathlib import Path
from m56_baseline import ROOT,audit
sys.path.insert(0,str(ROOT/'tests'))
from m56_diel_scope import rows
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
TOPS=['SpinorHost','SpinorHostDeep']
def checked(d):
    assert d.get('status')=='PASS' or ('status' not in d and d.get('timing_status')=='NO_DEVICE_PLACE_ROUTE_OR_SIGNOFF' and d.get('mapped_cells')) or d.get('scope')=='UNPLACED_FAMILY_MAX_CELL_AND_ASSUMED_LINK_BUDGET_NOT_STA'
    for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_source_sha256','external_tool_dependency_sha256']:
        for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
def main():
    baseline=audit();out=ROOT/'reports/m56';out.mkdir(exist_ok=True);sources={};artifacts={}
    def bind(rel,h):
        dest=sources if rel.startswith(('src/','scripts/','tests/','software/')) else artifacts
        if rel in dest:assert dest[rel]==h,(rel,'contradictory bindings')
        dest[rel]=h
    def manifest(rel):
        p=ROOT/rel;d=json.loads(p.read_text());checked(d);artifacts[rel]=sha(p)
        for key in ['source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_source_sha256','external_tool_dependency_sha256']:
            for rel,h in d.get(key,{}).items():bind(rel,h)
        return d
    identity=manifest('build/m56/default-identity.json');assert len(identity['tops'])==4
    for row in identity['tops']:
        before=ROOT/row['before'];after=ROOT/row['after'];archived=ROOT/row['archive']
        assert sha(before)==sha(after)==row['sha256'] and sha(archived)==row['archive_sha256']
        assert gzip.decompress(archived.read_bytes())==after.read_bytes()
        for p in [before,after,archived]:artifacts[str(p.relative_to(ROOT))]=sha(p)
    config=manifest('build/m56/configured/results.json');assert config['architectural_fflags_register_removed_in_host']
    ref=manifest('build/m56/corpus/results.json');assert ref['numeric_cases']==3094 and ref['commands']==10146 and ref['host_owned_csr_rejections']==864
    # The independent Spike process resets fflags for each target. Check that
    # the matrix really contains already-set host bits raised again by VPU.
    flags={int(f[1]):int(f[12],16) for f in (l.split() for l in (ROOT/'build/m56/corpus/spike-output.txt').read_text().splitlines())}
    overlap=0
    for c in json.loads((ROOT/'build/m56/corpus/cases.json').read_text()):
        prior=c['initial_flags']^(31 if c['mutate'] else 0);delta=flags[c['target']]
        overlap+=bool(prior&delta)
    assert overlap>0
    results={};commands=0;negative=0;context_cases=0;callback_errors=0
    for top in TOPS:
        manifest(f'build/m56/gsim/rtl/{top}/results.json')
        arithmetic=manifest(f'build/m56/fcsr/{top}/results.json');commands+=arithmetic['commands'];negative+=len(arithmetic['negative_controls'])
        memory=manifest(f'build/m56/memory/{top}/results.json');commands+=memory['commands'];assert memory['commands']==12718
        negative+=sum(len(v['negative_controls']) for v in memory['results'].values())
        context=manifest(f'build/m56/context-image/{top}/results.json');assert context['metrics']['cases']==726
        context_cases+=context['metrics']['cases'];callback_errors+=context['metrics']['restore_failures']+context['metrics']['save_failures'];negative+=len(context['negative_controls'])
        flush=manifest(f'build/m56/flush/{top}/results.json');assert flush['aborted']==1768;negative+=len(flush['negative_controls'])
        diel=manifest(f'build/m56/diel/{top}/results.json');assert diel['encodings']==165 and diel['required_encodings']==164 and diel['review_encodings']==['vmv_x_s'];negative+=len(diel['negative_controls'])
        assert 'samples=43560' in diel['summary'] and 'legal=9783 rejected=1107' in diel['summary']
        results[top]=dict(fcsr=arithmetic['summary'],memory=memory['results'],context=context['metrics'],flush=flush['summary'],diel=diel['summary'])
    assert commands==45728 and context_cases==1452 and callback_errors==556 and negative==30,(commands,context_cases,callback_errors,negative)
    gate=manifest('build/m56/timing/gate/results.json');assert gate['passes_300MHz'] is None and gate['passes_500MHz'] is None
    for label in ['spinor','compute']:manifest(f'build/m56/timing/{label}/budget.json')
    assert {v['budget_ns'] for v in gate['results'].values()}=={3.3}
    resources={}
    for top in ['SpinorHost','LishiVpuMemoryHost']:
        d=manifest(f'build/m56/synth/{top}/summary.json');c=d['mapped_cells']
        resources[top]=dict(logic_LUT=sum(v for k,v in c.items() if k.startswith('LUT')),FF=sum(c.get(k,0) for k in ['FDRE','FDSE','FDCE','FDPE']),DSP=c.get('DSP48E2',0),RAM={k:v for k,v in c.items() if k.startswith('RAM')})
    assert resources['SpinorHost']==dict(logic_LUT=24247,FF=13882,DSP=9,RAM={'RAM32M16':6,'RAM64M8':32})
    scope=rows();assert sum(r['scope']=='REQUIRED' for r in scope)==164 and sum(r['scope']=='EXCLUDED' for r in scope)==226
    table=out/'diel-scope.csv'
    with table.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(scope[0]),lineterminator='\n');w.writeheader();w.writerows(scope)
    for p in [*sorted((ROOT/'src/main/scala').rglob('*.scala')),*sorted((ROOT/'scripts').glob('*m56*.py')),*sorted((ROOT/'tests').glob('*m56*')),
              ROOT/'README.md',ROOT/'CURRENT.md',ROOT/'.gitattributes',ROOT/'docs/cpu-spinor-contract.md',ROOT/'docs/m56-host-fcsr.md']:
        bind(str(p.relative_to(ROOT)),sha(p))
    for p in [table,ROOT/'archive/m55/baseline.json',ROOT/'archive/m55/GenerateM56Baseline.scala',*sorted((ROOT/'archive/m55/source').rglob('*')),
              *sorted((ROOT/'docs/references').glob('m56-*')),out/'pre-short-address-budget.txt',out/'pre-middle-stage-budget.txt']:
        if p.is_file():artifacts[str(p.relative_to(ROOT))]=sha(p)
    for rel,h in json.loads((ROOT/'archive/m55/baseline.json').read_text())['reports'].items():artifacts[rel]=h
    text=f'''# M56：宿主管理 FCSR 与接入边界

本轮新增显式 hostFcsr 模式：宿主保留唯一架构 FCSR，VPU 只锁存执行 frm、累积
本条指令 flags，在原 completion 握手时供 CPU 合并。不会新建 CPU ROB、取指、
标量执行或特权状态。原四种独立预设的生成 SV 与变更前逐字节相同。

[端口/上下文/时序说明](../../docs/m56-host-fcsr.md)、[CPU 合同](../../docs/cpu-spinor-contract.md)。
宿主 monitor ID0x5602，原独立版0x5501；monitor ABI1、上下文 ABI1/576字节保持。

## 新宿主模式验证

- 两个浮点宿主预设，各 **3,094 个数值场景、9,282 条配置/状态/向量命令**，
  对照未修改 Spike 的整 RF/CSR 结果。每条目标指令前独立参考将 flags 清零以取得
  本条完整异常，再由测试 CPU 所有者模型在退休时与当前宿主 flags OR。
- 每预设另有 **864 个宿主 FCSR CSR 拒绝点**（三个地址、六种动作、源/目的零等），
  不将这部分称为 Spike 一致性。每预设总计10,146命令；数值比较采用合法 frm，
  保留 frm 只比较共同拒绝的指令及已定义策略，未把 RTZ/搬运的保留行为差异当错误。
- 覆盖 FP32/64、half 转换、RTZ/ROD、几何、mask/VL0、整数/Zvbb 混合，检查
  接收后宿主 frm/flags 扰动不改变执行快照。语料中有 **{overlap} 个**入口/当前 flags
  已置位且目标再次产生该异常的场景，验证 delta 不是 sticky flags XOR。
- 两宿主预设各重跑完整 memory **3,154** 和 edges **9,564** 命令，检查普通 RAM、
  总线/错误地址、前缀/分段恢复、停止等。与 FCSR 矩阵合计 **{commands:,} 条新宿主命令**。
  访存期望来自不可变 M55/上游独立语料，DUT 是新的宿主公共顶层。
- 上下文 **{context_cases:,} 场景、{callback_errors} 个前/后效果失败注入**，使用原 C API，
  execute 回调将 FCSR 路由到测试 CPU 所有者，其余送真实 VPU。独立 Python 镜像、
  4,608 个位翻转、19 个坏头、576 个截断长度及 ASan/UBSan 通过；尚未接实际 CPU。
- 每预设 **1,768 个 FP flush 时点**（8 编码×221），包含执行和持有完成阶段，
  比较全部64个RF字与架构状态，未发布 flags/版本，检查宿主 monitor ID。
- 共 **{negative} 次比较器/协议错误注入**检出，含错误 token/RF/CSR/delta、提前合并
  flags、load/RAM/tval、上下文所有权和完成延迟篡改。配置生成还拒绝 integer/host
  与未知所有者，检查 host SV 不再含架构 fflags 寄存器，standalone 保留它。

测试 CPU 所有者、CSR 回调和测试执行器都是软件模型，未综合成另一个 CPU。
宿主输入扰动是快照压力测试，不授权年轻 CPU 指令越过全局退休。

## Zvkt 清单与有限延迟审计

冻结原规范后明确：浮点算术/除法/访存等是排除项，不能笼统用它们的可变时长
否定 Zvkt；vfslide1up/down.vf 为明确列入的搬运例外。旧 M55 说明对此过于笼统，
本轮以 [清单](diel-scope.csv) 为准：391种目录中164种 required、226种 excluded，
vmv.x.s 受 copy 列表速记文字影响列 review，并保守额外测试。

两个宿主预设各 **165种编码×22种几何×3种掩码配置×4种数据模式=43,560样本**。
每预设合法组9,783、非法几何组1,107，各组固定控制条件下完成时长全部一致。
变化活动/非活动数据，保持被豁免的 gather 索引/slide amount；merge 选择数据另变。
测量 command 接收到 completion.valid，不把反压和 RF 检查时长计为执行时间。
这是当前公共接口的有限抽样，不验证数值，也不是全输入 DIEL 证明或完整 Zvkt 合规。

## 资源和固定条件预算

宿主公共顶层 Yosys xcup：**24,247逻辑LUT、13,882FF、9DSP**，相对M55默认版
+63LUT/-6FF，RAM64M8×32、RAM32M16×6保持。旧独立版SV逐字节一致，复用其
M55历史验证/映射证据，不冒充M56新增回归。Deep有本轮功能和延迟抽样，未另声明
其完整器件 PPA。

宿主模式初次计算顶层3.482ns未过；尝试无新增状态的地址改写反而达到4.982ns。
最终将单位步长低16位/中16位计算分为两拍，复用地址/进位寄存器，每个单位步长
元素地址增加一拍；跨步/索引的16位加法用两段8位carry-select，拍数保持。
早期诊断日志保留，工具自路径键错误也已修正；未将任何失败运行计为通过。

正式重新综合后，固定 M25 权重、100ps/link：公共 **3.300ns**、计算/访存
**3.300ns**，均≤3.333ns。网表压缩仅节约存储，预算读取的是同一 JSON 网络，
未改变权重/门槛。主IO与DSP影响端点不覆盖，无布局布线/真实时钟，未按-2校准，
不是STA/SDF；新宿主侧带还需SoC时序约束。**M56实际300/500MHz仍未知**。
M53本地OOC结果仅适用于旧RTL。

## 基线与复现

变更前M55散列审计通过，52个Scala文件、README/CURRENT/.gitattributes及CPU合同
冻结；变动历史源码从archive/m53/m54/m55核验，其余工具和产物保持。四种旧预设的
变更前SV也压缩冻结，当前输出与解压原件逐字节一致。

本轮一次派生访存语料复制耗尽工作区空间，未完成运行不计通过；随后改为新语料
压缩存储/流式输入并全部重跑，历史证据未删除。新综合网表也无损压缩保存。

已有M55固定工具和参考产物的工作区：

```bash
python3 scripts/verify_m56.py
python3 scripts/verify_m56.py --check-only
```

receipt绑定源码、独立参考/语料、CPU回调、生成模型/SV/压缩网表、运行日志和预算。
没有修改Orbital/Valence，没有部署、bitstream、板上或Linux整核接入声明。原生CPU
退休/权限/VS/FS、VM/PMP/一致性及ARM作业驱动仍需接入验证。
'''
    (out/'evaluation.md').write_text(text);sources['reports/m56/evaluation.md']=sha(out/'evaluation.md')
    receipt=dict(status='PASS',milestone=56,name='Spinor',historical_audit=baseline,standalone_presets_byte_identical=True,
      host_fcsr=True,host_monitor_implementation='0x5602',standalone_monitor_implementation='0x5501',commands=commands,numeric_cases_per_host=3094,csr_rejections_per_host=864,overlapping_sticky_flag_cases=overlap,
      results=results,context_cases=context_cases,context_callback_errors=callback_errors,negative_controls=negative,mapped_resources=resources,conditional_gate=gate['results'],passes_300MHz=None,passes_500MHz=None,
      zvkt_compliance_claimed=False,full_rvv=False,full_rva23=False,source_sha256=sources,artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PASS M56 bound evidence',commands,'new host commands',len(artifacts),'artifacts')
if __name__=='__main__':main()
