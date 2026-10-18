#!/usr/bin/env python3
"""Spike checks for FP scalar selection: unboxed operands, bit copies and flags."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from test_spike_differential import catalog,run_model
from test_compiled_programs import ROOT,BIN,pins

p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');a=p.parse_args()
out=ROOT/'build/spike-fp-select'/('mapped' if a.mapped else 'rtl');out.mkdir(parents=True,exist_ok=True)
tables,model=catalog();entries={x['name']:x for x in tables['v_alu_fp']};events=[]
for r in range(32):events.append(dict(kind='R',register=r,data=0))
def instruction(name,raw,scalar=0,avl=0):
    events.append(dict(kind='I',id=sum(e['kind']=='I' for e in events),name=name,instruction=raw,scalar=scalar,avl=avl,scalar2=0))
def csr(address,value):instruction('csr',address<<20|1<<15|1<<12|3<<7|0x73,value)
for sew in [32,64]:
    s=2 if sew==32 else 3;maximum=128//sew
    for length in [0,1,maximum]:
        instruction('vsetvli',(s<<3)<<20|1<<15|7<<12|3<<7|0x57,avl=length)
        csr(2,4);csr(1,8)
        for r in range(1,32):events.append(dict(kind='R',register=r,data=(0xfedcba98765432100123456789abcdef^r)))
        for mask in [0,(1<<128)-1,int('a596'*8,16)]:
            events.append(dict(kind='R',register=0,data=mask))
            scalars=[0xffffffff7f800001,0xffffffff00000000,0x123456783f800000,0x00000000bf800001] if sew==32 else [0x7ff0000000000001,0x7ff8123456789abc,0x8000000000000000,0x3ff0000000000001]
            for index,scalar in enumerate(scalars):
                for merge in [False,True]:
                    entry=entries['vfmerge_vfm' if merge else 'vfmv_v_f'];freg=0 if index%2==0 else 31
                    vd=(16 if index%2 else 8) if merge else (0 if index==2 else 8)
                    fields=(16 if merge else 0)<<20|freg<<15|vd<<7
                    instruction(entry['name'],entry['match']|fields&~entry['mask'],scalar)
states=run_model(events,out,model)
assert all(not s['illegal'] and s['frm']==4 and s['fflags']==8 for e,s in zip((e for e in events if e['kind']=='I'),states) if e['name'] in entries)
(out/'inputs.json').write_text(json.dumps(events,indent=2)+'\n');(out/'expected.json').write_text(json.dumps(states,indent=2)+'\n')
body=[]
for e in events:
    if e['kind']=='R':
        for chunk in range(2):body.append(f"ctx_access({2*e['register']+chunk},1,64'h{e['data']>>(64*chunk)&((1<<64)-1):x});")
        continue
    s=states[e['id']]
    args=[str(e['id']),f"32'h{e['instruction']:x}",f"64'h{e['scalar']:x}",'0',f"64'h{e['avl']:x}",str(s['illegal']),str(s['writes']),f"64'h{s['scalar']:x}",f"8'd{s['vl']}",f"64'h{s['vtype']:x}",f"7'd{s['vstart']}",f"2'd{s['vxrm']}",str(s['vxsat']),f"3'd{s['frm']}",f"5'd{s['fflags']}"]
    body.append('command('+','.join(args)+');')
    for reg,value in enumerate(s['registers']):
        for chunk in range(2):body.append(f"ctx_access({2*reg+chunk},0,64'h{value>>(64*chunk)&((1<<64)-1):x});")
rtl=ROOT/('build/synth/SpinorStandard/mapped.v' if a.mapped else 'build/rtl/SpinorStandard.sv');tb=out/'tb.sv';template=ROOT/'tests/spike_differential_tb.sv'
tb.write_text('`define FRM io_core_frm\n`define FLAGS io_core_fflags\n'+template.read_text().replace('// PIN_DECLARATIONS',pins(ROOT/'build/rtl/SpinorStandard.sv','SpinorStandard')).replace('// EVENTS','\n'.join(body)))
files=[tb,rtl];options=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];options=['-s','glbl']
else:
    for mod,instance in [('RamVectorFpMemory','vpu.vpu'),('VectorMemoryEngine','vpu.engine')]:
        src=ROOT/f'build/rtl/verification/assert/{mod}_Verification_Assert.sv';monitor=out/(mod+'-assert.sv')
        monitor.write_text(src.read_text().replace(mod+'.','tb.dut.'+instance+'.'));files.append(monitor);options+=['-s',mod+'_Verification_Assert']
with (out/'compile.log').open('w') as log:subprocess.run([BIN/'iverilog','-g2012','-s','tb',*options,'-DTOP=SpinorStandard','-o',out/'sim',*files],stdout=log,stderr=log,check=True)
with (out/'run.log').open('w') as log:run=subprocess.run([BIN/'vvp',out/'sim'],stdout=log,stderr=log,check=True,timeout=1800)
output=(out/'run.log').read_text();timings=[dict(id=int(f[1]),cycles=int(f[2])) for f in (x.split() for x in output.splitlines() if x.startswith('CMD '))]
assert len(timings)==len(states)
source=[Path(__file__).resolve(),ROOT/'tests/test_spike_differential.py',ROOT/'tests/test_compiled_programs.py',template]
artifacts=[*files,out/'inputs.json',out/'expected.json',out/'spike-input.txt',out/'spike-output.txt',out/'spike-stderr.log',out/'compile.log',out/'run.log']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(status='PASS',mapped=a.mapped,commands=len(states),vector_cases=144,full_registers_per_command=32,valid_frm=4,expected_fflags=8,unboxed_fp32=True,snan_bit_preserved=True,
            timings=timings,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS Spike FP select',len(states),'commands',flush=True)
