#!/usr/bin/env python3
"""Numerical all-encoding/all-vtype TA/MA policy matrix, unmodified Spike."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from m58_stream import ROOT,sha,run_fixture
from m57_isa_catalog import catalog

OUT=ROOT/'build/m58/policies'
M64=(1<<64)-1


def cases(policy):
    entries=[e for e in catalog() if (e['match']&127)==0x57 and (e['match']>>12&7)!=7]
    assert len(entries)==330
    geometry=[(s,m) for m in (0,1,2,3,5,6,7) for s in range(4) if m<4 or s<=m-5]
    result=[]
    pools={8:[0,1,0x7f,0x80,0xff,0xa5],16:[0,1,0x7fff,0x8000,0xffff,0x3c01],
           32:[0,1,0x80000000,0x3f800001,0xbf800000,0x7f800001,0x7fc12345,0x7f7fffff],
           64:[0,1,0x8000000000000000,0x3ff0000000000001,0xbff0000000000000,0x7ff0000000000001,0x7ff8123456789abc,0x7fefffffffffffff]}
    for g,(s,m) in enumerate(geometry):
        bits=8<<s;maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
        for i,e in enumerate(entries):
            variant=(i+g+policy)%4
            vm=int(variant==0)
            mask=[M64|(M64<<64),0,int('a596'*8,16),M64|(M64<<64)][variant]
            regs=[sum(pools[bits][(r+k+i+policy)%len(pools[bits])]<<(bits*k) for k in range(128//bits)) for r in range(32)]
            regs[0]=mask
            # Include valid and out-of-range gather indices, including each
            # index register of an m8 group; it is still a true numerical run.
            if e['name'].startswith('vrgather') and e['name'].endswith('_vv'):
                iw=16 if e['name'].startswith('vrgatherei16') else bits
                for r in range(24,32):
                    first=(r-24)*128//iw
                    regs[r]=sum(([0,1,maximum-1,maximum,maximum+1][(first+k)%5])<<(iw*k) for k in range(128//iw))
            fields=vm<<25|16<<20|24<<15|8<<7
            raw=e['match']|(fields&~e['mask'])
            scalar=[0,M64,1<<63,127][variant]
            if (raw>>12&7)==5:
                scalar=([0xffffffff7f800001,0xffffffff3f800001,0x123456783f800000,0xffffffff80000000] if bits==32 else
                        [0x7ff0000000000001,0x3ff0000000000001,0x8000000000000000,0xbff0000000000000])[variant]
            result.append(dict(name=e['name'],raw=raw,sew=bits,lmul=m,policy=policy,vm=(raw>>25)&1,
                               vtype=(s<<3)|m|(policy<<6),length=1 if (g+i)%3==0 else max(1,maximum-1),
                               maximum=maximum,scalar=scalar,frm=(i+g)%5,vcsr=((i%4)<<1)|(g%2),
                               initial_flags=0 if variant==1 else [0,1,0x15,0x1f][variant],registers=regs))
    assert len(result)==7260
    return result


def prepare(policy):
    folder=OUT/f'p{policy}';folder.mkdir(parents=True,exist_ok=True)
    model_path=ROOT/'build/m55/reference/results.json';model=json.loads(model_path.read_text())
    assert model['status']=='PASS' and sha(ROOT/model['binary'])==model['binary_sha256']
    rows=cases(policy);events=[];targets={};ident=0
    def ins(raw,scalar=0,avl=0,target=None):
        nonlocal ident
        events.append(dict(kind='I',id=ident,instruction=raw,scalar=scalar,scalar2=0,avl=avl))
        if target is not None:targets[ident]=target
        ident+=1
    for c in rows:
        events.extend(dict(kind='R',register=r,data=value) for r,value in enumerate(c['registers']))
        ins(c['vtype']<<20|1<<15|7<<12|3<<7|0x57,avl=c['length'])
        ins(15<<20|1<<15|1<<12|3<<7|0x73,scalar=c['vcsr'])
        ins(3<<20|1<<15|1<<12|3<<7|0x73,scalar=(c['frm']<<5)|c['initial_flags'])
        ins(c['raw'],scalar=c['scalar'],target=c)
    transport=[]
    for e in events:
        if e['kind']=='R':transport.append(f'R {e["register"]} {e["data"]:032x}')
        else:transport.append('I '+' '.join(f'{e[k]:x}' for k in ('instruction','scalar','scalar2','avl')))
    text='\n'.join(transport)+'\n'
    response=subprocess.run([ROOT/model['binary']],input=text,text=True,capture_output=True,cwd=ROOT,check=True,timeout=180)
    (folder/'spike-input.txt.gz').write_bytes(gzip.compress(text.encode(),mtime=0))
    (folder/'spike-output.txt.gz').write_bytes(gzip.compress(response.stdout.encode(),mtime=0))
    (folder/'spike-stderr.log').write_text(response.stderr)
    states=response.stdout.splitlines();assert len(states)==ident
    success=Counter();rejected=Counter();flagged=0;saturated=0;target_states=[]
    fixture=folder/'stimulus.txt.gz'
    with gzip.open(fixture,'wt') as out:
        for e in events:
            if e['kind']=='R':out.write(f'R {e["register"]} {e["data"]:032x}\n');continue
            f=states[e['id']].split();assert f[0]=='S' and len(f)==45 and int(f[1])==e['id']
            cause=int(f[3]);assert cause in (0,2)
            values=[e[k] for k in ('id','instruction','scalar','scalar2','avl')]+[int(f[2]),cause,0,int(f[5],16),int(f[4],16),*[int(x,16) for x in f[6:13]]]
            words=[int(r,16)>>(64*k)&M64 for r in f[13:] for k in range(2)]
            out.write('E '+' '.join(f'{x:x}' for x in words)+'\n')
            out.write('I '+' '.join(f'{x:x}' for x in values)+' @ -\n')
            if e['id'] in targets:
                c=targets[e['id']];(rejected if cause else success)[c['name']]+=1
                target_states.append(dict(name=c['name'],sew=c['sew'],lmul=c['lmul'],policy=policy,vm=c['vm'],length=c['length'],legal=not cause))
                flagged+=not cause and int(f[12],16)!=c['initial_flags']
                saturated+=not cause and int(f[10],16)!=(c['vcsr']&1)
    assert len(success)==330,(policy,'canonical encoding without a legal sample',len(success))
    assert flagged and saturated
    (folder/'cases.json.gz').write_bytes(gzip.compress(json.dumps(target_states,separators=(',',':')).encode(),mtime=0))
    d=dict(status='PASS',policy=policy,scenarios=len(rows),commands=ident,legal_targets=sum(success.values()),rejected_targets=sum(rejected.values()),
           successful_encodings=dict(success),flag_updates=flagged,saturation_updates=saturated,vstart=0,
           oracle='UNMODIFIED_SPIKE_ACTUAL_VTA_VMA_BITS_NO_EXPECTATION_NORMALIZATION',oracle_binary=model['binary'],oracle_binary_sha256=model['binary_sha256'],
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/m57_isa_catalog.py']},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [model_path,fixture,folder/'cases.json.gz',*sorted(folder.glob('spike-*'))]})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n')
    print('PASS policy oracle',policy,ident,'commands',len(success),'successful encodings',flush=True)
    return folder,d


def main():
    p=argparse.ArgumentParser();p.add_argument('--policy',type=int,choices=range(4),required=True)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--top',choices=['SpinorStandard','SpinorDeep'],default='SpinorStandard');a=p.parse_args()
    if a.prepare_only:prepare(a.policy);return
    folder=OUT/f'p{a.policy}';ref=json.loads((folder/'results.json').read_text())
    for group in ('source_sha256','artifact_sha256'):
        for rel,h in ref[group].items():assert sha(ROOT/rel)==h,rel
    out=folder/a.top;summary,negative,artifacts=run_fixture(a.top,out,folder/'stimulus.txt.gz')
    assert f'commands={ref["commands"]} ' in summary
    sources=[Path(__file__).resolve(),ROOT/'scripts/m58_stream.py',ROOT/'tests/m58_stream_driver.cc',ROOT/'tests/gsim_spike_driver.cc']
    artifacts[str((folder/'results.json').relative_to(ROOT))]=sha(folder/'results.json')
    d=dict(status='PASS',top=a.top,policy=a.policy,summary=summary,commands=ref['commands'],scenarios=ref['scenarios'],trace_replay=False,checked_registers_per_command=32,
           negative_controls=negative,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256=artifacts)
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS numeric policy matrix',a.top,a.policy,ref['commands'],'commands',flush=True)


if __name__=='__main__':main()
