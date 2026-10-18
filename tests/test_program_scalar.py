#!/usr/bin/env python3
"""Check the actual shared SV scalar adapter's signed operations and edge cases."""
import hashlib
import json
import subprocess
from pathlib import Path
from test_compiled_programs import ROOT,BIN,pins,signed,MASK64

OUT=ROOT/'build/program-scalar'
OUT.mkdir(parents=True,exist_ok=True)
lines=[];cases=[]

def case(instruction,a,b,expected):
    ident=len(cases)
    lines.extend(['caseStart=cycles;reset=1;tick();tick();reset=0;tick();',
                  'for(j=0;j<32;j=j+1)x[j]=0;',
                  f"x[1]=64'hfffffff0;x[10]=64'h{a&MASK64:x};x[11]=64'h{b&MASK64:x};"])
    for i,byte in enumerate(instruction.to_bytes(4,'little')+(0x00008067).to_bytes(4,'little')):
        lines.append(f"mem[{i}]=8'h{byte:x};")
    lines.append(f"caseid={ident};execute(BASE);if(x[10]!==64'h{expected&MASK64:x})$fatal(1,\"scalar signed case {ident} got=%h\",x[10]);")
    cases.append(dict(instruction=f'{instruction:08x}',a=a&MASK64,b=b&MASK64,expected=expected&MASK64))

for bits in [32,64]:
    for a in [-(1<<(bits-1)),-16,-1,0,1,(1<<(bits-1))-1]:
        for shift in ([0,1,3,31] if bits==32 else [0,1,3,31,32,63]):
            regop=59 if bits==32 else 51;immop=27 if bits==32 else 19
            case((32<<25)|(11<<20)|(10<<15)|(5<<12)|(10<<7)|regop,a,shift,a>>shift)
            case((32<<25)|(shift<<20)|(10<<15)|(5<<12)|(10<<7)|immop,a,0,a>>shift)
        for b in [-(1<<(bits-1)),-3,-1,0,1,3]:
            q=(-1 if (a<0)!=(b<0) else 1)*(abs(a)//abs(b)) if b else -1
            r=a-q*b if b else a
            if a==-(1<<(bits-1)) and b==-1:q=a;r=0
            for f3,value in [(4,q),(6,r)]:
                expected=signed(value&((1<<bits)-1),bits)&MASK64
                case((1<<25)|(11<<20)|(10<<15)|(f3<<12)|(10<<7)|(59 if bits==32 else 51),a,b,expected)

rtl=ROOT/'build/rtl/SpinorInteger.sv';template=ROOT/'tests/program_runner.sv'
tb=OUT/'tb.sv'
tb.write_text(template.read_text().replace('// PIN_DECLARATIONS',pins(rtl,'SpinorInteger')).replace('// RUN_CASES','\n'.join(lines)).replace('// FP_STATE_CHECK',''))
with (OUT/'compile.log').open('w') as log:
    subprocess.run([BIN/'iverilog','-g2012','-s','tb','-DTOP=SpinorInteger','-o',OUT/'sim',tb,rtl],stdout=log,stderr=log,check=True)
with (OUT/'run.log').open('w') as log:
    run=subprocess.run([BIN/'vvp',OUT/'sim'],cwd=ROOT,stdout=log,stderr=log,timeout=120)
assert run.returncode==0,(OUT/'run.log').read_text()[-3000:]
paths=[Path(__file__).resolve(),template,ROOT/'tests/test_compiled_programs.py',rtl,tb,OUT/'compile.log',OUT/'run.log']
result=dict(status='PASS',cases=len(cases),scope='SHARED_SCALAR_TEST_ADAPTER_SIGNED_SHIFT_DIVIDE_REMAINDER_NOT_CPU_COMPLIANCE',
            case_specs=cases,sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS shared scalar signed adapter:',len(cases),'cases')
