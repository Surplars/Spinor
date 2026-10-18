#!/usr/bin/env python3
"""Direct adaptive GSIM/Spike differential; no Icarus trace or replay input."""
import argparse,hashlib,json,subprocess,time
from collections import Counter
from pathlib import Path
from test_compiled_programs import ROOT,env
import test_spike_memory as memory
import test_spike_differential as arithmetic
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OUT=ROOT/'build/gsim-direct'
def validate(d):
    assert d['status']=='PASS'
    for key in ['sha256','source_sha256','artifact_sha256','external_source_sha256']:
        for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
def run(command,log,timeout=600):
    start=time.perf_counter()
    with log.open('w') as f:r=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=f,stderr=f,env=env(),timeout=timeout)
    assert r.returncode==0,(command,log.read_text()[-2000:]);return time.perf_counter()-start

def reference(suite,compact,fp):
    label=suite+('-compact' if compact else '-full')+('-fp' if fp else '-int') if suite=='arithmetic' else suite+('-compact' if compact else '-full')
    folder=OUT/'corpus'/label;folder.mkdir(parents=True,exist_ok=True)
    source=[Path(__file__).resolve(),ROOT/'tests/test_spike_memory.py',ROOT/'tests/test_spike_differential.py',ROOT/'tests/test_compiled_programs.py']
    if suite.startswith('edges'):source.append(ROOT/'tests/spike_memory_edges.py')
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in source}
    model_path=ROOT/('build/spike-model/results.json' if suite=='arithmetic' else 'build/spike-memory-model/results.json')
    model=json.loads(model_path.read_text());validate(model)
    record=folder/'results.json';saved=json.loads(record.read_text()) if record.exists() else {}
    reused=saved.get('source_sha256')==source_hashes and saved.get('model_manifest_sha256')==sha(model_path)
    if reused:
        validate(saved)
        return folder,json.loads((folder/'inputs.json').read_text()),json.loads((folder/'expected.json').read_text()),model,True
    if suite=='memory' or suite.startswith('edges'):
        entries=json.loads((ROOT/'build/spike-memory-model/catalog.json').read_text())
        if suite.startswith('edges'):
            from spike_memory_edges import events_for,bounded_events_for
            events=(bounded_events_for if suite=='edges-bounded' else events_for)(entries)
        else:events=memory.events_for(entries,compact)
        states=memory.reference(events,folder,model)
    else:
        catalog,model=arithmetic.catalog();entries=catalog['v_alu_int']+(catalog['v_alu_fp'] if fp else [])
        events=arithmetic.events_for(entries,compact)
        if not fp:
            events=[e for e in events if not(e['kind']=='I' and e.get('address') in [1,2,3])]
            for i,e in enumerate(e for e in events if e['kind']=='I'):e['id']=i
        raw=arithmetic.run_model(events,folder,model);states=[];gold=folder/'gold';gold.mkdir(exist_ok=True)
        for s in raw:
            text=''.join(f'{r>>(64*k)&memory.M64:016x}\n' for r in s.pop('registers') for k in range(2));path=gold/(hashlib.sha256(text.encode()).hexdigest()+'.hex');path.write_text(text)
            states.append(dict(s,tval=0,rf=str(path.relative_to(ROOT)),ram='-'))
    (folder/'inputs.json').write_text(json.dumps(events,indent=2)+'\n');(folder/'expected.json').write_text(json.dumps(states,indent=2)+'\n')
    artifacts=[*folder.glob('gold/*.hex'),folder/'inputs.json',folder/'expected.json',folder/'spike-input.txt',folder/'spike-output.txt',folder/'spike-stderr.log',model_path]
    d=dict(status='PASS',commands=len(states),reference='UNMODIFIED_UPSTREAM_SPIKE',model_manifest_sha256=sha(model_path),model_binary_sha256=model['binary_sha256'],source_sha256=source_hashes,artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    record.write_text(json.dumps(d,indent=2)+'\n');return folder,events,states,model,False

def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);p.add_argument('--suite',default='memory',choices=['memory','arithmetic','edges','edges-bounded']);p.add_argument('--compact',action='store_true');a=p.parse_args()
    assert not(a.suite.startswith('edges') and a.compact),'Edge matrix has one complete bounded definition'
    label=a.top+'-'+a.suite+('-compact' if a.compact else '-full');folder=OUT/label;folder.mkdir(parents=True,exist_ok=True);fp='Integer' not in a.top
    tool=json.loads((ROOT/'build/gsim-model/results.json').read_text());validate(tool)
    gdir=ROOT/f'build/gsim-direct/rtl/{a.top}';export=json.loads((gdir/'results.json').read_text());validate(export)
    corpus,events,states,model,reference_reused=reference(a.suite,a.compact,fp)
    lines=[]
    for e in events:
        if e['kind']=='R':lines.append(f'R {e["register"]} {e["data"]:032x}')
        elif e['kind']=='M':lines.append('M '+e['data'])
        elif e['kind']=='F':lines.append(f'F {e["address"]:x} {e["length"]:x}')
        else:
            s=states[e['id']];values=[e[k] for k in ['id','instruction','scalar','scalar2','avl']]+[s[k] for k in ['illegal','cause','tval','writes','scalar','vl','vtype','vstart','vxrm','vxsat','frm','fflags']]
            lines.append('I '+' '.join(f'{x:x}' for x in values)+' '+s['rf']+' '+s['ram'])
    stimulus=folder/'stimulus.txt';stimulus.write_text('\n'.join(lines)+'\n')
    harness=ROOT/'tests/gsim_spike_driver.cc';cache=OUT/'bin'/a.top;cache.mkdir(parents=True,exist_ok=True);binary=cache/'run'
    command=[ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-DENABLE_FP='+str(int(fp)),'-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [harness,gdir/(a.top+'.h'),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),ROOT/'tools/llvm-program/usr/bin/clang++-19']}
    saved=cache/'build.json';previous=json.loads(saved.read_text()) if saved.exists() else {}
    reused=previous.get('inputs')==inputs and binary.exists() and previous.get('binary_sha256')==sha(binary)
    if reused:
        compile_seconds=0.0;(folder/'compile.log').write_text('REUSED EXACT SOURCE/COMPILER/BINARY SHA MATCH\n')
    else:
        compile_seconds=run(command,folder/'compile.log',1200)
        saved.write_text(json.dumps(dict(inputs=inputs,binary_sha256=sha(binary),command=list(map(str,command)),compile_seconds=compile_seconds),indent=2)+'\n')
    seconds=run([binary,stimulus],folder/'run.log')
    output=(folder/'run.log').read_text();summary=next(x for x in output.splitlines() if x.startswith('PASS direct GSIM'))
    timings=[dict(id=int(f[1]),cycles=int(f[2]),requests=int(f[3])) for f in (x.split() for x in output.splitlines() if x.startswith('CMD '))];assert len(timings)==len(states)
    negative={};cases={'wrong-token':'completion token mismatch','wrong-rf':'RF mismatch','wrong-csr':'CSR mismatch'}
    if a.suite!='arithmetic':cases.update({'corrupt-load':'RF mismatch','wrong-ram':'RAM mismatch','wrong-tval':'memory fault address mismatch'})
    for name,diagnostic in cases.items():
        log=folder/(name+'.log')
        with log.open('w') as f:r=subprocess.run([binary,stimulus,name],cwd=ROOT,stdout=f,stderr=f,env=env(),timeout=120)
        assert r.returncode==1 and diagnostic in log.read_text(),(name,log.read_text()[-2000:]);negative[name]='REJECTED'
    sources=[Path(__file__).resolve(),harness,ROOT/'tests/test_spike_memory.py',ROOT/'tests/test_spike_differential.py',ROOT/'tests/test_compiled_programs.py']
    if a.suite.startswith('edges'):sources.append(ROOT/'tests/spike_memory_edges.py')
    artifacts=[stimulus,binary,saved,*folder.glob('*.log'),corpus/'results.json',gdir/'results.json',ROOT/'build/gsim-model/results.json']
    coverage=Counter(e.get('category','arithmetic' if a.suite=='arithmetic' else 'memory-or-config') for e in events if e['kind']=='I')
    d=dict(status='PASS',top=a.top,suite=a.suite,compact=a.compact,driver='DIRECT_ADAPTIVE_PUBLIC_PORTS',trace_replay=False,commands=len(states),timings=timings,summary=summary,compile_reused=reused,compile_seconds=compile_seconds,reference_reused=reference_reused,run_wall_seconds=seconds,negative_controls=negative,
      coverage=dict(coverage),fault_commands=sum(s['cause'] not in [0,2] for s in states),illegal_commands=sum(s['cause']==2 for s in states),
      checked_registers_per_command=32,checked_ram_bytes_per_command=8192 if a.suite!='arithmetic' else 0,independent_reference='UNMODIFIED_UPSTREAM_SPIKE',revision=model['revision'],hardware_changed=False,
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(label,summary,seconds,'seconds',flush=True)
if __name__=='__main__':main()
