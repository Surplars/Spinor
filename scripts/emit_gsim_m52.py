#!/usr/bin/env python3
"""Separate M52 production exports; preserve all frozen M51 tool inputs."""
import argparse,hashlib,json,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    presets=dict(SpinorStandard='standard',SpinorDeep='deep',SpinorInteger='integer',SpinorIntegerDeep='integer-deep')
    folder=ROOT/'build/gsim-direct/rtl'/a.top;folder.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    with (folder/'elaborate.log').open('w') as out:subprocess.run([ROOT/'mill','-i','Vpu.runMain','vpu.GenerateGsim',folder,presets[a.top],a.top],cwd=ROOT,stdout=out,stderr=out,check=True)
    elaborate_seconds=time.perf_counter()-start
    raw=folder/(a.top+'.fir');text=raw.read_text();assert not re.search(r'\bgsim_old\b',text)
    # GSIM reserves "old" everywhere, although FIRRTL permits it as a wire
    # name. Alpha-rename that local identifier and all references. Preserve
    # any genuine memory read-under-write OLD attribute verbatim.
    assert re.search(r'\bwire old : UInt<64>',text)
    lines=[];count=0
    for line in text.splitlines(True):
        if not re.match(r'\s*smem\b',line):line,n=re.subn(r'\bold\b','gsim_old',line);count+=n
        lines.append(line)
    normalized=folder/(a.top+'.gsim.fir');normalized.write_text(''.join(lines))
    for old in folder.glob(a.top+'[0-9]*.cpp'):old.unlink()
    start=time.perf_counter()
    with (folder/'generate.log').open('w') as out:subprocess.run([ROOT/'tools/gsim-src/build/gsim/gsim','--threads=1','--dir='+str(folder),normalized],cwd=ROOT,stdout=out,stderr=out,check=True)
    generation_seconds=time.perf_counter()-start
    files=[raw,normalized,folder/(a.top+'.h'),*sorted(folder.glob(a.top+'[0-9]*.cpp'))]
    sources=[Path(__file__).resolve(),ROOT/'src/main/scala/vpu/GenerateGsim.scala',ROOT/'third_party/gsim-reference.json',*sorted((ROOT/'src/main/scala/vpu').glob('*.scala'))]
    result=dict(status='PASS',top=a.top,normalization='ALPHA_RENAME_ONLY',identifier='old',replacement='gsim_old',occurrences=count,elaboration_seconds=elaborate_seconds,generation_seconds=generation_seconds,
      reason='Pinned GSIM lexes old as a RAM read-under-write token',source_sha256={str(x.relative_to(ROOT)):sha(x) for x in sources},artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in files})
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS GSIM production export',a.top,generation_seconds,'generation seconds')
if __name__=='__main__':main()
