#!/usr/bin/env python3
"""Record the pinned model's treatment of a normatively reserved encoding."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_spike_memory import reference,BASE
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    model=json.loads((ROOT/'build/spike-memory-model/results.json').read_text());assert model['status']=='PASS'
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for rel,h in model['sha256'].items():assert sha(ROOT/rel)==h,rel
    folder=ROOT/'build/m52-reference-policy-probe';folder.mkdir(exist_ok=True)
    events=[];cases=[];raw=0x04000027|1<<25|8<<20|1<<15|8<<7
    for avl in [0,3]:
        events.append(dict(kind='M',data=bytes((i*13+7)&255 for i in range(8192)).hex()))
        events.extend(dict(kind='R',register=r,data=0) for r in range(32))
        for name,word,scalar in [('vsetvli',16<<20|1<<15|7<<12|3<<7|0x57,0),('reserved-store',raw,BASE+1024)]:
            ident=sum(e['kind']=='I' for e in events)
            events.append(dict(kind='I',id=ident,name=name,instruction=word,scalar=scalar,scalar2=0,avl=avl))
            if name=='reserved-store':cases.append(dict(id=ident,avl=avl,instruction=word))
    states=reference(events,folder,model)
    for case in cases:
        s=states[case['id']];assert not s['illegal'] and not s['cause'];case.update(model_cause=s['cause'],model_illegal=s['illegal'],vl=s['vl'])
    spec=ROOT/'docs/references/m44-indexed-v1.0.txt';assert 'than one EEW for a single instruction.' in spec.read_text()
    sources=[Path(__file__).resolve(),ROOT/'tests/test_spike_memory.py',ROOT/'tests/spike_memory_adapter.cc',spec]
    artifacts=[folder/'spike-input.txt',folder/'spike-output.txt',folder/'spike-stderr.log',*folder.glob('gold/*.hex'),ROOT/'build/spike-memory-model/results.json']
    result=dict(status='PASS',scope='RESERVED_MODEL_CHOICE_PROBE_NOT_LEGAL_INSTRUCTION_COVERAGE',cases=cases,decision='Exclude this reserved family from strict Spike comparison; independently require Spinor rejection and unchanged state',
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS pinned Spike reserved-policy probe',len(cases),'cases')
if __name__=='__main__':main()
