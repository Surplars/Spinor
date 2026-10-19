#!/usr/bin/env python3
"""Independent architectural oracle: nonzero vstart and normative mask aliases.

Spike's pinned processor deliberately disables arithmetic vstart. We do not
patch Spike or label these cases as Spike comparisons.
"""
import argparse,hashlib,json,random,subprocess,sys
from pathlib import Path
from test_compiled_programs import ROOT,env
from m55_zvbb_events import catalog,encoded
from test_m55_lane import golden
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    folder=ROOT/'build/m55/restart'/a.top;folder.mkdir(parents=True,exist_ok=True);gold=folder/'gold';gold.mkdir(exist_ok=True)
    cache=ROOT/'build/m55/gsim/bin'/a.top;build=json.loads((cache/'build.json').read_text());binary=cache/'run'
    assert sha(binary)==build['binary_sha256']
    for rel,h in build['inputs'].items():assert sha(ROOT/rel)==h,rel
    rng=random.Random(0x55e128);lines=[];cases=[];ident=0
    def rf_file(regs):
        text=''.join(f'{r>>(64*k)&((1<<64)-1):016x}\n' for r in regs for k in range(2));p=gold/(hashlib.sha256(text.encode()).hexdigest()+'.hex');p.write_text(text);return str(p.relative_to(ROOT))
    def command(raw,scalar,avl,illegal,writes,result,vl,typ,start,regs):
        nonlocal ident
        fields=[ident,raw,scalar,0,avl,illegal,2 if illegal else 0,0,writes,result,vl,typ,start,0,0,0,0]
        lines.append('I '+' '.join(f'{n:x}' for n in fields)+' '+rf_file(regs)+' -');ident+=1
    mapping=dict(vandn=29,vbrev8=30,vbrev=31,vrev8=32,vclz=33,vctz=34,vcpop=35,vrol=36,vror=37,vwsll=5)
    def case(e,s,m,requested,start,vm,src=16,operand=24,reserved=False):
        typ=s<<3|m;maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m);vl=min(maximum,requested)
        regs=[rng.getrandbits(128) for _ in range(32)];regs[0]=int('a596'*8,16);lines.extend(f'R {i} {r:032x}' for i,r in enumerate(regs))
        command(typ<<20|1<<15|7<<12|3<<7|0x57,0,requested,0,1,vl,vl,typ,0,regs)
        command(8<<20|1<<15|1<<12|3<<7|0x73,start,0,0,1,0,vl,typ,start,regs)
        name=e['name'];wide=name.startswith('vwsll');illegal=reserved or wide and (s==3 or m==3)
        if name.endswith('_vi'):operand=63 if name=='vror_vi' else 31
        raw=encoded(e,vm,8,src,operand);scalar=33
        before=bytearray().join(r.to_bytes(16,'little') for r in regs);after=bytearray(before)
        bits=8<<s;outbits=bits*2 if wide else bits;mask=(1<<outbits)-1
        for i in range(start,vl) if not illegal else []:
            if not vm and not(regs[0]>>i&1):continue
            pos=src*16+i*(bits//8);x=int.from_bytes(before[pos:pos+bits//8],'little')
            if name.endswith('_vv'):
                pos=operand*16+i*(bits//8);y=int.from_bytes(before[pos:pos+bits//8],'little')
            elif name.endswith('_vi'):y=operand
            else:y=scalar
            value=golden(x,y,s+int(wide),mapping[name.rsplit('_',1)[0]],0)&mask
            pos=8*16+i*(outbits//8);after[pos:pos+outbits//8]=value.to_bytes(outbits//8,'little')
        result=[int.from_bytes(after[16*i:16*i+16],'little') for i in range(32)]
        command(raw,scalar,0,int(illegal),0,0,vl,typ,start if illegal else 0,result)
        cases.append(dict(name=name,sew=bits,lmul=m,vl=vl,vstart=start,vm=vm,illegal=bool(illegal),normative_reserved=reserved))
    for s,m in [(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]:
        for e in catalog():
            for requested,start,vm in [(0,1,0),(128,1,1),(128,2,0),(128,127,1)]:case(e,s,m,requested,start,vm)
    for e in catalog():
        for requested,start in [(0,0),(128,1)]:
            case(e,1,0,requested,start,0,src=0,reserved=True)
            if e['name'].endswith('_vv'):case(e,1,0,requested,start,0,operand=0,reserved=True)
    stimulus=folder/'stimulus.txt';stimulus.write_text('\n'.join(lines)+'\n');log=folder/'run.log'
    with log.open('w') as f:r=subprocess.run([binary,stimulus],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
    assert r.returncode==0,log.read_text()[-2000:]
    summary=next(x for x in log.read_text().splitlines() if x.startswith('PASS direct GSIM'));assert 'requests=0 responses=0' in summary
    negative={}
    for mode,diagnostic in [('wrong-token','completion token mismatch'),('wrong-rf','RF mismatch'),('wrong-csr','CSR mismatch')]:
        target=folder/(mode+'.log')
        with target.open('w') as f:r=subprocess.run([binary,stimulus,mode],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=30)
        assert r.returncode==1 and diagnostic in target.read_text();negative[mode]='REJECTED'
    spec=ROOT/'docs/references/m36-integer-v1.0.txt'
    assert 'A mask register source is\nconsidered to have EEW=1' in spec.read_text()
    d=dict(status='PASS',top=a.top,oracle='INDEPENDENT_PYTHON_ARCHITECTURAL_AND_NORMATIVE_POLICY_NOT_SPIKE',commands=ident,cases=len(cases),
      reserved_alias_cases=sum(c['normative_reserved'] for c in cases),nonzero_vstart_cases=sum(c['vstart']>0 and not c['normative_reserved'] for c in cases),negative_controls=negative,summary=summary,
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/m55_zvbb_events.py',ROOT/'tests/test_m55_lane.py',spec]},
      artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [stimulus,binary,cache/'build.json',*gold.glob('*.hex'),*folder.glob('*.log')]})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS independent Zvbb restart/mask-alias',a.top,len(cases),'cases',ident,'commands')
if __name__=='__main__':main()
