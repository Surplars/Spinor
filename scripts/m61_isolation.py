#!/usr/bin/env python3
"""Trace every combinational input/output cone in a flattened mapped netlist."""
from collections import defaultdict,deque
import argparse
import copy
import gzip
import json
from m61_build import ROOT,OUT,TMP,MODELS,sha


def paths(module):
    primary={b:(name,i) for name,p in module['ports'].items() if p['direction']=='input' and name not in ('clock','reset') for i,b in enumerate(p['bits']) if isinstance(b,int)}
    cells={n:c for n,c in module['cells'].items() if not c['type'].startswith(('FDRE','FDSE','FDCE','FDPE')) and c['type']!='$scopeinfo'}
    def bits(c,d):return [b for p,kind in c['port_directions'].items() if kind==d for b in c['connections'][p] if isinstance(b,int)]
    drivers={b:n for n,c in cells.items() for b in bits(c,'output')}
    deps={n:{drivers[b] for b in bits(c,'input') if b in drivers} for n,c in cells.items()}
    successors=defaultdict(list)
    for n,ds in deps.items():
        for prev in ds:successors[prev].append(n)
    q=deque(n for n,ds in deps.items() if not ds);degree={n:len(ds) for n,ds in deps.items()};reachable=dict(primary);visited=0
    while q:
        n=q.popleft();visited+=1;c=cells[n]
        origin=next((reachable[b] for b in bits(c,'input') if b in reachable),None)
        if origin:
            for b in bits(c,'output'):reachable[b]=origin
        for after in successors[n]:
            degree[after]-=1
            if not degree[after]:q.append(after)
    assert visited==len(cells),'combinational cycle or unresolved graph'
    bad=[]
    for name,p in module['ports'].items():
        if p['direction']=='output':
            for i,b in enumerate(p['bits']):
                if b in reachable:bad.append(dict(input=reachable[b],output=[name,i]))
    return bad,len(primary),sum(len(p['bits']) for p in module['ports'].values() if p['direction']=='output')


def payload_leaks(module,payload):
    return [name for name,c in module['cells'].items()
            if not c['type'].startswith(('FDRE','FDSE','FDCE','FDPE')) and c['type']!='$scopeinfo'
            and any(b in payload for p,d in c['port_directions'].items() if d=='input' for b in c['connections'][p])]


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=MODELS,default='host');a=p.parse_args()
    top=MODELS[a.model][0];folder=TMP/a.model;source=folder/'mapped.json';module=json.loads(source.read_text())['modules'][top]
    bad,inputs,outputs=paths(module);assert not bad,bad[:8]
    # Payload bits must terminate directly at input capture registers. Handshake
    # controls may qualify CE/state; a wide CPU token comparator may not.
    payload={b for name,p in module['ports'].items() if p['direction']=='input' and ('_bits' in name or name.startswith('io_fcsrHost_')) for b in p['bits'] if isinstance(b,int)}
    leaks=payload_leaks(module,payload)
    assert not leaks,('payload logic before input registers',leaks[:8])
    # Prove that both an aliased wire and a LUT-mediated leak are found.
    controls={}
    origin=next(b for name,p in module['ports'].items() if p['direction']=='input' and name not in ('clock','reset') for b in p['bits'] if isinstance(b,int))
    for mode in ('wire-bypass','lut-bypass'):
        broken=copy.deepcopy(module);target=max(b for n in module['netnames'].values() for b in n['bits'] if isinstance(b,int))+1
        if mode=='wire-bypass':target=origin
        else:broken['cells']['__negative_lut']=dict(type='LUT1',port_directions={'I0':'input','O':'output'},connections={'I0':[origin],'O':[target]})
        broken['ports']['__negative_output']=dict(direction='output',bits=[target])
        assert paths(broken)[0],mode;controls[mode]='REJECTED'
    broken=copy.deepcopy(module)
    end=max(b for n in module['netnames'].values() for b in n['bits'] if isinstance(b,int))+1
    broken['cells']['__negative_payload_lut']=dict(type='LUT1',port_directions={'I0':'input','O':'output'},connections={'I0':[next(iter(payload))],'O':[end]})
    broken['cells']['__negative_capture']=dict(type='FDRE',port_directions={'D':'input','Q':'output'},connections={'D':[end],'Q':[end+1]})
    broken['ports']['__negative_output']=dict(direction='output',bits=[end+1])
    assert not paths(broken)[0] and payload_leaks(broken,payload)
    controls['payload-logic-before-register']='REJECTED'
    out=OUT/'isolation'/a.model;out.mkdir(parents=True,exist_ok=True)
    source_manifest=OUT/'synth'/a.model/'results.json'
    result=dict(status='PASS',scope='FLATTENED_MAPPED_ALL_COMBINATIONAL_INPUT_TO_OUTPUT_CONES',model=a.model,top=top,
                input_signal_bits=inputs,output_signal_bits=outputs,combinational_io_paths=0,negative_controls=controls,
                raw_payload_capture=True,payload_input_bits=len(payload),
                clock_reset_excluded=True,not_cdc_proof=True,not_device_timing=True,
                source_sha256={'scripts/m61_isolation.py':sha(ROOT/'scripts/m61_isolation.py')},
                artifact_sha256={str(source_manifest.relative_to(ROOT)):sha(source_manifest)},mapped_uncompressed_sha256=sha(source))
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS isolated mapped IO',a.model,inputs,outputs,'signal bits; no combinational paths',flush=True)


if __name__=='__main__':main()
