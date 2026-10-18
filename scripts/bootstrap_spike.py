#!/usr/bin/env python3
"""Build an unmodified, SHA-pinned upstream Spike plus the transport adapter."""
import hashlib
import json
import os
import platform
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tools/spike'
EVIDENCE=ROOT/'build/spike-model'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert platform.system()=='Linux' and platform.machine()=='x86_64'
    lockfile=ROOT/'third_party/spike-reference.json';lock=json.loads(lockfile.read_text())
    OUT.mkdir(parents=True,exist_ok=True);EVIDENCE.mkdir(parents=True,exist_ok=True)
    def download(spec,path):
        if not path.exists() or sha(path)!=spec['sha256']:
            with urllib.request.urlopen(spec['url'],timeout=60) as r:raw=r.read()
            assert hashlib.sha256(raw).hexdigest()==spec['sha256'],spec['url']
            path.write_bytes(raw)
    archive=OUT/'source.tar.gz';download(lock['source'],archive)
    src=ROOT/lock['source']['source_dir']
    # Verify the extracted files against the original archive, without patches.
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if not member.isfile():continue
            path=OUT/member.name;raw=tar.extractfile(member).read()
            if not path.is_file() or path.read_bytes()!=raw:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                path.chmod(member.mode)
    deps=OUT/'deps';deps.mkdir(exist_ok=True)
    for spec in lock['packages'].values():
        path=deps/spec['file'];download(spec,path)
        subprocess.run(['dpkg-deb','-x',path,deps],check=True)
    env=os.environ.copy();usr=deps/'usr'
    env['PATH']=str(usr/'bin')+':'+env['PATH']
    env['LD_LIBRARY_PATH']=str(usr/'lib/x86_64-linux-gnu')
    env['CPPFLAGS']='-I'+str(usr/'include')
    env['LDFLAGS']='-L'+str(usr/'lib/x86_64-linux-gnu')+' -Wl,-rpath,'+str(usr/'lib/x86_64-linux-gnu')
    env['CFLAGS']='-O1 -g0';env['CXXFLAGS']='-O1 -g0'
    build=OUT/'build';build.mkdir(exist_ok=True)
    if not (build/'Makefile').exists():
        with (build/'configure.log').open('w') as log:
            subprocess.run([src/'configure','--prefix='+str(OUT/'install'),'--with-boost='+str(usr),'--with-boost-libdir='+str(usr/'lib/x86_64-linux-gnu')],cwd=build,env=env,stdout=log,stderr=log,check=True)
    libraries=['libriscv.a','libdisasm.a','libfesvr.a','libsoftfloat.a','libfdt.a']
    with (EVIDENCE/'make.log').open('w') as log:
        subprocess.run(['make','-j4','CFLAGS=-Wno-error','CXXFLAGS=-Wno-error',*libraries],cwd=build,env=env,stdout=log,stderr=log,check=True)
    adapter=ROOT/'tests/spike_adapter.cc';binary=OUT/'spinor-spike'
    command=['g++','-std=c++20','-O1','-g0','-iquote',str(build)]
    for name in ['riscv','fesvr','softfloat']:command+=['-iquote',str(src/name)]
    command += [str(adapter),'-Wl,--start-group',*[str(build/x) for x in libraries],'-Wl,--end-group',
                '-L'+str(usr/'lib/x86_64-linux-gnu'),'-Wl,-rpath,'+str(usr/'lib/x86_64-linux-gnu'),
                '-lboost_regex','-lboost_system','-ldl','-lpthread','-o',str(binary)]
    with (EVIDENCE/'link.log').open('w') as log:subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=log,check=True)
    # Extract only upstream encoding data; all arithmetic comes from Spike.
    make=(src/'riscv/riscv.mk.in').read_text();encoding=(src/'riscv/encoding.h').read_text()
    groups={}
    for group in ['v_alu_int','v_alu_fp','v_ctrl']:
        block=re.search(r'riscv_insn_ext_'+group+r'\s*=\s*\\\n(.*?)(?=\n\w+\s*[:?+]?=)',make,re.S)
        names=re.findall(r'^\s*(\w+)\s*\\?$',block.group(1),re.M)
        groups[group]=[dict(name=n,match=int(re.search(r'^#define MATCH_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16),
                           mask=int(re.search(r'^#define MASK_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16)) for n in names]
    catalog=EVIDENCE/'catalog.json';catalog.write_text(json.dumps(groups,indent=2)+'\n')
    sources={str(p.relative_to(ROOT)):sha(p) for p in sorted(src.rglob('*')) if p.is_file()}
    result=dict(status='PASS',repository=lock['repository'],revision=lock['source']['revision'],isa=lock['isa'],
                vlen=128,elen=64,vstart_alu=False,semantics_modified=False,transport_source_sha256=sha(adapter),
                compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
                model_source_sha256=sources,model_libraries_sha256={str((build/x).relative_to(ROOT)):sha(build/x) for x in libraries},
                binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),link_command=command,
                sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),lockfile,adapter,catalog]})
    (EVIDENCE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS unmodified Spike',result['revision'],'catalog',sum(map(len,groups.values())),'encodings',flush=True)

if __name__=='__main__':main()
