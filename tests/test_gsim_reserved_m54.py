#!/usr/bin/env python3
"""Normative rejection policy for mixed-EEW store source aliases.

The pinned upstream Spike executes these reserved encodings. This standalone
oracle instead checks our documented rejection policy, unchanged state and no
TileLink traffic. It is never labelled a Spike architectural comparison.
"""
import argparse,hashlib,json,random,subprocess,time
from pathlib import Path
from test_compiled_programs import ROOT,env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    folder=ROOT/'build/m54/reserved-eew'/a.top;folder.mkdir(parents=True,exist_ok=True);gold=folder/'gold';gold.mkdir(exist_ok=True)
    cache=ROOT/'build/m54/gsim/bin'/a.top;build=json.loads((cache/'build.json').read_text());binary=cache/'run'
    assert sha(binary)==build['binary_sha256']
    for rel,h in build['inputs'].items():assert sha(ROOT/rel)==h,rel
    spec=ROOT/'docs/references/m44-indexed-v1.0.txt';text=spec.read_text()
    assert 'A vector register cannot be used to provide source operands with more\nthan one EEW for a single instruction.' in text
    catalog={e['name']:e for e in json.loads((ROOT/'build/spike-memory-model/catalog.json').read_text())}
    ram=bytes((i*13+7)&255 for i in range(8192));ram_path=gold/'ram.hex';ram_path.write_text(''.join(f'{b:02x}\n' for b in ram))
    rng=random.Random(0x52ee1234);lines=[];cases=[];ident=0
    def command(raw,scalar,avl,illegal,writes,result,vl,typ,vstart,rf):
        nonlocal ident
        fields=[ident,raw,scalar,0,avl,illegal,2 if illegal else 0,raw if illegal else 0,writes,result,vl,typ,vstart,0,0,0,0]
        lines.append('I '+' '.join(f'{n:x}' for n in fields)+' '+str(rf.relative_to(ROOT))+' '+str(ram_path.relative_to(ROOT)));ident+=1
    geometries=[(2,0,nf,8,8,0) for nf in range(1,9)]+[(0,0,nf,10,8,2) for nf in range(1,9)]+[(2,2,nf,8,10,1) for nf in [1,2]]
    for s,lm,nf,vr,index,iw in geometries:
        for avl in [0,3]:
            for start in [0,1]:
                regs=[rng.getrandbits(128) for _ in range(32)]
                rf_text=''.join(f'{r>>(64*k)&((1<<64)-1):016x}\n' for r in regs for k in range(2));rf=gold/(hashlib.sha256(rf_text.encode()).hexdigest()+'.hex');rf.write_text(rf_text)
                lines.append('M '+ram.hex());lines.append('F 0 0');lines.extend(f'R {i} {r:032x}' for i,r in enumerate(regs))
                typ=s<<3|lm;vl=min(avl,(16>>s)*(1<<lm))
                command(typ<<20|1<<15|7<<12|3<<7|0x57,0,avl,0,1,vl,vl,typ,0,rf)
                command(8<<20|1<<15|1<<12|3<<7|0x73,start,0,0,1,0,vl,typ,start,rf)
                e=catalog[f'vsuxei{8<<iw}_v'];raw=e['match']|((nf-1)<<29|1<<25|index<<20|1<<15|vr<<7)&~e['mask']
                command(raw,0x80010800,0,1,0,0,vl,typ,start,rf)
                cases.append(dict(sew=8<<s,lmul=1<<lm,index_eew=8<<iw,nf=nf,data_register=vr,index_register=index,vl=vl,vstart=start,instruction=raw))
    stimulus=folder/'stimulus.txt';stimulus.write_text('\n'.join(lines)+'\n');log=folder/'run.log';begin=time.perf_counter()
    with log.open('w') as f:r=subprocess.run([binary,stimulus],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
    assert r.returncode==0,log.read_text()[-2000:]
    summary=next(x for x in log.read_text().splitlines() if x.startswith('PASS direct GSIM'));assert 'requests=0 responses=0' in summary
    negative={}
    for name,diagnostic in [('wrong-token','completion token mismatch'),('wrong-rf','RF mismatch'),('wrong-ram','RAM mismatch')]:
        target=folder/(name+'.log')
        with target.open('w') as f:r=subprocess.run([binary,stimulus,name],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
        assert r.returncode==1 and diagnostic in target.read_text();negative[name]='REJECTED'
    sources=[Path(__file__).resolve(),ROOT/'tests/gsim_spike_driver.cc',spec]
    artifacts=[stimulus,binary,cache/'build.json',*gold.glob('*.hex'),*folder.glob('*.log')]
    result=dict(status='PASS',oracle='NORMATIVE_RESERVED_ENCODING_REJECTION_POLICY_NOT_SPIKE',top=a.top,commands=ident,reserved_cases=len(cases),cases=cases,negative_controls=negative,run_and_negative_wall_seconds=time.perf_counter()-begin,summary=summary,
      policy='Reject before any RAM request; retain complete VRF, RAM and vstart, with illegal-instruction completion',
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS normative reserved EEW',a.top,len(cases),'cases',ident,'commands')
if __name__=='__main__':main()
