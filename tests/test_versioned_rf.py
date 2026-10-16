#!/usr/bin/env python3
"""Independent two-version/byte-write/atomic-map model, including commit+read."""
from pathlib import Path
import json
import random
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin'
rng=random.Random(0x2e15)
memory=[[0]*32 for _ in range(2)];versions=0
rows=[];expected=[]

def step(re,ra,rc,we,wa,wc,mask,data,commit,cmask):
    global versions
    rp=((versions>>ra)&1)^rc
    wp=((versions>>wa)&1)^wc
    assert not(re and we and ra==wa and rp==wp),'collision is outside the hardware contract'
    read=memory[rp][ra] if re else None
    if we:
        for b in range(16):
            if mask>>b&1:
                memory[wp][wa]=(memory[wp][wa]&~(255<<(8*b)))|(data&(255<<(8*b)))
    if commit:versions^=cmask
    rows.append((re,ra,rc,we,wa,wc,mask,data,commit,cmask));expected.append((read,versions))

for candidate in range(2):
    for address in range(32):step(0,0,0,1,address,candidate,0xffff,rng.getrandbits(128),0,0)
for i in range(4096):
    ra=rng.randrange(32);wa=rng.randrange(32);rc=rng.randrange(2);wc=rng.randrange(2)
    re=int(rng.random()<.8);we=int(rng.random()<.7)
    if ra==wa and rc==wc:we=0
    step(re,ra,rc,we,wa,wc,rng.getrandbits(16),rng.getrandbits(128),int(rng.random()<.15),rng.getrandbits(32))
(OUT/'versioned-rf.stim').write_text(''.join(
    f'{re} {ra} {rc} {we} {wa} {wc} {mask:x} {data:x} {commit} {cmask:x}\n'
    for re,ra,rc,we,wa,wc,mask,data,commit,cmask in rows))
exe=OUT/'VersionedRegisterFileRam'
with (OUT/'versioned-rf.compile.log').open('w') as log:
    subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb','-o',str(exe),
                    str(ROOT/'tests/versioned_rf_tb.sv'),str(ROOT/'build/rtl/VersionedRegisterFileRam.sv')],
                   stdout=log,stderr=log,check=True)
run=subprocess.run([str(BIN/'vvp'),str(exe)],cwd=ROOT,check=True,capture_output=True,text=True)
(OUT/'versioned-rf.trace').write_text(run.stdout)
trace=[s.split() for s in run.stdout.splitlines() if s.startswith('R ')]
assert len(trace)==len(expected)
for i,(_,index,data,versions) in enumerate(trace):
    value,mapping=expected[i]
    assert int(index)==i
    assert int(versions,16)==mapping,(i,'version map')
    if value is not None:assert int(data,16)==value,(i,'read data',data,f'{value:x}')
result={'transactions':len(rows),'reads_checked':sum(v is not None for v,_ in expected),
        'random_atomic_commits':sum(r[8] for r in rows),'status':'PASS'}
(OUT/'versioned-rf.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
