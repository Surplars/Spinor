#!/usr/bin/env python3
"""Summarize checked cycles; hypothetical clock scaling is explicitly separate."""
import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m8';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
data=json.loads((ROOT/'build/performance/results.json').read_text())
assert data['benchmark_source_sha256']==sha(ROOT/'tests/performance.py')
assert data['testbench_sha256']==sha(ROOT/'build/performance/performance-tb.sv')
for name,path in [('M7','archive/m7/rtl/RamVectorFp.sv'),('M8','build/rtl/RamVectorFp.sv')]:
 assert data['results'][name]['rtl_sha256']==sha(ROOT/path)
 assert len(data['results'][name]['cases'])==220
rows=[]
for old,new in zip(data['results']['M7']['cases'],data['results']['M8']['cases'],strict=True):
 assert old['id']==new['id']
 if new['operation'] in ['vmul','vdivu','vfadd'] or new['operation']=='vadd' and new['vl']==1:assert old['cycles']==new['cycles']
 rows.append({**new,'M7_cycles_per_instruction':old['cycles_per_instruction'],'speedup_M7_over_M8':old['cycles']/new['cycles']})
with (OUT/'performance.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# 砺矢 M8 性能测试','',
 '本报告测量可验证的指令执行周期，不测 FPGA 最高频率。M7 和 M8 使用相同的独立测试程序，各 220 组，每组连续执行 8 条依赖指令，并检查最终寄存器值。计时从第一条指令发射前到最后一条完成接受，包含指令启动、候选目的复制、取数、执行、写回和提交；配置、上下文初始化和最终结果读取不计入。宿主无额外停顿或完成背压。','',
 '基础矩阵覆盖 SEW8/16/32/64、LMUL1/2/4/8、VL=1/满长度、无掩码/交替掩码/全关闭掩码、vadd.vv/vx；另测完整长度的 vxor、vmul、vdivu 和 FP32/64 vfadd。每组重复次数固定，不能把该测试当作 CPU/访存或应用性能。','',
 '## 满向量 LMUL=8 的依赖 vadd','',
 '| SEW | 形式 | 元素数 | M7 周期/指令 | M8 周期/指令 | 加速比 | M8 活跃元素/周期 | 假设300 MHz时 M元素/秒 |',
 '|---:|:---|---:|---:|---:|---:|---:|---:|']
for w in [8,16,32,64]:
 for form in ['vv','vx']:
  r=next(r for r in rows if r['operation']=='vadd' and r['sew']==w and r['form']==form and r['lmul']==8 and r['mask']=='all' and r['vl']==1024//w)
  lines.append(f"| {w} | {form} | {r['vl']} | {r['M7_cycles_per_instruction']:.0f} | {r['cycles_per_instruction']:.0f} | {r['speedup_M7_over_M8']:.2f}× | {r['active_elements_per_cycle']:.4f} | {r['hypothetical_Melements_per_second_at_300MHz']:.2f} |")
lines += ['', '## 固定开销与边际元素成本', '',
 '对无掩码 INT8 vadd，用 VL=1 与满长度两点计算 `C(VL)=边际周期×VL+固定项`。固定项包含流水排空等成本，是端到端拟合值，不是单独测得的启动阶段耗时。', '',
 '| LMUL | vv 边际周期/元素 | vx 边际周期/元素 | 固定项/周期 |', '|---:|---:|---:|---:|']
for lm in [1,2,4,8]:
 values=[]
 for form in ['vv','vx']:
  selected=[r for r in rows if r['operation']=='vadd' and r['sew']==8 and r['lmul']==lm and r['mask']=='all' and r['form']==form]
  first=next(r for r in selected if r['vl']==1);last=max(selected,key=lambda r:r['vl'])
  marginal=(last['cycles_per_instruction']-first['cycles_per_instruction'])/(last['vl']-1)
  values.append((marginal,first['cycles_per_instruction']-marginal))
 assert values[0][1]==values[1][1]
 lines.append(f'| {lm} | {values[0][0]:.0f} | {values[1][0]:.0f} | {values[0][1]:.0f} |')
lines += ['', '## 怎么读这些指标','',
 '- 周期/指令：端到端向量指令成本，短向量受启动和复制开销影响较大。',
 '- 周期/活跃元素：包含掩码扫描和固定开销。全关闭掩码没有活跃元素，因此该项为空，不使用 VL 冒充有效计算量。',
 '- 活跃元素/周期：端到端吞吐；300 MHz 一列只将它乘以假设时钟，不证明 M8 能以该频率运行。',
 '- 单元素 VL=1 的加法周期没有改善；乘法、除法和 FP 加法的已测周期与 M7 一致。',
 '- 发射端当前 .vv 每 6 周期、.vx 每 4 周期发射一个基础整数元素；缓存/解包尚未让执行 lane 达到每周期一个元素。',
 '- 这轮没有 LSU、外部内存流量或多指令重叠，不能报告 DDR 带宽、缓存性能、应用加速比或完整 RVV 峰值。','',
 '完整数据在 [performance.csv](performance.csv)，原始周期及输入 SHA 在 performance-results.json。',
 'M8 器件频率尚未经过 Vivado 实现确认，未生成新的 SDF；不继承 M5 的 WNS。']
(OUT/'performance.md').write_text('\n'.join(lines)+'\n')
(ROOT/'reports/m8/performance-results.json').write_text(json.dumps(data,indent=2)+'\n')
print('Wrote',len(rows),'rows:',OUT/'performance.csv')
