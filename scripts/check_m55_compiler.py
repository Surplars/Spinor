#!/usr/bin/env python3
"""Real strip-mined assembly example; no claim of CPU/program execution.

The pinned Clang19 accepts Zvbb assembly but does not expose these C intrinsic
names. Keep the example explicit instead of supplying invented intrinsics.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_compiled_programs import env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=ROOT/'build/m55/compiler';out.mkdir(parents=True,exist_ok=True)
cc=ROOT/'tools/llvm-program/usr/bin/clang-19';objdump=ROOT/'tools/riscv-program/usr/bin/riscv64-unknown-elf-objdump'
source=ROOT/'software/programs/bit-features.S';obj=out/'bit-features.o';dis=out/'bit-features.dis'
cmd=[cc,'--target=riscv64-unknown-elf','-march=rv64gcv_zvbb','-mabi=lp64d','-c',source,'-o',obj]
with (out/'compile.log').open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True)
with dis.open('w') as f:subprocess.run([objdump,'-d',obj],cwd=ROOT,env=env(),stdout=f,stderr=f,check=True)
# The installed Binutils predates Zvbb mnemonics. Verify actual machine words
# using the independently pinned upstream match/mask catalog, including sizes.
from m55_zvbb_events import catalog
objcopy=ROOT/'tools/riscv-program/usr/bin/riscv64-unknown-elf-objcopy';raw=out/'text.bin'
subprocess.run([objcopy,'-O','binary','--only-section=.text',obj,raw],cwd=ROOT,env=env(),check=True)
code=raw.read_bytes();offset=0;decoded=[];entries=catalog()
while offset<len(code):
    half=int.from_bytes(code[offset:offset+2],'little');size=4 if half&3==3 else 2
    assert offset+size<=len(code)
    word=int.from_bytes(code[offset:offset+size],'little')
    if size==4:
        matches=[e['name'] for e in entries if word&e['mask']==e['match']]
        assert len(matches)<=1
        if matches:decoded.append(dict(offset=offset,word=f'0x{word:08x}',name=matches[0]))
    offset+=size
text=' '.join(e['name'].replace('_','.') for e in decoded)+' '+dis.read_text()
for mnemonic in ['vandn.vx','vbrev8.v','vrev8.v','vbrev.v','vrol.vx','vror.vi','vclz.v','vctz.v','vcpop.v','vwsll.vx']:assert mnemonic in text,mnemonic
encoding=out/'zvbb-encodings.json';encoding.write_text(json.dumps(decoded,indent=2)+'\n')
d=dict(status='PASS',decoded=decoded,scope='LLVM_ASSEMBLE_MACHINE_WORD_CHECK_ONLY_NOT_TARGET_EXECUTION',command=list(map(str,cmd)),
    source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),source,ROOT/'software/programs/bit-features.h',ROOT/'tests/m55_zvbb_events.py']},
    artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [obj,dis,raw,encoding,out/'compile.log',cc,objdump,objcopy,ROOT/'build/m55/reference/results.json']})
(out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS LLVM Zvbb assembly workload')
