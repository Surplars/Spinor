#!/usr/bin/env python3
"""Cycle measurements on a dependent vadd stream; no FPGA Fmax inference."""
import argparse
import json
from pathlib import Path
import subprocess
from test_vector import HEADER

parser=argparse.ArgumentParser()
parser.add_argument('--ram',action='store_true',help='measure M2 RAM-first engine instead of M1')
args=parser.parse_args()
if args.ram:
    HEADER=HEADER.replace('wire [4:0] io_vl;',
        'wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;')
    HEADER=HEADER.replace('input [4:0] expectedVl','input [7:0] expectedVl')

root=Path(__file__).resolve().parents[1]
out=root/'build/test';out.mkdir(parents=True,exist_ok=True)
tools=root/'tools/oss-cad-suite/bin'
lines=[HEADER]
for r in [0,1,2]:
    for chunk in range(2):lines.append(f"ctx({2*r+chunk},1'b1,64'd0,64'd0);")
for sew in range(4):
    w=8<<sew;vl=128//w;vtype=sew<<3
    ones=sum(1<<(w*i) for i in range(vl))
    result=sum(64<<(w*i) for i in range(vl))
    inst=(vtype<<20)|(7<<12)|(3<<7)|0x57
    lines.append(f"command(32'h{inst:x},0,0,{vl},80'd{sew},0,{vl},1,0,{vl},64'd{vtype});")
    for chunk in range(2):
        lines.append(f"ctx({2+chunk},1'b1,64'd0,64'd0);")
        lines.append(f"ctx({4+chunk},1'b1,64'h{(ones>>(64*chunk))&((1<<64)-1):x},64'd0);")
    lines.append(f"begin: bench{sew} integer start,k;start=cycles;")
    inst=(1<<25)|(1<<20)|(2<<15)|(1<<7)|0x57
    lines.append(f"for(k=0;k<64;k=k+1) command(32'h{inst:x},0,0,0,k,0,0,0,0,{vl},64'd{vtype});")
    lines.append(f'$display("BENCH {w} 64 %0d",cycles-start);end')
    for chunk in range(2):lines.append(f"ctx({2+chunk},1'b0,0,64'h{(result>>(64*chunk))&((1<<64)-1):x});")
lines.append('$finish;end endmodule\n')
tb=out/('ram-benchmark_tb.sv' if args.ram else 'benchmark_tb.sv');tb.write_text('\n'.join(lines))
result={}
tops=['RamVector','RamVector16','RamVectorFlops'] if args.ram else ['VectorPrototypeBaseline','VectorPrototype','VectorPrototype16','VectorPrototypeFlops']
for top in tops:
    exe=out/(top+'-benchmark')
    with (out/(top+'-benchmark.compile.log')).open('w') as log:
        subprocess.run([str(tools/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}','-o',str(exe),
                        str(tb),str(root/f'build/rtl/{top}.sv')],stdout=log,stderr=log,check=True)
    run=subprocess.run([str(tools/'vvp'),str(exe)],capture_output=True,text=True)
    (out/(top+'-benchmark.log')).write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError(run.stdout+run.stderr)
    result[top]=[]
    for line in run.stdout.splitlines():
        if line.startswith('BENCH '):
            _,sew,n,ticks=line.split()
            result[top].append(dict(sew=int(sew),instructions=int(n),cycles=int(ticks),
                                    cycles_per_instruction=int(ticks)/int(n)))
(out/('ram-benchmark.json' if args.ram else 'benchmark.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
