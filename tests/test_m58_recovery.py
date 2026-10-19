#!/usr/bin/env python3
"""Strided segment field faults and FOF -> arithmetic/CSR -> retry sequences."""
import argparse
import csv
import gzip
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from m58_stream import ROOT,sha,run_fixture
from m57_isa_catalog import catalog
import test_spike_memory as memory

OUT=ROOT/'build/m58/recovery'


def events():
    entries={e['name']:e for e in catalog()}
    rows=[];ident=0;scenarios=[]
    def ins(raw,scalar=0,scalar2=0,avl=0,**meta):
        nonlocal ident
        rows.append(dict(kind='I',id=ident,instruction=raw,scalar=scalar,scalar2=scalar2&memory.M64,avl=avl,**meta));ident+=1
        return ident-1
    def case(name,s,nf,element,field,stride_mode=1,vm=1,mask=(1<<128)-1,start=0):
        e=entries[name];width=1<<s;mode=e['match']>>26&3
        step=width*nf*(2*stride_mode if mode==2 else 1)
        rows.extend([dict(kind='M',data=bytes((i*13+7)&255 for i in range(8192)).hex()),dict(kind='F',address=0,length=0)])
        for r in range(32):
            value=sum(((r*17+13*k+7)&255)<<(8*k) for k in range(16))
            rows.append(dict(kind='R',register=r,data=mask if r==0 else value))
        # m1; request two segments even at SEW64. Both are within VLMAX.
        ins((s<<3)<<20|1<<15|7<<12|3<<7|0x57,avl=2)
        if start:ins(8<<20|1<<15|1<<12|3<<7|0x73,scalar=start)
        raw=e['match']|(((nf-1)<<29|vm<<25|(2<<20 if mode==2 else 0)|1<<15|8<<7)&~e['mask'])
        fault=memory.BASE+2048+element*step+field*width
        rows.append(dict(kind='F',address=fault,length=width))
        at_fault=ins(raw,memory.BASE+2048,step)
        # Observe FOF's actual VL through both an arithmetic consumer and a
        # vector CSR read, including the first-element trapping case.
        arithmetic=csr=None
        if 'ff_' in name:
            a=entries['vadd_vv'];arithmetic=ins(a['match']|((1<<25|16<<20|24<<15|8<<7)&~a['mask']))
            csr=ins(0xc20<<20|2<<12|3<<7|0x73)
        rows.append(dict(kind='F',address=0,length=0))
        retry=ins(raw,memory.BASE+2048,step)
        scenarios.append(dict(name=name,sew=8<<s,nf=nf,fault_element=element,fault_field=field,stride_mode=stride_mode,
                              vm=vm,mask=mask,initial_vstart=start,fault_id=at_fault,retry_id=retry,arithmetic_id=arithmetic,csr_id=csr))
    for s in (1,3):
        for nf in (5,6,7):
            for prefix in ('vlse','vsse'):
                name=f'{prefix}{8<<s}_v'
                for element in (0,1):
                    for field in range(nf):
                        for direction in (-1,1):case(name,s,nf,element,field,direction)
                # All inactive, masked-off faulting element and first active
                # element after restart are distinct cases.
                for vm,mask,start in [(0,0,0),(0,1,0),(0,2,1)]:case(name,s,nf,1,nf-1,vm=vm,mask=mask,start=start)
    for s in range(4):
        for nf in (2,8):
            for element in (0,1):
                for field in range(nf):case(f'vle{8<<s}ff_v',s,nf,element,field)
    assert len(scenarios)==404
    return rows,scenarios


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    model_path=ROOT/'build/spike-memory-model/results.json';model=json.loads(model_path.read_text())
    assert model['status']=='PASS' and sha(ROOT/model['binary'])==model['binary_sha256']
    ev,scenarios=events();states=memory.reference(ev,OUT,model)
    with gzip.open(OUT/'stimulus.txt.gz','wt') as out:
        for e in ev:
            if e['kind']=='R':out.write(f'R {e["register"]} {e["data"]:032x}\n')
            elif e['kind']=='M':out.write('M '+e['data']+'\n')
            elif e['kind']=='F':out.write(f'F {e["address"]:x} {e["length"]:x}\n')
            else:
                s=states[e['id']]
                values=[e[k] for k in ('id','instruction','scalar','scalar2','avl')]+[s[k] for k in ('illegal','cause','tval','writes','scalar','vl','vtype','vstart','vxrm','vxsat','frm','fflags')]
                words=(ROOT/s['rf']).read_text().split();assert len(words)==64
                out.write('E '+' '.join(words)+'\n')
                out.write('I '+' '.join(f'{x:x}' for x in values)+' @ '+s['ram']+'\n')
    table=[];fof_traps=fof_trims=0
    for c in scenarios:
        f=states[c['fault_id']];r=states[c['retry_id']]
        assert not f['illegal'] and not r['cause']
        if c['arithmetic_id'] is not None:
            a=states[c['arithmetic_id']];csr=states[c['csr_id']]
            if c['fault_element']==0:
                assert f['cause']==5 and f['vl']==2 and f['vstart']==0;fof_traps+=1
            else:
                assert f['cause']==0 and f['vl']==1 and f['vstart']==0;fof_trims+=1
            assert not a['cause'] and a['vl']==f['vl'] and csr['scalar']==f['vl'] and r['vl']==f['vl']
        elif c['vm'] or c['mask']>>c['fault_element']&1:
            assert f['cause']==(7 if c['name'].startswith('vs') else 5) and f['vl']==2 and f['vstart']==c['fault_element']
        else:assert f['cause']==0 and f['vl']==2 and f['vstart']==0
        table.append(dict(c,observed_cause=f['cause'],observed_vl=f['vl'],observed_vstart=f['vstart']))
    assert fof_traps==fof_trims==40
    with (OUT/'cases.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator='\n');w.writeheader();w.writerows(table)
    for name in ('spike-input.txt','spike-output.txt'):
        p=OUT/name;p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
    artifacts=[model_path,OUT/'stimulus.txt.gz',OUT/'cases.csv',*sorted(OUT.glob('spike-*')),*sorted((OUT/'gold').glob('*.hex'))]
    d=dict(status='PASS',commands=len(states),scenarios=len(scenarios),strided_cases=324,fof_cases=80,fof_element0_traps=fof_traps,fof_later_truncations=fof_trims,
           reference='UNMODIFIED_SPIKE_PLUS_EXPLICIT_VL_VSTART_CLAUSE_ASSERTIONS',oracle_binary=model['binary'],oracle_binary_sha256=model['binary_sha256'],
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/m57_isa_catalog.py',ROOT/'tests/test_spike_memory.py']},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS recovery oracle',d['commands'],'commands',len(scenarios),'scenarios',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--top',choices=['SpinorStandard','SpinorDeep'],default='SpinorStandard');a=p.parse_args()
    if a.prepare_only:prepare();return
    ref=json.loads((OUT/'results.json').read_text())
    for group in ('source_sha256','artifact_sha256'):
        for rel,h in ref[group].items():assert sha(ROOT/rel)==h,rel
    out=OUT/a.top;summary,negative,artifacts=run_fixture(a.top,out,OUT/'stimulus.txt.gz',memory=True)
    assert f'commands={ref["commands"]} ' in summary
    artifacts[str((OUT/'results.json').relative_to(ROOT))]=sha(OUT/'results.json')
    source=[Path(__file__).resolve(),ROOT/'scripts/m58_stream.py',ROOT/'tests/m58_stream_driver.cc',ROOT/'tests/gsim_spike_driver.cc']
    d=dict(status='PASS',top=a.top,commands=ref['commands'],scenarios=ref['scenarios'],summary=summary,trace_replay=False,checked_registers_per_command=32,checked_ram_bytes_per_command=8192,
           negative_controls=negative,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source},artifact_sha256=artifacts)
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS field recovery and FOF consumers',a.top,ref['commands'],'commands',flush=True)


if __name__=='__main__':main()
