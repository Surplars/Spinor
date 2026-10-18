#!/usr/bin/env python3
"""Compile the scalar context library for both possible hosts, no target runtime."""
import hashlib,json,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_compiled_programs import env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def undefined_symbols(path):
    raw=path.read_bytes();assert raw[:6]==b'\x7fELF\x02\x01'
    h=struct.unpack_from('<HHIQQQIHHHHHH',raw,16);sections=[struct.unpack_from('<IIQQQQIIQQ',raw,h[5]+i*h[10]) for i in range(h[11])];undefined=[]
    for s in sections:
        if s[1]!=2:continue
        strings=sections[s[6]];names=raw[strings[4]:strings[4]+strings[5]]
        for off in range(s[4],s[4]+s[5],s[9]):
            name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',raw,off)
            if name and index==0:undefined.append(names[name:names.index(0,name)].decode())
    return h[1],undefined

def main():
    out=ROOT/'build/context-cross';out.mkdir(exist_ok=True);cc=ROOT/'tools/llvm-program/usr/bin/clang-19';source=ROOT/'software/context/spinor_context.c'
    targets={'riscv64':(['--target=riscv64-unknown-elf','-march=rv64imac','-mabi=lp64'],243),'aarch64':(['--target=aarch64-none-elf','-march=armv8-a','-mgeneral-regs-only'],183)}
    results={};artifacts=[]
    for name,(flags,machine) in targets.items():
        obj=out/(name+'.o');log=out/(name+'.log')
        command=[str(cc),*flags,'-std=c11','-O2','-ffreestanding','-fno-builtin','-fno-vectorize','-fno-slp-vectorize','-Wall','-Wextra','-Werror','-pedantic','-c',str(source),'-o',str(obj)]
        with log.open('w') as f:subprocess.run(command,cwd=ROOT,env=env(),stdout=f,stderr=f,check=True)
        actual,undefined=undefined_symbols(obj);assert actual==machine and not undefined,(name,actual,undefined)
        results[name]=dict(command=command,machine=machine,undefined_symbols=undefined,size=obj.stat().st_size);artifacts += [obj,log]
    files=[Path(__file__).resolve(),source,ROOT/'software/context/spinor_context.h',ROOT/'tests/test_compiled_programs.py']
    result=dict(status='PASS',scope='FREESTANDING_COMPILE_ONLY_NOT_TARGET_EXECUTION',targets=results,compiler_sha256=sha(cc),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS context cross compile: RV64IMAC/LP64 and AArch64 general registers; zero runtime symbols')
if __name__=='__main__':main()
