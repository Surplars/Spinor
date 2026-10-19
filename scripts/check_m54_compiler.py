#!/usr/bin/env python3
"""Compile a real intrinsic workload; target CPU execution remains separate."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_compiled_programs import env
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out=ROOT/'build/m54/compiler';out.mkdir(parents=True,exist_ok=True)
cc=ROOT/'tools/llvm-program/usr/bin/clang-19';source=ROOT/'software/programs/half-conversions.c';asm=out/'half-conversions.s'
cmd=[cc,'--target=riscv64-unknown-elf','-march=rv64gcv_zvfhmin','-mabi=lp64d','-O2','-ffreestanding','-fno-builtin','-S',source,'-o',asm]
with (out/'compile.log').open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),stdout=f,stderr=f,check=True)
text=asm.read_text();assert 'vfwcvt.f.f.v' in text and 'vfncvt.f.f.w' in text and 'vle16.v' in text and 'vse16.v' in text
d=dict(status='PASS',scope='LLVM_INTRINSIC_COMPILE_ONLY_NOT_TARGET_EXECUTION',command=list(map(str,cmd)),
       source_sha256={str(x.relative_to(ROOT)):sha(x) for x in [Path(__file__).resolve(),source]},
       artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in [asm,out/'compile.log',cc]})
(out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS LLVM Zvfhmin intrinsic compile')
