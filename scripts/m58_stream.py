"""Bound, compact test transport; never writes expected values from DUT output."""
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_compiled_programs import env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def compile_driver(top):
    folder=ROOT/'build/m58/bin'/top
    folder.mkdir(parents=True,exist_ok=True)
    gdir=ROOT/'build/m55/gsim/rtl'/top
    harness=ROOT/'tests/m58_stream_driver.cc'
    compiler=ROOT/'tools/llvm-program/usr/bin/clang++-19'
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [harness,ROOT/'tests/gsim_spike_driver.cc',compiler,gdir/(top+'.h'),*sorted(gdir.glob(top+'[0-9]*.cpp'))]}
    binary=folder/'run';record=folder/'build.json'
    old=json.loads(record.read_text()) if record.exists() else {}
    if old.get('inputs')!=inputs or not binary.is_file() or sha(binary)!=old.get('binary_sha256'):
        cmd=[compiler,'-std=c++20','-O2','-DENABLE_FP=1','-DDUT_CLASS=S'+top,'-DDUT_HEADER="'+top+'.h"','-I'+str(gdir),*sorted(gdir.glob(top+'[0-9]*.cpp')),harness,'-ldl','-o',binary]
        with (folder/'compile.log').open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True,timeout=300)
        record.write_text(json.dumps(dict(status='PASS',inputs=inputs,binary_sha256=sha(binary)),indent=2)+'\n')
    return binary,record


def run_fixture(top,folder,fixture,memory=False):
    folder.mkdir(parents=True,exist_ok=True)
    binary,build=compile_driver(top)
    def execute(mode,name):
        # Stream the losslessly compressed independent expectation, not a trace.
        with (folder/name).open('w') as log:
            p=subprocess.Popen([str(binary),'-',str(folder/'scratch-rf.hex'),*([mode] if mode else [])],cwd=ROOT,env=env(),stdin=subprocess.PIPE,stdout=log,stderr=log)
            try:
                with gzip.open(fixture,'rb') as source:
                    while block:=source.read(65536):
                        try:p.stdin.write(block)
                        except BrokenPipeError:break
                try:p.stdin.close()
                except BrokenPipeError:pass
                return p.wait(timeout=240)
            except BaseException:
                p.kill();p.wait();raise
    assert execute(None,'run.log')==0,(folder/'run.log').read_text()[-2000:]
    summary=next(l for l in (folder/'run.log').read_text().splitlines() if l.startswith('PASS stream public DUT'))
    if not memory:assert 'requests=0 responses=0' in summary
    negatives={}
    modes=[('wrong-token','completion token mismatch'),('wrong-rf','RF mismatch'),('wrong-csr','CSR mismatch')]
    if memory:modes.extend([('corrupt-load','RF mismatch'),('wrong-ram','RAM mismatch'),('wrong-tval','memory fault address mismatch')])
    for mode,diagnostic in modes:
        assert execute(mode,mode+'.log')==1
        assert diagnostic in (folder/(mode+'.log')).read_text(),mode
        negatives[mode]='REJECTED'
    (folder/'scratch-rf.hex').unlink(missing_ok=True)
    artifacts={str(p.relative_to(ROOT)):sha(p) for p in [fixture,binary,build,*sorted(folder.glob('*.log'))]}
    return summary,negatives,artifacts
