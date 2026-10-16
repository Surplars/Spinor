#!/usr/bin/env python3
"""Prevent unknown DSPs, primary inputs and combinational cycles becoming timing passes."""
import hashlib,importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('budget',ROOT/'scripts/cloud_budget.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
def cell(typ,ins,outs):return dict(type=typ,parameters={},port_directions={**{p:'input' for p in ins},**{p:'output' for p in outs}},connections={**ins,**outs})
with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
 d=Path(tmp);net=d/'mapped.json';out=d/'out'
 cells={'src':cell('FDRE',{'D':[8]},{'Q':[2]}),'l1':cell('LUT1',{'I0':[2]},{'O':[3]}),'l2':cell('LUT1',{'I0':[3]},{'O':[4]}),'dst':cell('FDRE',{'D':[4]},{'Q':[8]}),'dsp':cell('DSP48E2',{'A':[2]},{'P':[5]}),'unknown_dst':cell('FDRE',{'D':[5]},{'Q':[6]}),'pi':cell('LUT1',{'I0':[90]},{'O':[91]}),'pi_dst':cell('FDRE',{'D':[91]},{'Q':[92]})}
 def write():net.write_text(json.dumps({'modules':{'fixture':{'cells':cells,'netnames':{}}}}))
 write();b.analyze(net,'fixture',out);r=json.loads((out/'budget.json').read_text())
 assert r['uncharacterized_DSP_cells']==1 and r['passes_300MHz'] is None
 assert all(s['DSP_tainted_endpoints_excluded']==1 and s['covered_endpoint_count']==2 for s in r['scenarios'])
 assert [round(s['worst']['budget_ns'],3) for s in r['scenarios']]==[.627,.777,1.077]
 cells['l1']['connections']['I0']=[4];write()
 try:b.analyze(net,'fixture',out)
 except AssertionError as e:assert 'combinational cycle' in str(e)
 else:raise AssertionError('cycle accepted')
 assert not (out/'budget.json').exists(),'stale success survived failed analysis'
print('PASS conditional budget: hand-computed path, unknown DSP exclusion, PI exclusion, cycle rejection')

(ROOT/'build/test/cloud-budget-results.json').write_text(json.dumps(dict(status='PASS',checks=['hand-computed delays','DSP exclusion','PI exclusion','cycle rejection','stale output removal'],source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['scripts/cloud_budget.py','tests/test_cloud_budget.py']}),indent=2)+'\n')
