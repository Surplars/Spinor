#!/usr/bin/env python3
"""Freeze monitor ABI v1, wrapper regression and optional integration add-on."""
import hashlib,json,re,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/monitor-v1';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
baseline=read('reports/m17/receipt.json')
for group in ['source_sha256','artifact_sha256']:
 for p,h in baseline[group].items():assert sha(ROOT/p)==h,p
assert sha(ROOT/'lishi-vpu-m17.zip')=='6dfa23549faa6739f403bf64225ad145361cc86f81c97d32deccf93f14eb3920'
files=set();tests=[]
for label in ['VpuMonitor-rtl','VpuMonitorTiny-rtl','VpuMonitor-mapped','VpuMonitor-base-rtl']:
 p='build/monitor/test/'+label+'-results.json';d=read(p);assert d['status']=='PASS' and d['cycles']==2600
 for n,h in d['sha256'].items():assert sha(ROOT/n)==h,n;files.add(n)
 files.update([p,'build/monitor/test/'+label+'.log','build/monitor/test/'+label+'-compile.log']);tests.append(d)
assert tests[1]['wraps']>0
for k in ['reads','writes','denied','held_cycles','snapshots','clears']:assert tests[0][k]==tests[2][k]
integration=[]
for label,n in [('rtl',254),('smoke',94),('mapped',94)]:
 stem='build/monitor/integration/vector-memory-'+label;d=read(stem+'-results.json')
 rtl='build/synth/LishiVpuMonitored/mapped.v' if label=='mapped' else 'build/rtl/LishiVpuMonitored.sv'
 assert d['status']=='PASS' and d['memory_cases']==n
 assert d['rtl_or_netlist_sha256']==sha(ROOT/rtl)
 assert d['testbench_sha256']==sha(ROOT/(stem+'-tb.sv'))
 log=(ROOT/(stem+'.log')).read_text()
 assert 'PASS monitored-mmio' in log
 assert re.search(r'PASS monitored-mmio reads=\d+ accepted=\d+ completed=\d+ faults=[1-9]\d* stops=[1-9]\d*',log)
 for suffix in ['-results.json','-tb.sv','.log','.compile.log']:files.add(stem+suffix)
 if label!='mapped':
  assert d['assertions_enabled']
  for module in ['VectorMemoryEngine','RamVectorFpMemory']:files.add(stem+'-'+module+'-assert.sv')
 integration.append(d)
assert integration[0]['metrics']==baseline['memory_tests'][0]['metrics']
assert integration[1]['metrics']==integration[2]['metrics']
software=read('build/monitor/software/results.json');assert software['status']=='PASS'
for n,h in software['sha256'].items():assert sha(ROOT/n)==h,n;files.add(n)
files.update(['build/monitor/software/results.json','build/monitor/software/decoded.json'])
pat=r'(?ms)^module (\w+)\b.*?^endmodule'
old={m.group(1):m.group(0) for m in re.finditer(pat,(ROOT/'build/rtl/LishiVpuMemory.sv').read_text())}
new={m.group(1):m.group(0) for m in re.finditer(pat,(ROOT/'build/rtl/LishiVpuMonitored.sv').read_text())}
shared={k:hashlib.sha256(v.encode()).hexdigest() for k,v in old.items() if k!='LishiVpuMemory'}
assert shared and all(new.get(k)==old[k] for k in shared)
summaries={}
for top in ['VpuMonitor','LishiVpuMonitored']:
 summaries[top]=read('build/synth/'+top+'/summary.json')
 for name in ['summary.json','mapped.json','mapped.v','paths.json','synth.log','synth.ys']:files.add('build/synth/'+top+'/'+name)
budget=read('build/timing-budget/monitored/budget.json')
for p,h in budget['input_sha256'].items():assert sha(ROOT/p)==h,p;files.add(p)
assert budget['passes_300MHz'] is None and budget['passes_500MHz'] is None
for name in ['budget.json','budget.md']:files.add('build/timing-budget/monitored/'+name)
for folder in ['build/monitor/rtl','software/monitor']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file():files.add(str(p.relative_to(ROOT)))
files.update(['tests/test_monitor.py','tests/test_monitored_memory.py','tests/test_monitor_client.py','scripts/verify_monitor.py','scripts/report_monitor.py','docs/monitor-soc.md','build/rtl/LishiVpuMonitored.sv'])
cells=summaries['LishiVpuMonitored']['mapped_cells']
lut=sum(v for k,v in cells.items() if k.startswith('LUT'));ff=sum(v for k,v in cells.items() if k.startswith('FD'))
assert (cells['DSP48E2'],cells['RAM64M8'],cells['RAM32M16'])==(9,32,6)
numbers='/'.join(f"{x['worst']['budget_ns']:.3f}" for x in budget['scenarios'])
evaluation=f'''# Monitor ABI v1 云端检查

新增可选顶层LishiVpuMonitored和独立监控TL从设备；M17默认顶层和原有源码/证据保持原散列。不是完整RVV，也未集成Valence或乱序窗口。

4组monitor测试各2600周期：生产RTL、生产映射网表、8位计数器回绕模型、0xa0010000真实地址解码。覆盖原子快照/清零、反压、子字访问、32位写的未选中字节、坏请求、只读保护、错误和序号。Tiny发生{tests[1]['wraps']}次计数回绕。映射与RTL统计一致。

集成顶层在持续monitor轮询下通过254组完整访存、94组RTL与94组映射访存检查，额外验证算术flush取消和13项计数的实际接口事件。访存逐用例周期与M17完全相同；报告总周期多出的部分是末尾增加的取消/快照检查。数值和LSU子模块中{len(shared)}份定义与M17逐字相同；作为内部子模块的LishiVpuMemory外壳由CIRCT裁剪常量端口，因此不声称该外壳RTL逐字相同。

监控顶层全图LUT {lut}（M17为14530）、FF {ff}（M17为10143）、DSP9不变，RAM64M8×32及RAM32M16×6不变。独立monitor的计数/原子快照当前使用FF，不是RAM优化计数器；因此保持可选。数据通路没有额外向量数据副本。

全图条件预算{numbers}ns，对应每段假设连线50/100/200ps；未布局、无-2校准，排除DSP相关端点。不是STA或300/500MHz通过证据，本轮没有Vivado结果。

Linux用户态UIO工具经gcc -Wall -Wextra -Werror编译，文件夹具验证容量/宽字段/错误解码和3种拒绝情形。未在真实内核UIO、ARM MMIO或硬件上运行。通用UIO提供监控访问，不提供VPU作业提交、CPU上下文管理或Linux RVV支持。

ABI及接入边界见docs/monitor-soc.md。应用附加包到M17目录后，执行python3 scripts/verify_monitor.py可复现。对外接口仍为现有不可撤销CPU命令/完成和物理普通RAM LSU；实际SoC尚需总线/时钟接入、CPU适配、保护/翻译/一致性、精确异常、上下文管理及剩余ISA。
'''
(OUT/'evaluation.md').write_text(evaluation);files.add('reports/monitor-v1/evaluation.md')
receipt=dict(status='OPTIONAL_MONITORED_WRAPPER_RTL_AND_MAPPED_PASS_NOT_FULL_RVV',base_zip_sha256=sha(ROOT/'lishi-vpu-m17.zip'),
 monitor_tests=tests,integration_tests=integration,software_test=software,resources=summaries,conditional_budget=budget,unchanged_datapath_module_sha256=shared,
 Vivado_executed=False,passes_300MHz=None,passes_500MHz=None,actual_Linux_UIO_tested=False,
 sha256={p:sha(ROOT/p) for p in sorted(files)})
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');files.add('reports/monitor-v1/receipt.json')
target=ROOT/'lishi-vpu-monitor-v1.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):z.write(ROOT/p,'lishi-vpu/'+p)
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None
 for p,h in receipt['sha256'].items():assert hashlib.sha256(z.read('lishi-vpu/'+p)).hexdigest()==h,p
target.with_suffix('.zip.sha256').write_text(sha(target)+'  '+target.name+'\n')
print(receipt['status']);print(target,target.stat().st_size,sha(target))
