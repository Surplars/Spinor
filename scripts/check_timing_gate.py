#!/usr/bin/env python3
"""Fail delivery if either top exceeds the fixed cloud reference budget.

This gate is conditional on 100 ps per net segment, with the unchanged family
weights and assumptions. It never sets physical frequency sign-off fields.
"""
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--baseline',default='build/timing-budget/m25-baseline/budget.json')
p.add_argument('--frozen',default='archive/m25/reports/receipt.json')
p.add_argument('--spinor',default='build/timing-budget/m26-spinor/budget.json')
p.add_argument('--compute',default='build/timing-budget/m26-compute/budget.json')
p.add_argument('--output',default='build/timing-budget/m26-gate/results.json')
a=p.parse_args();out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.unlink(missing_ok=True)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
base=json.loads((ROOT/a.baseline).read_text());inputs={a.baseline:sha(ROOT/a.baseline)}
frozen=json.loads((ROOT/a.frozen).read_text())['conditional_budgets']['m25-spinor']
inputs[a.frozen]=sha(ROOT/a.frozen)
assert base['weights_ps']==frozen['weights_ps'] and base['provenance']==frozen['provenance']
assert base['scenarios']==frozen['scenarios'],'frozen M25 graph budget changed'
results={}
for top,path in [('SpinorVpu',a.spinor),('LishiVpuMemory',a.compute)]:
 d=json.loads((ROOT/path).read_text());inputs[path]=sha(ROOT/path)
 assert d['top']==top and d['scope']==base['scope'],top
 assert d['weights_ps']==base['weights_ps'] and d['provenance']==base['provenance'],top
 assert d['passes_300MHz'] is None and d['passes_500MHz'] is None
 assert not d['placed'] and not d['routed'] and not d['speed_grade_calibrated']
 for file,h in d['input_sha256'].items():assert sha(ROOT/file)==h,file;inputs[file]=h
 scenario,=[s for s in d['scenarios'] if s['assumed_link_ps']==100]
 ns=scenario['worst']['budget_ns'];assert ns<=1000/300,(top,ns,'exceeds fixed 300 MHz conditional budget')
 results[top]=dict(budget_ns=ns,budget_residual_ns=1000/300-ns,
                   covered_endpoints=scenario['covered_endpoint_count'],
                   excluded_DSP_endpoints=scenario['DSP_tainted_endpoints_excluded'],
                   path=scenario['worst'])
inputs[str(Path(__file__).resolve().relative_to(ROOT))]=sha(Path(__file__).resolve())
result=dict(status='PASS',scope='CONDITIONAL_REFERENCE_GATE_NOT_DEVICE_STA',
            target_period_ns=1000/300,assumed_link_ps=100,results=results,
            passes_300MHz=None,passes_500MHz=None,input_sha256=inputs)
out.write_text(json.dumps(result,indent=2)+'\n')
print('PASS fixed cloud reference gate:',', '.join(f'{k} {v["budget_ns"]:.3f} ns' for k,v in results.items()))
