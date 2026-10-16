#!/usr/bin/env python3
"""Byte/cycle reference for checked normal-RAM vector operations, no board MHz."""
import argparse,csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--milestone',choices=['m10','m11','m12','m13','m14','m15','m16'],default='m10');args=p.parse_args()
OUT=ROOT/'reports'/args.milestone;OUT.mkdir(parents=True,exist_ok=True)
d=json.loads((ROOT/'build/test/vector-memory-rtl-results.json').read_text())
assert d['status']=='PASS'
assert d['rtl_or_netlist_sha256']==hashlib.sha256((ROOT/'build/rtl/LishiVpuMemory.sv').read_bytes()).hexdigest()
metrics={m['case']:m for m in d['metrics']};rows=[]
for case in d['benchmark_cases']:
 m=metrics[case['case']];count=case['vl'];byteCount=count*case['eew']//8
 assert m['requests']==count
 rows.append({**case,**m,'bytes':byteCount,'cycles_per_element':m['cycles']/count,'bytes_per_cycle':byteCount/m['cycles'],
  'hypothetical_MBps_at_300MHz':byteCount/m['cycles']*300})
assert len(rows)==24
with (OUT/'memory-performance.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
lines=['# M10 访存周期参考','',
 '每项为 LMUL8、满长度、无掩码连续地址 load/store，检查数据和请求地址。计时含命令接受、逐元素上下文取数/写回、vstart 更新、协议等待和完成接受；不含配置、初始化及最后的数据读取。此部分没有人为的完成背压。','',
 '模拟内存使用单事务注册返回，A 通道每三个周期有一个周期不给 ready。service_wait 为模型接受 A 后额外等待的周期，D 最早在 A 后第 2 个周期被接受，所以它不是“零延迟 DDR”。尚无 cache、译址、PMP、真实 DDR 控制器和板级时钟。','',
 '| EEW | 操作 | 元素数 | 额外等待周期 | 总周期 | 周期/元素 | 有效字节/周期 | 假设300 MHz的MB/s |',
 '|---:|:---|---:|---:|---:|---:|---:|---:|']
for r in rows:
 lines.append(f"| {r['eew']} | {'store' if r['write'] else 'load'} | {r['vl']} | {r['service_wait']} | {r['cycles']} | {r['cycles_per_element']:.2f} | {r['bytes_per_cycle']:.4f} | {r['hypothetical_MBps_at_300MHz']:.2f} |")
lines += ['', '这是一版正确性优先的单事务、逐元素实现。每个已完成元素都通过核心 CSR 通道更新 vstart，便于证明停止/重启一致性，吞吐明显受固定控制开销限制。',
 '后续可以在保留精确元素提交边界的前提下，增加源/目的块缓存、专用 vstart 更新接口以及多 source 请求窗口。不得据此报告真实 DDR 带宽；300 MHz 换算不表示 M10 已通过该频率。']
(OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')
print('Wrote',len(rows),'checked memory measurements')
for r in rows:
 if r['service_wait']==0:print(r['eew'],'store' if r['write'] else 'load',r['cycles'],'cycles',round(r['bytes_per_cycle'],4),'B/cycle')

if args.milestone=='m11':
 baseline=list(csv.DictReader((ROOT/'archive/m10/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)
 comparison=['# M11 对照 M10','', '| EEW | 操作 | 等待 | M10周期 | M11周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write'])
  assert new['cycles']<int(old['cycles'])
  comparison.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 comparison+=['','同一个有背压、注册返回的单事务内存模型；不是实际 DDR 带宽，也不证明 300 MHz。专用 vstart 提交替代 CSR 指令；load 数据写回仍先于进度提交，停止必须等已写回元素的进度提交完成。']
 (OUT/'memory-performance.md').write_text('\n'.join(comparison)+'\n')

if args.milestone=='m12':
 baseline=list(csv.DictReader((ROOT/'archive/m11/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)==24
 lines=['# M12 对照 M11','','| EEW | 操作 | 额外等待 | M11周期 | M12周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write']) and new['cycles']<=int(old['cycles'])
  assert d['context_reads'][str(new['case'])]==18
  lines.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 lines+=['','128 字节、LMUL8、无掩码满长度，命令至完成；不含配置和初始化。单事务内存模型含周期性 A 背压，D 最早在 A 后两个周期接受；额外等待为 0/4/16。不是实际 DDR 或频率验证。', '每项均检查上下文读次数为 18：2 次掩码快照读，16 次数据块读。EEW8/16/32 原先分别为 130/66/34，EEW64 原本为 18。load 逐元素写回和进度提交仍保留。']
 (OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')

if args.milestone=='m13':
 baseline=list(csv.DictReader((ROOT/'archive/m12/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)==24
 lines=['# M13 对照 M12','','| EEW | 操作 | 额外等待 | M12周期 | M13周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write']) and new['cycles']<=int(old['cycles'])
  assert d['context_reads'][str(new['case'])]==18
  lines.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 lines+=['','128 字节、LMUL8、无掩码满长度，命令至完成；不含配置和初始化。单事务内存模型含周期性 A 背压，D 最早在 A 后两个周期接受；额外等待为 0/4/16。不是实际 DDR 或频率验证。', '每项均检查上下文读次数为 18：2 次掩码快照读，16 次数据块读。EEW8/16/32 原先分别为 130/66/34，EEW64 原本为 18。load 逐元素写回和进度提交仍保留。']
 (OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')

if args.milestone=='m14':
 baseline=list(csv.DictReader((ROOT/'archive/m13/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)==24
 lines=['# M14 对照 M13','','| EEW | 操作 | 额外等待 | M13周期 | M14周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write']) and new['cycles']<=int(old['cycles'])
  assert d['context_reads'][str(new['case'])]==18
  lines.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 lines+=['','128 字节、LMUL8、无掩码满长度，命令至完成；不含配置和初始化。单事务内存模型含周期性 A 背压，D 最早在 A 后两个周期接受；额外等待为 0/4/16。不是实际 DDR 或频率验证。', '每项均检查上下文读次数为 18：2 次掩码快照读，16 次数据块读。EEW8/16/32 原先分别为 130/66/34，EEW64 原本为 18。load 逐元素写回和进度提交仍保留。']
 (OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')

if args.milestone=='m15':
 baseline=list(csv.DictReader((ROOT/'archive/m14/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)==24
 lines=['# M15 对照 M14','','| EEW | 操作 | 额外等待 | M14周期 | M15周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write']) and new['cycles']<=int(old['cycles'])
  assert d['context_reads'][str(new['case'])]==18
  lines.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 lines+=['','128 字节、LMUL8、无掩码满长度，命令至完成；不含配置和初始化。单事务内存模型含周期性 A 背压，D 最早在 A 后两个周期接受；额外等待为 0/4/16。不是实际 DDR 或频率验证。', '每项均检查上下文读次数为 18：2 次掩码快照读，16 次数据块读。EEW8/16/32 原先分别为 130/66/34，EEW64 原本为 18。load 逐元素写回和进度提交仍保留。']
 (OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')

if args.milestone=='m16':
 baseline=list(csv.DictReader((ROOT/'archive/m15/reports/memory-performance.csv').open()))
 assert len(baseline)==len(rows)==24
 lines=['# M16 对照 M15','','| EEW | 操作 | 额外等待 | M15周期 | M16周期 | 减少 |','|---:|:---|---:|---:|---:|---:|']
 for old,new in zip(baseline,rows):
  for key in ['case','service_wait','eew','vl']:assert int(old[key])==new[key]
  assert old['write']==str(new['write']) and new['cycles']<=int(old['cycles'])
  assert d['context_reads'][str(new['case'])]==18
  lines.append(f"| {new['eew']} | {'store' if new['write'] else 'load'} | {new['service_wait']} | {old['cycles']} | {new['cycles']} | {(1-new['cycles']/int(old['cycles']))*100:.1f}% |")
 lines+=['','128 字节、LMUL8、无掩码满长度，命令至完成；不含配置和初始化。单事务内存模型含周期性 A 背压，D 最早在 A 后两个周期接受；额外等待为 0/4/16。不是实际 DDR 或频率验证。', '每项均检查上下文读次数为 18：2 次掩码快照读，16 次数据块读。EEW8/16/32 原先分别为 130/66/34，EEW64 原本为 18。load 逐元素写回和进度提交仍保留。']
 (OUT/'memory-performance.md').write_text('\n'.join(lines)+'\n')
