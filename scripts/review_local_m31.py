#!/usr/bin/env python3
"""Verify an M31 report ZIP and record only the timing scope it establishes."""
import argparse,hashlib,json,re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('--output',type=Path,default=ROOT/'reports/local-m31');a=p.parse_args()
with ZipFile(a.zip) as z:
 assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
 data={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
read=lambda n:data[n].decode('utf-8-sig')
base=json.loads((ROOT/'reports/m31/receipt.json').read_text());inputs=json.loads(read('run-inputs.json'));outputs=json.loads(read('output-sha256.json'))
assert (inputs['top'],inputs['target'] if 'target' in inputs else inputs['part'],inputs['mode'],inputs['milestone'])==('SpinorVpu','xczu15eg-ffvb1156-2-i','All','M31')
verified={}
for name,content in data.items():
 if name=='output-sha256.json':continue
 assert sha(content)==outputs[name],name;verified[name]=sha(content)
source={}
for top in ['SpinorVpu','RamVectorFp']:
 name='rtl/'+top+'.sv';expected=base['artifact_sha256']['build/rtl/'+top+'.sv'];assert inputs['source_hashes'][name]==expected;source[name]=expected
for label,file in [('extensions','integer-extensions.sv'),('integration','spinor-integration.sv')]:
 name='tb/'+file;expected=base['windows_handoff']['replays'][label]['testbench_sha256'];assert inputs['source_hashes'][name]==expected;source[name]=expected
for name in ['run.ps1','run_vivado.tcl','RUN_ME_FIRST.txt']:
 expected=base['source_sha256']['scripts/windows-current/'+name];assert inputs['source_hashes'][name]==expected;source[name]=expected

def timing(name):
 text=read(name);lines=text.splitlines();i=next(i for i,l in enumerate(lines) if 'WNS(ns)' in l)
 values=lines[i+2].split();assert len(values)==12,(name,values)
 names=['WNS_ns','TNS_ns','setup_failing','setup_total','WHS_ns','THS_ns','hold_failing','hold_total','WPWS_ns','TPWS_ns','pulse_failing','pulse_total']
 d={key:(int(value) if 'failing' in key or 'total' in key else float(value)) for key,value in zip(names,values,strict=True)}
 assert '| Design State      : Routed' in text if name=='timing_routed.rpt' else True
 return d
routed=timing('timing_routed.rpt');placed=timing('timing_placed.rpt')
assert re.search(r'\| Speed File\s*:\s*-2\s+PRODUCTION',read('timing_routed.rpt'))
assert re.search(r'^vpu_clk\s+3\.333\s+',read('clocks.rpt'),re.M)
assert (routed['WNS_ns'],routed['WHS_ns'],routed['WPWS_ns'])==(0.392,0.009,1.124)
assert all(routed[k]==0 for k in ['TNS_ns','setup_failing','THS_ns','hold_failing','TPWS_ns','pulse_failing'])
assert routed['setup_total']==routed['hold_total']==25582
checks={k:int(v) for k,v in re.findall(r'checking (\w+) \((\d+)\)',read('timing_routed.rpt'))}
assert checks['no_clock']==checks['unconstrained_internal_endpoints']==0
assert (checks['no_input_delay'],checks['no_output_delay'])==(613,608)
route={}
for key,label in [('routable','routable nets'),('fully_routed','fully routed nets'),('routing_errors','nets with routing errors')]:
 route[key]=int(re.search(r'# of '+label+r'\.+\s*:\s*(\d+)',read('route_status.rpt'))[1])
assert route=={'routable':21784,'fully_routed':21784,'routing_errors':0}
def row(label):
 return int(re.search(r'^\|\s*'+re.escape(label)+r'\s*\|\s*(\d+)\s*\|',read('utilization_routed.rpt'),re.M)[1])
resources={key:row(label) for key,label in [('LUT_total','CLB LUTs'),('LUT_logic','LUT as Logic'),('LUT_memory_including_SRL','LUT as Memory'),('LUTRAM','LUT as Distributed RAM'),('SRL','LUT as Shift Register'),('FF','CLB Registers'),('RAMB36','RAMB36/FIFO*'),('DSP48E2','DSPs'),('BUFGCE','BUFGCE')]}
assert resources['LUT_total']==14173 and resources['FF']==11605 and resources['RAMB36']==2 and resources['DSP48E2']==7 and resources['BUFGCE']==0
summ=dict(line.split('=',1) for line in read('run-summary.txt').splitlines() if '=' in line)
assert float(summ['setup_slack_ns'])==routed['WNS_ns'] and float(summ['hold_slack_ns'])==routed['WHS_ns'] and int(summ['DSP48E2_count'])==resources['DSP48E2']
log=read('vivado.log');warnings=Counter(re.findall(r'^WARNING: \[([^\]]+)\]',log,re.M))
assert not re.search(r'^(ERROR:|CRITICAL WARNING:)',log,re.M)
assert warnings['Timing 38-242']>0 and warnings['Route 35-197']>0
sim={}
for name,project in [('extensions','spinor_extensions'),('integration','spinor_integration')]:
 content=read(f'simulation/{name}/project/{project}.sim/sim_1/behav/xsim/simulate.log')
 assert not re.search(r'^(ERROR:|Fatal:|FATAL:)',content,re.M)
 sim[name]=[line for line in content.splitlines() if line.startswith('PASS ')]
 assert '$finish called at time' in content
assert sim['extensions']==['PASS integer-extensions commands=884 cycles=129796']
assert sim['integration']==['PASS monitored-mmio reads=7504 accepted=313 completed=304 faults=50 stops=6','PASS vector-memory commands=119 requests=783 responses=783 cycles=18774']
def first_path(file):
 text=read(file)
 return dict(source=re.search(r'Source:\s*(.+)',text)[1].strip(),destination=re.search(r'Destination:\s*(.+)',text)[1].strip(),
  data_delay_ns=float(re.search(r'Data Path Delay:\s*([\d.]+)ns',text)[1]),logic_levels=int(re.search(r'Logic Levels:\s*(\d+)',text)[1]))
setup=first_path('setup_paths.rpt');hold=first_path('hold_paths.rpt')
assert 'RAMB36E2' in read('setup_paths.rpt') and setup['data_delay_ns']==2.876 and setup['logic_levels']==6
coverage={name:int(rows) for name,rows in re.findall(r'(\S+\.txt) timing_rows=(\d+)',read('dsp-export-coverage.txt'))}
assert len(coverage)==7 and all(coverage.values())
cloud=base['conditional_reference_gate']['results'];conditional={k:v['budget_ns'] for k,v in cloud.items()}
result=dict(status='PASS',scope='M31_USER_VIVADO_ROUTED_OOC_DEFINED_INTERNAL_CONSTRAINTS_ONLY',
 upload=dict(filename=a.zip.name,bytes=a.zip.stat().st_size,sha256=sha(a.zip.read_bytes()),verified_report_entries=len(verified),original_output_hash_entries=len(outputs),omitted_output_entries=len(outputs)-len(verified)),
 tested_hardware_commit='2deb1e742e1fdff7bd837a967991c1625d9a51ef',source_bindings=source,
 tool='Vivado 2025.1 build 6140274',part='xczu15eg-ffvb1156-2-i',speed_grade='-2',design_state='Routed',
 requested_period_ns=float(inputs['period_ns'] if 'period_ns' in inputs else inputs['implementation_period_ns']),effective_period_ns=3.333,
 placed=placed,routed=routed,route=route,resources=resources,check_timing=checks,warnings=dict(warnings),
 simulation=sim,critical_setup=setup,critical_hold=hold,DSP_reported_nonempty_export_rows=coverage,
 cloud_conditional_budget_ns=conditional,passes_300MHz_current_OOC_constraints=True,passes_300MHz_actual_SoC_clock_and_IO=None,passes_500MHz=None,
 real_clock_source_constrained=False,host_IO_delays_constrained=False,post_route_SDF_simulation=False,
 DCP_EDIF_and_DSP_arc_tables_received=False,report_sha256=verified,
 input_sha256={'scripts/review_local_m31.py':sha(Path(__file__).read_bytes()),'reports/m31/receipt.json':sha((ROOT/'reports/m31/receipt.json').read_bytes())})
a.output.mkdir(parents=True,exist_ok=True);(a.output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
evaluation=f'''# M31 本地 Vivado / XSim 核查

M31 的 SpinorVpu 已在 Vivado 2025.1、xczu15eg-ffvb1156-2-i 上完成独立 OOC 布局布线，**当前约束覆盖的内部路径满足约 300MHz**。该结果来自用户本地报告；HD.CLK_SRC 和宿主 IO 延迟尚未指定，不是完整 SoC/板级时钟与接口签核。

| 项目 | 结果 |
|---|---:|
| 时钟周期 | 3.333ns（请求3.333333ns，Vivado按1ps精度取整） |
| Setup WNS / TNS | +0.392ns / 0 |
| Hold WHS / THS | +0.009ns / 0 |
| Pulse width slack | +1.124ns |
| Setup / hold失败端点 | 0 / 0，各检查25,582端点 |
| 需要布线 / 已完全布线网络 | 21,784 / 21,784 |
| 布线错误 | 0 |
| 无时钟寄存器 / 未约束内部端点 | 0 / 0 |
| 未设input / output delay的端口 | 613 / 608 |

布局阶段 WNS +0.502ns、WHS +0.020ns；最终报告为布线后的 +0.392/+0.009ns。两种余量均正，但hold仅9ps，真实时钟树/布局改变后必须重新检查。BUFG使用量为0，工具发出Timing38-242与Route35-197，明确指出缺少HD.CLK_SRC会影响clock delay/skew估计；多项Route35-198来自未指定外部partition pin位置。不能用此结果外推最高频率，也不能声称完整SoC已通过300MHz。

## 功能仿真

- XSim整数扩展自检：884条命令，129,796周期，PASS。
- XSim公开SpinorVpu集成：119组访存，783次请求/响应，18,774周期，PASS。
- 并发monitor参考：7,504次读，313次接受、304次完成，50次故障事件、6次停止事件，PASS；这些是TB主动注入并检查的场景计数，不能当成非预期运行故障。剩余接受/完成差来自取消场景。
- 这里是行为RTL自检与静态时序报告，没有post-route SDF仿真。不是完整ISA合规测试。

## 实际资源

| 项目 | Vivado布线后 |
|---|---:|
| CLB LUT总数 | 14,173（器件4.15%） |
| 逻辑LUT | 14,077 |
| LUTRAM / SRL | 42 / 54（合计96个memory LUT） |
| FF | 11,605（1.70%） |
| RAMB36 | 2 |
| DSP48E2 | 7 |

层次报告显示两个RAMB36属于版本化向量寄存器堆；整数乘法器1个DSP、FP lane6个DSP。monitor为1,071逻辑LUT/1,309FF。云端Yosys估计为18,529逻辑LUT/12,308FF/9DSP，并把寄存器堆映射为LUTRAM；Vivado选择BRAM，映射拓扑不同。不能把资源差异当成功能变化，也不能按一个倍率把云端估计校准为器件STA。

## 关键路径与后续

最差setup：`{setup['source']}` → `{setup['destination']}`。数据路径2.876ns，6级LUT，其中逻辑1.359ns、连线1.517ns。当前优先观察BRAM读出后的选择/移位和写回数据复用，而非仅调整DSP流水。

最差hold：`{hold['source']}` → `{hold['destination']}`，数据0.133ns；对应整数结果队列写地址。先确定实际时钟源/BUFG和SoC接口时序，再复验此9ps余量，避免对缺少真实时钟模型的OOC结果直接作hold修补。

Vivado还提示BRAM同址读写碰撞；当前VersionedRegisterFile合同禁止客户端同时读写同一物理行。行为自检通过不等于完成BRAM综合网表碰撞模式验证，后续应保持该合同并作定向验证。timescale警告来自DUT未声明timescale而TB声明1ns/1ps；本次行为自检结束并输出PASS，不能把该警告解读为SDF已执行。

7个DSP导出文件的摘要共{sum(coverage.values())}行，均非空。报告小包没有原始arc表、DCP和EDIF，不能在此核查每条arc完整性或恢复设计；已有报告足以核查本次已约束内部STA结果，无需为读取这些报告重新运行Vivado。

后续继续补齐VPU指令，同时以此作为固定本地OOC比较基线；接入Orbital/SoC时加入实际时钟和接口约束、重跑实现。当前仍是部分RVV、单指令容量。

## 证据

上传报告包SHA-256：`{result['upload']['sha256']}`，{result['upload']['bytes']}字节。CRC及32个提取报告/日志的SHA均与原output-sha256.json一致；原manifest列77个文件，另外45个输出未收到，未作完整性声明。输入的两份RTL、两份打包TB、runner/Tcl与M31冻结源码/证据散列一致；尚未复开用户DCP。原始用户日志保留于本会话build/local-m31-reports，不额外发布其中的宿主信息。receipt记录逐项散列、约束范围及解析结果。

复核命令：`python3 scripts/review_local_m31.py <上传的_reports.zip>`。旧M31云端与修复报告保留历史状态；本报告补充实际本地结果，不重写原始交付证据。
'''
(a.output/'evaluation.md').write_text(evaluation);print('PASS M31 local routed OOC: setup +0.392ns, hold +0.009ns; exact source/TB bindings and 32 report hashes verified')
