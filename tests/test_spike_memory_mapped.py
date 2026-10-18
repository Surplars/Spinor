#!/usr/bin/env python3
"""Bounded LSU gate-level cross-check; retain full RF/RAM/fault checks."""
import json,sys
from pathlib import Path
import test_spike_memory as driver
from test_spike_memory import ROOT,sha
original=driver.events_for
WANTED={'vle32_v','vse32_v','vlse32_v','vsuxei32_v','vle32ff_v','vlm_v','vs1r_v'}
def bounded(entries,compact=False):
    events=original(entries,True);blocks=[]
    for e in events:
        if e['kind']=='M':blocks.append([])
        blocks[-1].append(e)
    result=[]
    for block in blocks:
        memory=[e for e in block if e['kind']=='I' and e['instruction']&127 in [7,39]]
        plain=any(e['name'] in WANTED and e.get('nf')==1 for e in memory)
        fault=any(e['name'] in ['vle32_v-fault','vse32_v-fault','vle32ff_v-fault'] and e.get('nf')==1 and e.get('fault_index')==1 for e in memory)
        restart=any(e['name']=='vle32_v-restart' for e in memory)
        if plain or fault or restart:result+=block
    for i,e in enumerate(e for e in result if e['kind']=='I'):e['id']=i
    assert len([e for e in result if e['kind']=='I'])==26
    return result
if __name__=='__main__':
    driver.OUT=ROOT/'build/spike-memory-bounded';driver.events_for=bounded
    sys.argv=[sys.argv[0],'--compact','--mapped'];driver.main()
    p=driver.OUT/'SpinorStandard-compact-mapped/results.json';d=json.loads(p.read_text());d['bounded']=True;d['segment_forms']=7
    d['source_sha256'][str(Path(__file__).resolve().relative_to(ROOT))]=sha(Path(__file__).resolve())
    p.write_text(json.dumps(d,indent=2)+'\n')
