#!/usr/bin/env python3
"""Check the timing cut in a mapped graph, independently of RTL mux equations."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'build/synth/RamVectorFp/mapped.json').read_text())['modules']['RamVectorFp']
drivers={}
for name,cell in m['cells'].items():
    for port,direction in cell['port_directions'].items():
        if direction=='output':
            for bit in cell['connections'][port]:drivers[bit]=(name,cell)
unit_state=set(m['netnames']['unit.state']['bits'])
stage_address=set(m['netnames']['stagedAddress']['bits'])
assert unit_state and len(stage_address)==5
ram=[c for n,c in m['cells'].items() if n.startswith('rf.storage_ext.') and c['type']=='RAM64M8']
assert len(ram)==32,'This audit expects the pinned xcup automatic RAM64M8 mapping'
groups={'write_address':['ADDRH'],'write_data':['DIA','DIB','DIC','DID','DIE','DIF','DIG'],'write_enable':['WE']}
result={'status':'PASS','scope':'Mapped register-to-RAM combinational fanin; not device delay','groups':{}}
for group,ports in groups.items():
    stack=[b for c in ram for p in ports for b in c['connections'][p]]
    seen=set();stops=set()
    while stack:
        bit=stack.pop()
        if bit in seen or bit not in drivers:continue
        seen.add(bit);_,c=drivers[bit]
        if c['type'].startswith('FD'):
            stops.add(bit);continue
        for port,direction in c['port_directions'].items():
            if direction=='input':stack.extend(c['connections'][port])
    direct=sorted(unit_state&stops)
    result['groups'][group]={'FP_state_register_bits_in_direct_cone':direct,
        'stage_address_bits_in_cone':len(stage_address&stops),'source_FF_bits':len(stops)}
    if direct:result['status']='FAIL'
out=ROOT/'build/test/write-cone.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if result['status']!='PASS':raise SystemExit('FP state still directly reaches a RAM write port')
