#!/usr/bin/env python3
"""Public DUT overlap/restart tests with a separate math/SoftFloat oracle."""
import argparse
from collections import Counter
import gzip
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from m58_stream import ROOT,sha,run_fixture
from m59_arch import Model,cases,reasons

OUT=ROOT/'build/m59'
M64=(1<<64)-1


def crosscheck(sew):
    folder=OUT/'reference'/f'sew{sew}';folder.mkdir(parents=True,exist_ok=True)
    model=Model();rows=[];lines=[]
    for c in cases(sew):
        if c['profile'] not in (0,1):continue
        c=dict(c,start=0)
        # Maintained source-EEW reserved policy is audited independently; the
        # fixed Spike executes some such encodings. Do not call them matches.
        if 'source-eew' in reasons(c):continue
        rows.append(c);lines.append('Z')
        lines.extend(f'R {r} {v:032x}' for r,v in enumerate(c['registers']))
        lines.extend([f'I {c["vtype"]<<20|1<<15|7<<12|3<<7|0x57:x} 0 0 {c["vl"]:x}',
                      f'I {15<<20|1<<15|1<<12|3<<7|0x73:x} {c["vcsr"]:x} 0 0',
                      f'I {3<<20|1<<15|1<<12|3<<7|0x73:x} {(c["frm"]<<5)|c["flags"]:x} 0 0',
                      f'I {c["instruction"]:x} {c["scalar"]:x} 0 0'])
    lock=ROOT/'build/m55/reference/results.json';ref=json.loads(lock.read_text());assert sha(ROOT/ref['binary'])==ref['binary_sha256']
    transport='\n'.join(lines)+'\n';p=subprocess.run([ROOT/ref['binary']],input=transport,text=True,capture_output=True,cwd=ROOT,check=True,timeout=180)
    (folder/'spike-input.txt.gz').write_bytes(gzip.compress(transport.encode(),mtime=0));(folder/'spike-output.txt.gz').write_bytes(gzip.compress(p.stdout.encode(),mtime=0));(folder/'spike-stderr.log').write_text(p.stderr)
    states=p.stdout.splitlines();assert len(states)==4*len(rows)
    legal=0
    for i,c in enumerate(rows):
        f=states[4*i+3].split();expected=model.execute(c)
        observed=dict(registers=[int(x,16) for x in f[13:]],fflags=int(f[12],16),vxsat=int(f[10],16),vstart=int(f[8],16),illegal=int(f[2]))
        assert observed=={k:expected[k] for k in observed},(i,c['name'],c['sew'],c['lmul'],c['layout'],c['vm'],expected['reasons'],{k:(observed[k],expected[k]) for k in observed if observed[k]!=expected[k]})
        legal+=not observed['illegal']
    d=dict(status='PASS',sew=sew,cases=len(rows),legal=legal,source_eeW_disagreements_excluded=True,vstart=0,oracle_binary=ref['binary'],oracle_binary_sha256=ref['binary_sha256'],
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources()},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [lock,*sorted(folder.glob('spike-*'))]})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS independent model vs Spike',sew,len(rows),'cases',legal,'legal',flush=True)


def sources():
    return [Path(__file__).resolve(),ROOT/'tests/m59_arch.py',ROOT/'tests/m57_isa_catalog.py',ROOT/'tests/reference_fp.py',ROOT/'tests/reference_fp_resize_m54.py',ROOT/'tests/fp_reference.c',ROOT/'tests/fp_resize_reference_m54.c']


def prepare(sew):
    folder=OUT/'corpus'/f'sew{sew}';folder.mkdir(parents=True,exist_ok=True)
    ref_path=OUT/'reference'/f'sew{sew}'/'results.json';ref=json.loads(ref_path.read_text());assert ref['status']=='PASS'
    for rel,h in ref['source_sha256'].items():assert sha(ROOT/rel)==h,rel
    model=Model();ident=0;vl=0;typ=1<<63;start=0;vxrm=sat=frm=flags=0;regs=[0]*32
    stats=Counter();why=Counter();legal_names=set();records=[]
    def emit(out,raw,scalar=0,avl=0,bad=0,writes=0,value=0):
        nonlocal ident
        words=[r>>(64*k)&M64 for r in regs for k in range(2)]
        values=[ident,raw,scalar,0,avl,bad,2 if bad else 0,0,writes,value,vl,typ,start,vxrm,sat,frm,flags]
        out.write('E '+' '.join(f'{x:x}' for x in words)+'\nI '+' '.join(f'{x:x}' for x in values)+' @ -\n');ident+=1
    with gzip.open(folder/'stimulus.txt.gz','wt') as out:
        for c in cases(sew):
            regs=c['registers'];out.writelines(f'R {r} {v:032x}\n' for r,v in enumerate(regs))
            vl=c['vl'];typ=c['vtype'];start=0
            emit(out,typ<<20|1<<15|7<<12|3<<7|0x57,avl=vl,writes=1,value=vl)
            old=(vxrm<<1)|sat;vxrm=c['vcsr']>>1;sat=c['vcsr']&1
            emit(out,15<<20|1<<15|1<<12|3<<7|0x73,scalar=c['vcsr'],writes=1,value=old)
            old=(frm<<5)|flags;frm=c['frm'];flags=c['flags']
            emit(out,3<<20|1<<15|1<<12|3<<7|0x73,scalar=(frm<<5)|flags,writes=1,value=old)
            start=c['start'];emit(out,8<<20|1<<15|1<<12|3<<7|0x73,scalar=start,writes=1)
            result=model.execute(c);regs=result['registers'];start=result['vstart'];sat=result['vxsat'];flags=result['fflags']
            emit(out,c['instruction'],scalar=c['scalar'],bad=result['illegal'])
            stats['cases']+=1;stats['rejected' if result['illegal'] else 'legal']+=1;why.update(result['reasons'])
            if not result['illegal']:
                legal_names.add(c['name']);stats['nonzero_start_legal']+=c['start']>0;stats['resume_with_work']+=0<c['start']<c['vl']
            records.append(dict(name=c['name'],lmul=c['lmul'],vd=c['vd'],vs2=c['vs2'],vs1=c['vs1'],vm=c['vm'],vl=c['vl'],vstart=c['start'],profile=c['profile'],legal=not result['illegal'],reasons=result['reasons']))
    (folder/'cases.json.gz').write_bytes(gzip.compress(json.dumps(records,separators=(',',':')).encode(),mtime=0))
    libs=[ROOT/'tools/fp/libfp-reference.so',ROOT/'build/m54/reference/libresize.so']
    d=dict(status='PASS',sew=sew,commands=ident,stats=dict(stats),rejection_reasons=dict(why),legal_encodings=sorted(legal_names),
           oracle='INDEPENDENT_TYPED_INTERVAL_PYTHON_SOFTFLOAT_NOT_SPIKE_NONZERO_VSTART',source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources()},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [folder/'stimulus.txt.gz',folder/'cases.json.gz',ref_path,*libs]})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS independent arch corpus',sew,ident,'commands',dict(stats),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--sew',type=int,choices=[8,16,32,64],required=True);p.add_argument('--crosscheck-only',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--top',choices=['SpinorStandard','SpinorDeep'],default='SpinorStandard');a=p.parse_args()
    if a.crosscheck_only:crosscheck(a.sew);return
    if a.prepare_only:prepare(a.sew);return
    folder=OUT/'corpus'/f'sew{a.sew}';ref=json.loads((folder/'results.json').read_text())
    for group in ('source_sha256','artifact_sha256'):
        for rel,h in ref[group].items():assert sha(ROOT/rel)==h,rel
    out=OUT/'runs'/f'sew{a.sew}'/a.top;summary,negative,artifacts=run_fixture(a.top,out,folder/'stimulus.txt.gz')
    assert f'commands={ref["commands"]} ' in summary;artifacts[str((folder/'results.json').relative_to(ROOT))]=sha(folder/'results.json')
    d=dict(status='PASS',top=a.top,sew=a.sew,commands=ref['commands'],stats=ref['stats'],summary=summary,trace_replay=False,checked_registers_per_command=32,negative_controls=negative,
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [*sources(),ROOT/'scripts/m58_stream.py',ROOT/'tests/m58_stream_driver.cc']},artifact_sha256=artifacts)
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS arch overlap/restart',a.top,a.sew,ref['commands'],'commands',flush=True)


if __name__=='__main__':main()
