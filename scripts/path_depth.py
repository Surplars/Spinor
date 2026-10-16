#!/usr/bin/env python3
"""Conservative cell-hop graph on mapped logic; NOT delay/Fmax estimation.

Every input of a combinational cell is conservatively connected to every output.
Thus CARRY4 counted as a cell hop, not a LUT delay. No interconnect/placement,
clock uncertainty, setup/hold, speed grade or DSP/BRAM timing is modelled.
"""
import argparse
from collections import Counter,defaultdict,deque
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def analyze(top):
    folder=ROOT/'build/synth'/top
    module=json.loads((folder/'mapped.json').read_text())['modules'][top]
    original=module['cells']
    dsps={n:c for n,c in original.items() if c['type']=='DSP48E2'}
    for c in dsps.values():
        if any(int(v,2)!=0 for k,v in c['parameters'].items() if k.endswith('REG')):
            raise ValueError('DSP48E2 internal registers require explicit graph boundaries')
    memories={n:c for n,c in original.items() if c['type'].startswith('RAM')}
    # Distributed RAM: writes are clocked state boundaries, but each read
    # address still has a combinational path to its corresponding output.
    # Treat a read as one explicitly uncharacterized cell hop, NOT a LUT delay.
    cells={n:c for n,c in original.items() if n not in memories}
    for name,mem in memories.items():
        if mem['type'] not in ['RAM32M16','RAM64M8','RAM32M','RAM64M']:
            raise ValueError(f'Unsupported RAM read topology: {mem["type"]}')
        for port,d in mem['port_directions'].items():
            if d=='output':
                address='ADDR'+port[2:]
                cells[name+'.READ_'+port]={'type':mem['type']+'_READ',
                    'port_directions':{address:'input',port:'output'},
                    'connections':{address:mem['connections'][address],port:mem['connections'][port]}}
    flops={n:c for n,c in cells.items() if c['type'].startswith(('FDRE','FDSE','FDCE','FDPE'))}
    allowed=lambda t:t.startswith(('LUT','MUXF','CARRY','INV','BUF')) or t.endswith('_READ') or t=='DSP48E2'
    ignored={'$scopeinfo'}
    unknown={c['type'] for c in cells.values() if c['type'] not in ignored and not allowed(c['type']) and not c['type'].startswith(('FDRE','FDSE','FDCE','FDPE'))}
    if unknown:raise ValueError(f'Unsupported cell types in graph: {unknown}')
    comb={n:c for n,c in cells.items() if allowed(c['type'])}
    names={}
    for name,net in module['netnames'].items():
        for i,b in enumerate(net['bits']):
            if not isinstance(b,int):continue
            if b not in names or ('$' in names[b] and '$' not in name):names[b]=f'{name}[{i}]'
    driver={}
    users=defaultdict(list)
    for n,c in comb.items():
        for p,direction in c['port_directions'].items():
            for b in c['connections'][p]:
                if isinstance(b,int):
                    if direction=='output':driver[b]=n
                    elif direction=='input':users[b].append(n)
    deps={n:set(driver[b] for p,d in c['port_directions'].items() if d=='input'
                    for b in c['connections'][p] if b in driver) for n,c in comb.items()}
    nexts=defaultdict(list)
    for n,ds in deps.items():
        for d in ds:nexts[d].append(n)
    count={n:len(ds) for n,ds in deps.items()}
    todo=deque(n for n,k in count.items() if not k)
    order=[]
    while todo:
        n=todo.popleft();order.append(n)
        for x in nexts[n]:
            count[x]-=1
            if count[x]==0:todo.append(x)
    if len(order)!=len(comb):raise ValueError('combinational cycle or unsupported feedback in graph')
    # Only paths starting at FF.Q; primary input timing is reported separately.
    paths={}
    for n,c in flops.items():
        for b in c['connections']['Q']:paths[b]=(0,n,[])
    for n,c in memories.items():
        for p,d in c['port_directions'].items():
            if d=='output':
                for b in c['connections'][p]:paths[b]=(0,n+'.stored-data',[])
    for n in order:
        c=comb[n]
        candidates=[paths[b] for p,d in c['port_directions'].items() if d=='input'
                    for b in c['connections'][p] if b in paths]
        if not candidates:continue
        depth,start,chain=max(candidates,key=lambda x:x[0])
        path=(depth+1,start,chain+[(n,c['type'])])
        for p,d in c['port_directions'].items():
            if d=='output':
                for b in c['connections'][p]:paths[b]=path
    endpoints=[]
    fanout=Counter()
    for n,c in original.items():
        for p,d in c['port_directions'].items():
            if d=='input':
                for b in c['connections'][p]:
                    if isinstance(b,int) and p not in ['C','CLK']:fanout[b]+=1
    for n,c in flops.items():
        for port in ['D','CE','R','S','CLR','PRE']:
            for bit in c['connections'].get(port,[]):
                if bit in paths:
                    depth,start,chain=paths[bit]
                    endpoints.append(dict(hops=depth,start=start,end=f'{n}.{port}',
                                          end_net=names.get(bit,str(bit)),
                                          kind='data' if port=='D' else 'control',
                                          cell_types=dict(Counter(t for _,t in chain)),
                                          chain=[{'cell':n,'type':t} for n,t in chain]))
    endpoints.sort(key=lambda x:x['hops'],reverse=True)
    result=dict(top=top,metric='conservative mapped combinational cell hops between registers',
                NOT_FMAX=True,timing_ns=None,passes_300MHz=None,passes_500MHz=None,
                ram_read_hops_have_no_characterized_delay=True,
                unregistered_DSP48E2_counted_as_one_uncalibrated_hop=len(dsps),
                memory_cells=dict(Counter(c['type'] for c in memories.values())),
                longest_data=next((x for x in endpoints if x['kind']=='data'),None),
                longest_control=next((x for x in endpoints if x['kind']=='control'),None),
                top_paths=endpoints[:10],fanout=[dict(net=names.get(b,str(b)),loads=n) for b,n in fanout.most_common(10)])
    (folder/'paths.json').write_text(json.dumps(result,indent=2)+'\n')
    print(top,'data',(result['longest_data'] or {}).get('hops'),
          'control',(result['longest_control'] or {}).get('hops'),
          'fanout',fanout.most_common(1)[0][1] if fanout else 0)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('tops',nargs='*',default=['IntegerLaneBaseline','IntegerLaneSplit','IntegerLaneSplit16','VectorPrototype'])
    for top in p.parse_args().tops:analyze(top)

if __name__=='__main__':main()
