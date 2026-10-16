#!/usr/bin/env python3
"""Compile UIO client, exercise stable snapshot decode against a file fixture.
This tests userspace decoding, not Linux UIO discovery or real MMIO ordering.
"""
import hashlib,json,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/monitor/software';OUT.mkdir(parents=True,exist_ok=True)
exe=OUT/'lishi-monitor';src=ROOT/'software/monitor/lishi_monitor.c'
subprocess.run(['gcc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],check=True)
page=bytearray(4096)
def put(off,val):struct.pack_into('<Q',page,off,val)
put(0,0x4c495348);put(8,0x10000);put(16,0x18);put(24,0x3f)
put(0x20,(1<<48)|(32<<32)|(64<<16)|128);put(0x28,(8<<32)|512);put(0x30,32)
put(0x38,0x30);put(0x48,7);put(0x180,0xad);put(0x188,0x8000000000000000)
put(0x190,0x123456);put(0x198,0x12345);put(0x1a0,0x80000008);put(0x1a8,0xfedcba9876543210);put(0x1b0,0xabcd)
values=[(0xffffffff-123*i)&0xffffffff for i in range(13)]
for i,x in enumerate(values):put(0x100+8*i,x)
fixture=OUT/'mmio.bin';fixture.write_bytes(page)
run=subprocess.run([str(exe),'--read-snapshot',str(fixture)],capture_output=True,text=True,check=True)
d=json.loads(run.stdout)
assert (d['vlen'],d['elen'],d['vector_registers'],d['instruction_capacity'],d['architectural_vrf_bytes'])==(128,64,32,1,512)
assert list(d['counters'].values())==values
assert d['vtype']==0x8000000000000000 and d['error_token_lo']==0xfedcba9876543210 and d['error_token_hi']==0xabcd
assert fixture.read_bytes()==page
negative=[]
for label,offset,value,existing in [('abi',8,0x20000,True),('no_snapshot',0x38,0,True),('no_ack',0x38,0x30,False)]:
 altered=bytearray(page);struct.pack_into('<Q',altered,offset,value);fixture.write_bytes(altered)
 bad=subprocess.run([str(exe),*(['--read-snapshot'] if existing else []),str(fixture)],capture_output=True,text=True)
 assert bad.returncode!=0,label;negative.append(label)
(OUT/'decoded.json').write_text(json.dumps(d,indent=2)+'\n')
r=dict(status='PASS',scope='HOST_FILE_FIXTURE_NOT_REAL_KERNEL_UIO_OR_ARM_MMIO',negative_controls=negative,
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [src,ROOT/'software/monitor/lishi_monitor.h',Path(__file__).resolve()]})
(OUT/'results.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
