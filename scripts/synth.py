#!/usr/bin/env python3
"""OOC UltraScale+ mapping. No device P&R or claimed FPGA Fmax."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'tools/oss-cad-suite/bin'

def run(top):
    out=ROOT/'build/synth'/top
    out.mkdir(parents=True,exist_ok=True)
    sourceTop={'VectorPrototypeBram':'VectorPrototype','RamVectorBram':'RamVector',
               'RamVectorFpNoDsp':'RamVectorFp'}.get(top,top)
    inputs=[ROOT/f'build/rtl/{sourceTop}.sv',Path(__file__).resolve()]
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    setup=''
    if top=='VectorPrototypeBram':
        setup='''rename VectorPrototype VectorPrototypeBram
proc
memory_collect
select -assert-count 1 banks_memory_32x64/t:$mem_v2
setattr -set ram_style "block" banks_memory_32x64/t:$mem_v2
'''
    elif top=='RamVectorBram':
        setup='''rename RamVector RamVectorBram
proc
memory_collect
select -assert-count 1 storage_64x128/t:$mem_v2
setattr -set ram_style "block" storage_64x128/t:$mem_v2
'''
    elif top=='RamVectorFpNoDsp':
        setup='rename RamVectorFp RamVectorFpNoDsp\n'
    extra=' -nodsp' if top.endswith('NoDsp') else ''
    script=f'''read_verilog -sv {ROOT}/build/rtl/{sourceTop}.sv
{setup}
synth_xilinx -family xcup -top {top} -flatten -noiopad -noclkbuf -nosrl -nowidelut{extra}
tee -o {out}/stat.json stat -json
check -assert
write_json {out}/mapped.json
write_verilog -noattr {out}/mapped.v
'''
    (out/'synth.ys').write_text(script)
    start=time.monotonic()
    with (out/'synth.log').open('w') as log:
        subprocess.run([str(BIN/'yosys'),'-T','-s',str(out/'synth.ys')],stdout=log,stderr=subprocess.STDOUT,check=True)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in source_hashes.items()),'synthesis input changed during run'
    stat=json.loads((out/'stat.json').read_text())
    module=stat['modules']['\\'+top]
    summary={'input_sha256':source_hashes,'netlist_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/'mapped.json',out/'mapped.v']},'top':top,'elapsed_seconds':round(time.monotonic()-start,2),
             'mapped_cells':module['num_cells_by_type'],'scope':'out-of-context mapping, no IOB/clock buffers',
             'family':'xcup','target_device':'xczu15eg-ffvb1156-2-i',
             'vrf_mapping':'forced block RAM' if top.endswith('Bram') else 'automatic',
             'DSP_mapping_disabled':top.endswith('NoDsp'),
             'timing_status':'NO_DEVICE_PLACE_ROUTE_OR_SIGNOFF'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument('tops',nargs='*',default=['IntegerLaneBaseline','IntegerLaneSplit','IntegerLaneSplit16','VectorPrototype','VectorPrototype16','VectorPrototypeFlops','VectorPrototypeBram'])
    a=p.parse_args()
    with ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(run,a.tops))
    (ROOT/'build/synth/summary.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
