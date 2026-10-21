#!/usr/bin/env python3
"""Apply the unchanged family budget to the new mapped top; never device STA."""
import argparse
import json
from cloud_budget_m56 import analyze
from m61_build import ROOT,OUT,TMP,MODELS,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=MODELS,default='host');a=p.parse_args()
    out=OUT/'timing'/a.model;path=TMP/a.model/'mapped.json';top=MODELS[a.model][0]
    analyze(path,top,out)
    d=json.loads((out/'budget.json').read_text())
    frozen=json.loads((ROOT/'build/timing-budget/m25-baseline/budget.json').read_text())
    assert d['weights_ps']==frozen['weights_ps'] and d['provenance']==frozen['provenance']
    scenario,=[s for s in d['scenarios'] if s['assumed_link_ps']==100]
    assert scenario['worst']['budget_ns']<=1000/300,(a.model,scenario['worst'])
    assert d['passes_300MHz'] is None and not d['placed'] and not d['routed'] and not d['speed_grade_calibrated']
    result=dict(status='PASS',model=a.model,scope='CONDITIONAL_REFERENCE_NOT_DEVICE_STA',budget_ns=scenario['worst']['budget_ns'],
                passes_300MHz=None,covered_endpoints=scenario['covered_endpoint_count'],excluded_dsp_endpoints=scenario['DSP_tainted_endpoints_excluded'],
                source_sha256={'scripts/m61_timing.py':sha(ROOT/'scripts/m61_timing.py'),'scripts/cloud_budget_m56.py':sha(ROOT/'scripts/cloud_budget_m56.py')},
                artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [out/'budget.json',out/'budget.md',OUT/'synth'/a.model/'results.json',ROOT/'build/timing-budget/m25-baseline/budget.json']})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS fixed conditional timing',a.model,result['budget_ns'],flush=True)


if __name__=='__main__':main()
