#!/usr/bin/env python3
"""Build pinned GSIM with local dependencies; never modifies another repository."""
import hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    lock=json.loads((ROOT/'third_party/gsim-reference.json').read_text())
    source=ROOT/'tools/gsim-src';deps=ROOT/'tools/gsim-deps';deps.mkdir(parents=True,exist_ok=True)
    for spec in lock['dependencies']:
        path=deps/spec['file']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:
            path.write_bytes(urllib.request.urlopen(spec['url'],timeout=60).read())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==spec['sha256']
        subprocess.run(['dpkg-deb','-x',str(path),str(deps)],check=True)
    if not source.exists():
        subprocess.run(['git','clone','--no-checkout','--filter=blob:none',lock['repository'],str(source)],check=True)
        subprocess.run(['git','checkout','--detach',lock['revision']],cwd=source,check=True)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==lock['revision']
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source,text=True).strip()
    env=os.environ.copy();env['PATH']=str(deps/'usr/bin')+':'+env['PATH']
    env['CPATH']=str(deps/'usr/include')+':'+env.get('CPATH','')
    env['M4']=str(deps/'usr/bin/m4');env['BISON_PKGDATADIR']=str(deps/'usr/share/bison')
    libs=ROOT/'tools/llvm-program/usr/lib/x86_64-linux-gnu'
    env['LD_LIBRARY_PATH']=str(libs)+':'+env.get('LD_LIBRARY_PATH','')
    cxx=ROOT/'tools/llvm-program/usr/bin/clang++-19'
    log=ROOT/'build/gsim-tool-build.log';log.parent.mkdir(exist_ok=True)
    with log.open('w') as stream:subprocess.run(['make','-j4','CXX='+str(cxx),'build-gsim'],cwd=source,env=env,stdout=stream,stderr=stream,check=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    version=subprocess.check_output([cxx,'--version'],text=True,env=env).splitlines()[0]
    assert '19.1.7' in version
    tracked=subprocess.check_output(['git','ls-files'],cwd=source,text=True).splitlines()
    binary=source/'build/gsim/gsim';out=ROOT/'build/gsim-model';out.mkdir(exist_ok=True)
    result=dict(status='PASS',revision=lock['revision'],semantics_modified=False,compiler=version,binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),compiler_binary_sha256=sha(cxx),
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'third_party/gsim-reference.json',ROOT/'software/programs/toolchain.lock.json']},
      external_source_sha256={str((source/rel).relative_to(ROOT)):sha(source/rel) for rel in tracked if (source/rel).is_file()},unused_submodules=[rel for rel in tracked if not (source/rel).is_file()])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS pinned GSIM built',lock['revision'])
if __name__=='__main__':main()
