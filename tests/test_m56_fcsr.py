#!/usr/bin/env python3
"""CPU FCSR owner model + real production public VPU, Spike per-instruction flags."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from test_compiled_programs import ROOT,env
import test_spike_differential as spike
from m56_fcsr_events import cases,fp_execution
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OUT=ROOT/'build/m56'
def corpus():
    folder=OUT/'corpus';folder.mkdir(parents=True,exist_ok=True);model_path=ROOT/'build/m55/reference/results.json';model=json.loads(model_path.read_text())
    sources=[Path(__file__).resolve(),ROOT/'tests/m56_fcsr_events.py',ROOT/'tests/test_spike_differential.py',ROOT/'tests/m55_zvbb_events.py']
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sources};record=folder/'results.json'
    if record.exists():
        d=json.loads(record.read_text())
        if d['source_sha256']==inputs:
            for p,h in d['artifact_sha256'].items():assert sha(ROOT/p)==h,p
            return folder,d
    for p,h in model['source_sha256'].items():assert sha(ROOT/p)==h,p
    events=[];blocks=[];ident=0
    def ins(raw,scalar=0,avl=0):
        nonlocal ident
        events.append(dict(kind='I',id=ident,instruction=raw,scalar=scalar,scalar2=0,avl=avl));ident+=1;return ident-1
    for c in cases():
        s=(c['sew']//8).bit_length()-1;typ=s<<3|c['lmul']
        config=ins(typ<<20|1<<15|7<<12|3<<7|0x57,avl=c['length'])
        vc=ins(15<<20|1<<15|1<<12|3<<7|0x73,scalar=c['vcsr'])
        for r,bits in enumerate(c['registers']):events.append(dict(kind='R',register=r,data=bits))
        ins(2<<20|1<<15|1<<12|3<<7|0x73,scalar=c['frm']);ins(1<<20|1<<15|1<<12|3<<7|0x73,scalar=0)
        target=ins(c['instruction'],scalar=c['scalar']);blocks.append(dict(c,config=config,vcsr_command=vc,target=target))
    states=spike.run_model(events,folder,model);gold=folder/'gold';gold.mkdir(exist_ok=True);lines=[];commands=0;valids=0;deltas={};mutations=0;success={}
    def emit(mid,c,kind):
        nonlocal commands,valids,mutations
        e=events_by_id[mid];state=states[mid];target=kind=='target'
        legal=not state['illegal'];valid=target and legal and fp_execution(c['instruction']);delta=state['fflags'] if valid else 0
        rm=(7 if c['frm']<5 else 0) if target and c['mutate'] else c['frm']
        flags=(c['initial_flags']^31) if target and c['mutate'] else c['initial_flags'];flags|=delta
        values=[commands,e['instruction'],e['scalar'],0,e['avl'],state['illegal'],state['cause'],0,state['writes'],state['scalar'],state['vl'],state['vtype'],state['vstart'],state['vxrm'],state['vxsat'],rm,flags]
        text=''.join(f'{r>>(64*k)&((1<<64)-1):016x}\n' for r in state['registers'] for k in range(2));p=gold/(hashlib.sha256(text.encode()).hexdigest()+'.hex');p.write_text(text)
        lines.append('I '+' '.join(f'{x:x}' for x in values)+' '+str(p.relative_to(ROOT))+' - '+f'{delta:x} {int(valid):x} {int(target and c["mutate"]):x}')
        commands+=1;valids+=valid;mutations+=target and c['mutate']
        if target:
            deltas[str(delta)]=deltas.get(str(delta),0)+1
            if legal:success[c['name']]=success.get(c['name'],0)+1
    events_by_id={e['id']:e for e in events if e['kind']=='I'}
    for c in blocks:
        lines.append(f'P {c["frm"]:x} {c["initial_flags"]:x}');emit(c['config'],c,'config');emit(c['vcsr_command'],c,'vcsr')
        lines.extend(f'R {r} {bits:032x}' for r,bits in enumerate(c['registers']));emit(c['target'],c,'target')
    # FCSR/frm/fflags CSR traffic belongs to CPU, including zero-source reads.
    tail=states[-1];text=''.join(f'{r>>(64*k)&((1<<64)-1):016x}\n' for r in tail['registers'] for k in range(2));p=gold/(hashlib.sha256(text.encode()).hexdigest()+'.hex');p.write_text(text);reserved=0
    for rm in range(8):
        lines.append(f'P {rm:x} {31-rm:x}')
        for addr in [1,2,3]:
            for action in [1,2,3,5,6,7]:
                for src in [0,1,31]:
                    for rd in [0,3]:
                        raw=addr<<20|src<<15|action<<12|rd<<7|0x73
                        values=[commands,raw,0x9f,0,0,1,2,0,0,0,tail['vl'],tail['vtype'],tail['vstart'],tail['vxrm'],tail['vxsat'],rm,31-rm]
                        lines.append('I '+' '.join(f'{x:x}' for x in values)+' '+str(p.relative_to(ROOT))+' - 0 0 0');commands+=1;reserved+=1
    stimulus=folder/'stimulus.txt';stimulus.write_text('\n'.join(lines)+'\n')
    (folder/'cases.json').write_text(json.dumps([{k:v for k,v in c.items() if k!='registers'} for c in blocks],indent=2)+'\n')
    artifacts=[stimulus,folder/'cases.json',*folder.glob('spike-*'),*gold.glob('*.hex'),model_path]
    d=dict(status='PASS',numeric_cases=len(blocks),commands=commands,spike_commands=len(states),valid_flag_deltas=valids,delta_histogram=deltas,snapshot_input_mutations=mutations,host_owned_csr_rejections=reserved,successful_encodings=success,
       oracle='UNMODIFIED_SPIKE_PER_INSTRUCTION_FLAGS_PLUS_SOFTWARE_CPU_FCSR_OWNER',source_sha256=inputs,artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    record.write_text(json.dumps(d,indent=2)+'\n');return folder,d

def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorHost',choices=['SpinorHost','SpinorHostDeep']);a=p.parse_args()
    folder,ref=corpus();out=OUT/'fcsr'/a.top;out.mkdir(parents=True,exist_ok=True);gdir=OUT/'gsim/rtl'/a.top;binary=out/'run';harness=ROOT/'tests/m56_host_driver.cc'
    cmd=[ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-DENABLE_FP=1','-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
    for command,label in [(cmd,'compile.log'),([binary,folder/'stimulus.txt'],'run.log')]:
        with (out/label).open('w') as f:subprocess.run(list(map(str,command)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=300)
    summary=next(x for x in (out/'run.log').read_text().splitlines() if x.startswith('PASS host FCSR'));assert f'commands={ref["commands"]}' in summary
    negatives={}
    for mode,diagnostic in [('wrong-token','completion token mismatch'),('wrong-rf','RF mismatch'),('wrong-csr','CSR mismatch'),('wrong-delta','flag delta mismatch'),('early-merge','CPU FCSR changed before retirement')]:
        with (out/(mode+'.log')).open('w') as f:r=subprocess.run([binary,folder/'stimulus.txt',mode],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
        assert r.returncode==1 and diagnostic in (out/(mode+'.log')).read_text(),mode;negatives[mode]='REJECTED'
    d=dict(status='PASS',top=a.top,summary=summary,commands=ref['commands'],negative_controls=negatives,
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),harness,ROOT/'tests/m56_fcsr_events.py']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary,*out.glob('*.log'),folder/'results.json',gdir/'results.json']})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(summary)
if __name__=='__main__':main()
