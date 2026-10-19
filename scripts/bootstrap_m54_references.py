#!/usr/bin/env python3
"""Separate half-enabled Spike transport and pinned SoftFloat wrapper."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'build/m54/reference';out.mkdir(parents=True,exist_ok=True)
    old=json.loads((ROOT/'build/spike-model/results.json').read_text())
    for rel,h in old['model_libraries_sha256'].items():assert sha(ROOT/rel)==h,rel
    adapter=ROOT/'tests/spike_half_adapter.cc';binary=out/'spike-half'
    cmd=[str(x) for x in old['link_command']];cmd[cmd.index(str(ROOT/'tests/spike_adapter.cc'))]=str(adapter);cmd[-1]=str(binary)
    with (out/'spike-link.log').open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=f,check=True)
    soft=ROOT/'tools/fp/softfloat';lib=soft/'build/Linux-x86_64-GCC/softfloat.a'
    wrapper=ROOT/'tests/fp16_reference.c';shared=out/'libhalf.so'
    with (out/'softfloat-link.log').open('w') as f:subprocess.run(['gcc','-std=c11','-O2','-fPIC','-shared','-I'+str(soft/'source/include'),wrapper,lib,'-o',shared],cwd=ROOT,stdout=f,stderr=f,check=True)
    result=dict(status='PASS',isa='rv64gcv_zvfhmin_zvl128b',semantics_modified=False,revision=old['revision'],
        binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),link_command=cmd,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),adapter,wrapper]},
        artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary,shared,out/'spike-link.log',out/'softfloat-link.log',lib,ROOT/'build/spike-model/results.json']})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS separate Spike Zvfhmin and SoftFloat half models')
if __name__=='__main__':main()
