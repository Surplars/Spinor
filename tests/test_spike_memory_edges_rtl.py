#!/usr/bin/env python3
"""SV-driven counterpart of the exact bounded direct-GSIM edge corpus."""
import json,sys
from pathlib import Path
import test_spike_memory as driver
from spike_memory_edges import bounded_events_for
from test_spike_memory import ROOT,sha
if __name__=='__main__':
    driver.OUT=ROOT/'build/spike-memory-edges-rtl';driver.events_for=lambda entries,compact:bounded_events_for(entries)
    sys.argv=[sys.argv[0],'--compact'];driver.main()
    p=driver.OUT/'SpinorStandard-compact-rtl/results.json';d=json.loads(p.read_text());d['bounded']=True;d['segment_forms']=None;d['scope']='Exact M52 bounded edge corpus; independent SV handshakes against the same Spike oracle'
    d['source_sha256'].update({str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/spike_memory_edges.py']})
    p.write_text(json.dumps(d,indent=2)+'\n')
