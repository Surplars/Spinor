#!/usr/bin/env python3
"""Bind registered-boundary tests, all-bit isolation checks and conditional timing."""
import gzip
import hashlib
import json
import re
from pathlib import Path
from m61_build import ROOT,OUT,MODELS,sha

ADDED={'src/main/scala/vpu/SpinorIsolated.scala','src/main/scala/vpu/GenerateIsolated.scala'}
RETIMED={'src/main/scala/vpu/'+name+'.scala' for name in
         ('SpinorVpu','VpuMonitor','VectorMemoryEngine','RamVector','MemoryRamVector')}


def baseline():
    lock=json.loads((ROOT/'archive/m60/baseline.json').read_text())
    assert lock['documentation_evidence_audit_passed'] and not lock['legacy_hardware_changed']
    assert sha(ROOT/'reports/m60/receipt.json')==lock['receipt_sha256']
    for rel,h in lock['archive_sha256'].items():assert sha(ROOT/rel)==h,rel
    prior=json.loads((ROOT/'reports/m60/receipt.json').read_text())
    legacy={rel:h for rel,h in prior['source_sha256'].items() if rel.endswith('.scala')}
    actual={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert len(legacy)==54 and {rel:actual[rel] for rel in legacy if rel not in RETIMED}=={rel:h for rel,h in legacy.items() if rel not in RETIMED}
    for rel in RETIMED:assert sha(ROOT/'archive/m60/source'/rel)==legacy[rel],rel
    assert set(actual)-set(legacy)==ADDED
    direct=json.loads((OUT/'legacy/results.json').read_text());check(direct)
    assert direct['status']=='PASS' and set(direct['configs'])==set(MODELS)
    for row in direct['configs'].values():assert row['byte_identical']
    return dict(status='PASS',prior_commit=lock['commit'],unchanged_legacy_scala_sources=49,
                opt_in_retimed_scala_sources=sorted(RETIMED),legacy_direct_sv_byte_identical=True,added_scala_sources=sorted(ADDED))


def check(d):
    for group in ('source_sha256','artifact_sha256'):
        for rel,h in d.get(group,{}).items():assert sha(ROOT/rel)==h,rel
    if 'oracle_binary' in d:assert sha(ROOT/d['oracle_binary'])==d['oracle_binary_sha256']


def audit():
    baseline();p=ROOT/'reports/m61/receipt.json';d=json.loads(p.read_text());assert d['status']=='PASS'
    assert d['legacy_default_rtl_changed'] is False and d['hardware_changed'] is True and d['isolated_core_retimed'] is True
    check(d);print('PASS current M61 exact inputs/evidence; four legacy default SV files byte-identical, isolated core retimed',flush=True)


def main():
    previous=baseline();out=ROOT/'reports/m61';out.mkdir(parents=True,exist_ok=True)
    sources={};artifacts={}
    def bind(rel,h):
        dst=sources if rel.startswith(('src/','scripts/','tests/')) else artifacts
        if rel in dst:assert dst[rel]==h,('contradictory input binding',rel)
        dst[rel]=h
    def manifest(rel):
        d=json.loads((ROOT/rel).read_text());assert d['status']=='PASS',rel;check(d)
        artifacts[rel]=sha(ROOT/rel)
        for group in ('source_sha256','artifact_sha256'):
            for p,h in d.get(group,{}).items():bind(p,h)
        if 'oracle_binary' in d:bind(d['oracle_binary'],d['oracle_binary_sha256'])
        return d
    direct=manifest('build/m61/legacy/results.json')
    recoveryFixture=manifest('build/m58/recovery/results.json')
    assert recoveryFixture['commands']==1384 and recoveryFixture['scenarios']==404
    runs={};area={};timing={};isolation={};hardware=hostCsr=commands=directHardware=recoveryHardware=recoveryRequests=negatives=0
    for model,(top,_,_) in MODELS.items():
        rtl=manifest(f'build/m61/rtl/{model}/results.json')
        gs=manifest(f'build/m61/gsim/{model}/results.json')
        corpus=manifest(f'build/m61/corpus/{model}/results.json')
        assert corpus['encodings']==(229 if model=='integer' else 330)
        assert corpus['scenarios']==(1832 if model=='integer' else 2640)
        run=manifest(f'build/m61/runs/{model}/results.json')
        assert not run['trace_replay'] and run['checked_registers_per_command']==32
        # Compilation records must match the persisted actual generated sources.
        for name,h in run['gsim_input_sha256'].items():
            if name=='clang++-19':assert sha(ROOT/'tools/llvm-program/usr/bin/clang++-19')==h
            elif name=='m61_isolated_driver.cc':assert sha(ROOT/'tests/m61_isolated_driver.cc')==h
            else:
                p=OUT/'gsim'/model/(name+'.gz');assert hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()==h,name
        fields={k:int(v) for k,v in re.findall(r'(commands|hardware|host_csr|reads|requests|responses)=(\d+)',run['summary'])}
        assert fields['commands']==corpus['commands'] and fields['requests']==fields['responses']==0
        commands+=fields['commands'];hardware+=fields['hardware'];hostCsr+=fields['host_csr'];negatives+=len(run['negative_controls'])
        direct=(OUT/'runs'/model/'directed.log').read_text().strip()
        assert direct.startswith('PASS isolated directed') and 'monitor_burst=1' in direct and 'prefix_retry=2' in direct
        df={k:int(v) for k,v in re.findall(r'(hardware|requests|responses)=(\d+)',direct)}
        assert df['requests']==df['responses']==18;directHardware+=df['hardware']
        recovery=(OUT/'runs'/model/'recovery.log').read_text().strip()
        assert recovery.startswith('PASS isolated public DUT')
        mf={k:int(v) for k,v in re.findall(r'(commands|hardware|host_csr|requests|responses)=(\d+)',recovery)}
        assert mf['commands']==mf['hardware']==1384 and mf['requests']==mf['responses']==6232 and mf['host_csr']==0
        recoveryHardware+=mf['hardware'];recoveryRequests+=mf['requests']
        runs[model]=dict(matrix=run['summary'],directed=direct,recovery=recovery)
        syn=manifest(f'build/m61/synth/{model}/results.json')
        counts=syn['mapped_cells'];area[model]=dict(logic_luts=sum(n for c,n in counts.items() if re.fullmatch(r'LUT[1-6]',c)),
            ff=sum(n for c,n in counts.items() if c.startswith(('FDRE','FDSE','FDCE','FDPE'))),dsp=counts.get('DSP48E2',0),
            ram={c:n for c,n in counts.items() if c.startswith('RAM')})
        iso=manifest(f'build/m61/isolation/{model}/results.json')
        assert iso['combinational_io_paths']==0 and iso['raw_payload_capture'];assert len(iso['negative_controls'])==3
        packed=OUT/'synth'/model/'mapped.json.gz';rawHash=hashlib.sha256(gzip.decompress(packed.read_bytes())).hexdigest()
        assert rawHash==iso['mapped_uncompressed_sha256'];negatives+=len(iso['negative_controls'])
        isolation[model]={k:iso[k] for k in ('input_signal_bits','output_signal_bits','payload_input_bits','combinational_io_paths','raw_payload_capture')}
        tm=manifest(f'build/m61/timing/{model}/results.json');assert tm['passes_300MHz'] is None and tm['budget_ns']<=1000/300
        budget=json.loads((OUT/'timing'/model/'budget.json').read_text())
        assert budget['input_sha256'][f'/tmp/spinor-m61/{model}/mapped.json']==rawHash
        timing[model]={k:tm[k] for k in ('budget_ns','covered_endpoints','excluded_dsp_endpoints')}
    assert hardware==41648 and hostCsr==5280 and commands==46928 and negatives==24
    assert recoveryHardware==5536 and recoveryRequests==24928
    # Exact legacy reference corpus inputs remain pinned; no expectation is read
    # from the isolated DUT's output. Expand their bindings into the new receipt.
    for sew in (8,16,32,64):manifest(f'build/m60/corpus/sew{sew}/results.json')
    for p in [*sorted((ROOT/'src/main/scala').rglob('*.scala')),*sorted((ROOT/'scripts').glob('*m61*.py')),
              ROOT/'scripts/check_docs.py',ROOT/'tests/m61_isolated_driver.cc',ROOT/'tests/test_m61_isolated.py',
              ROOT/'README.md',ROOT/'CURRENT.md',ROOT/'.gitattributes',ROOT/'docs/README.md',ROOT/'docs/integration.md',
              ROOT/'docs/cpu-spinor-contract.md',ROOT/'docs/tilelink.md',ROOT/'docs/monitor-soc.md',ROOT/'docs/architecture.md',ROOT/'docs/validation.md',ROOT/'docs/m61-isolation.md']:
        bind(str(p.relative_to(ROOT)),sha(p))
    for p in [ROOT/'archive/m60/baseline.json',*sorted((ROOT/'archive/m60/source').rglob('*')),ROOT/'reports/m60/receipt.json',
              ROOT/'archive/docs-m60/baseline.json',ROOT/'tools/llvm-program/usr/bin/clang++-19']:
        if p.is_file():artifacts[str(p.relative_to(ROOT))]=sha(p)
    text=f'''# M61：可选寄存隔离顶层

新增 `SpinorIsolated` 与 `GenerateIsolated`，旧提交边界保留。
49个原有Scala文件精确不变，5个增加默认关闭的可选分级；四种旧直接配置重新生成的完整SV与已验收M56逐字节相同。
本轮优化SoC接入时序，不增加ISA指令，也不在VPU内加入CPU退休器或MMU。

## 协议与边界

命令、context、grant token、FCSR输入先采样，宽token比较在采样之后进行。
RAM A/D及monitor A/D分别经过非直通寄存切片；ready仅由本地寄存状态产生，未使用透明flow/pipe队列。
预览包只保存一份，供preview和done共用；授权前核心completion.ready保持0。
monitor A另加一拍控制值校验，保持64位非法高位拒绝与32位未使用高半部忽略，
再用等价的小位宽控制替代原64位<=2比较链；实际snapshot/clear和非法写均经真实端口验证。
隔离顶层另启用LSU几何译码寄存和短地址分段；整数隔离配置在RAM窗口选择与操作数扩展之间再加一拍，
切断实际映射中暴露的长链。四种旧直接配置不启用这些新增分级；不能把旧核心测试自动当作分级后的证据。

CPU在不可撤销队头完成本地资格检查后offer；收到preview后，通过完整80位token的grant授权。
grant握手后在本地检查身份、执行核心完成握手、采样发布后状态，再返回可反压done。
CPU在done.fire处理标量结果/异常/flags，授权至done期间不得丢弃owner或插入恢复/年轻指令。
这是一项明确的新协议，不能将grant视为旧reply的同拍退休握手。

授权前算术stop可取消，memory stop保留总线与所有者；grant胜过同拍stop，此后不能撤销授权。
身份错误封锁，不消费核心完成。数据/状态观察也经过寄存；同频隔离不提供CDC。

## 功能验证

四配置：标准host、Deep host、标准standalone、integer-deep。
从冻结M60独立参考语料取SEW8/16/32/64、LMUL1、分离布局、起点0/2场景。
前三配置覆盖330编码，整数配置229编码。不是完整M60全部几何重跑，也不把旧核心证据冒作新隔离顶层测试。

矩阵在真实隔离顶层GSim公共端口执行 **{hardware:,}条VPU命令**，另有{hostCsr:,}次测试宿主自身FCSR访问。
每条比较完整32向量寄存器和已实现状态，阻塞preview与done，检查未授权普通指令不提前发布，
检查完整身份和授权后owner保持。done的发布后状态快照也与参考CSR值比较，反压期间必须保持。
host FCSR观察与执行舍入快照分开：首次offer前的context访问也必须正确观察宿主frm/fflags，
done.state.fflags是CPU合并本条flags之前的值。共{commands:,}个测试命令记录；不是DUT轨迹重放。

每配置另有真实RTL数值/访存定向测试：offer同拍stop、preview后stop、grant同拍stop、
被反压A上的load/store停止、响应排空、原基址前缀重试、denied错误、monitor多请求反压，
及已知答案FP舍入快照/flags（整数版为FP拒绝）。合计{directHardware}条定向VPU命令、
72次实际RAM A/D请求/响应。停止的待返回load不写入响应数据并保留vstart=0；
已发store仍提交1元素前缀、vstart=1，再从原基址恢复。没有将两者混为同一个前缀策略。
12次运行比较器/错误授权控制与12次结构检查负控制均检出。

针对新增LSU分级，每配置再经真实端口执行冻结M58的404场景、1,384条命令，
使用未修改Spike参考与显式VL/vstart规则，比较完整32向量寄存器、已实现CSR及8KiB RAM。
覆盖strided NF5/6/7的EEW16/64字段故障、FOF NF2/8全EEW的首元素异常和后续截断、恢复后的算术。
合计{recoveryHardware:,}条恢复测试命令、{recoveryRequests:,}次实际RAM请求/响应。
本轮正向测试共{hardware+directHardware+recoveryHardware:,}条隔离顶层接收的VPU命令，包含预期取消/非法场景；测试宿主FCSR操作另计。

## 组合隔离与时序

对四份完整xcup映射网表检查全部非clock/reset输入到全部输出的组合锥，均为0条组合通路。
另检查所有外部payload没有在输入采样寄存器前进入组合逻辑，避免仅切断ready却留下宽token比较。
wire旁路、LUT旁路、采样前payload逻辑的三种故意破坏均被检查器检出。
这是对当前生成网表的结构检查，不是CDC、IO约束或器件时序认证。

四配置资源与固定100ps/link条件预算：

| 配置 | 逻辑LUT | FF | DSP | 条件预算ns |
|---|---:|---:|---:|---:|
'''
    for model in MODELS:
        r=area[model];text+=f"| {model} | {r['logic_luts']} | {r['ff']} | {r['dsp']} | {timing[model]['budget_ns']:.3f} |\n"
    text+='''
使用原M25固定家族权重与显式连线假设，排除DSP影响端点、主IO、真实时钟和器件布线，
未按ZU15EG-2校准；不含hold/恢复移除/存储写入签核。实际300MHz仍未知。
寄存隔离消除了当前网表中的跨接口组合贯穿，不能保证系统布局拥塞、IO延迟或时钟质量不影响Fmax。
保留版本化RAM和FP单元，不把向量寄存器文件改成大规模触发器。

完整协议、生成命令和CPU迁移要求见[隔离指南](../../docs/m61-isolation.md)。
```bash
python3 scripts/verify_m61.py
python3 scripts/verify_m61.py --check-only
```
完整重跑需要已保留的固定工具与M60参考产物；使用/tmp的构建中间文件可再生成，
当前验收绑定的SV/FIR/GSim源码和网表以gzip保存在build/m61，check-only不依赖/tmp仍存在。
旧功能/文档receipt不改写。当前仍不声明完整V/RVA23/Zvkt、实际CPU/Linux集成或器件300MHz通过。
'''
    (out/'evaluation.md').write_text(text);sources['reports/m61/evaluation.md']=sha(out/'evaluation.md')
    result=dict(status='PASS',milestone=61,hardware_changed=True,legacy_default_rtl_changed=False,isolated_core_retimed=True,baseline=previous,
                matrix_hardware_commands=hardware,test_host_fcsr_operations=hostCsr,matrix_records=commands,directed_hardware_commands=directHardware,
                recovery_hardware_commands=recoveryHardware,recovery_ram_requests=recoveryRequests,total_hardware_commands=hardware+directHardware+recoveryHardware,
                runs=runs,resources=area,isolation=isolation,conditional_timing=timing,negative_controls=negatives,
                passes_300MHz=None,passes_500MHz=None,full_v=False,full_rva23=False,zvkt_claimed=False,
                source_sha256=sources,artifact_sha256=artifacts)
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');check(result)
    print('PASS M61',hardware,'matrix hardware commands;',directHardware,'directed commands; all registered IO cones checked',flush=True)


if __name__=='__main__':main()
