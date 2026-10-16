#!/usr/bin/env python3
"""Freeze a standalone OoO-window experiment as an add-on to immutable M17."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/ooo-window';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
baseline=read('reports/m17/receipt.json')
for group in ['source_sha256','artifact_sha256']:
 for p,h in baseline[group].items():assert sha(ROOT/p)==h,p
assert sha(ROOT/'lishi-vpu-m17.zip')=='6dfa23549faa6739f403bf64225ad145361cc86f81c97d32deccf93f14eb3920'
tests=[];files=set()
for label in ['rtl','mapped']:
 p=f'build/issue-window/results-{label}.json';d=read(p)
 assert d['status']=='PASS' and d['cycles']==10000
 for name,h in d['sha256'].items():assert sha(ROOT/name)==h;files.add(name)
 files.add(p);files.add('build/issue-window/'+label+'-simulation.log');files.add('build/issue-window/'+label+'-compile.log');tests.append(d)
assert tests[0]['stats']==tests[1]['stats']
assert tests[0]['stats']['max_occupancy']==8 and tests[0]['stats']['max_executing']==4
budget=read('build/timing-budget/issue-window/budget.json')
for p,h in budget['input_sha256'].items():assert sha(ROOT/p)==h;files.add(p)
assert budget['passes_300MHz'] is None and budget['passes_500MHz'] is None
for name in ['budget.json','budget.md']:files.add('build/timing-budget/issue-window/'+name)
for name in ['summary.json','paths.json','mapped.v','mapped.json','synth.log','synth.ys']:
 files.add('build/synth/VectorIssueWindow/'+name)
files.update(['src/main/scala/vpu/VectorIssueWindow.scala','tests/test_issue_window.py','scripts/report_issue_window.py','docs/ooo-window.md'])
for p in (OUT/'first-candidate').glob('*'):files.add(str(p.relative_to(ROOT)))
receipt=dict(status='STANDALONE_WINDOW_RTL_AND_MAPPED_PASS_NOT_INTEGRATED',base='M17',
 base_zip_sha256=sha(ROOT/'lishi-vpu-m17.zip'),tests=tests,resources=read('build/synth/VectorIssueWindow/summary.json'),conditional_budget=budget,
 limits=['NO_REAL_VPU_EXECUTION_INTEGRATION','NO_DUAL_ISSUE','ISSUE_SELECTION_II_2','NO_RENAMING_OR_FORWARDING','NO_CPU_OR_LSU_INTEGRATION','NO_DEVICE_STA'],
 sha256={p:sha(ROOT/p) for p in sorted(files)})
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');files.add('reports/ooo-window/receipt.json')
target=ROOT/'lishi-vpu-ooo-window-v1.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(files):z.write(ROOT/p,'lishi-vpu/'+p)
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None
 for p,h in receipt['sha256'].items():assert hashlib.sha256(z.read('lishi-vpu/'+p)).hexdigest()==h
target.with_suffix('.zip.sha256').write_text(sha(target)+'  '+target.name+'\n')
print(receipt['status']);print(target,target.stat().st_size,sha(target))
