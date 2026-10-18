#!/usr/bin/env python3
"""Raw-encoding, whole-register/CSR differential against unmodified upstream Spike."""
import argparse
import hashlib
import json
import random
import subprocess
from pathlib import Path
from test_compiled_programs import ROOT,BIN,pins

OUT=ROOT/'build/spike-differential'
M64=(1<<64)-1
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def catalog():
    model=json.loads((ROOT/'build/spike-model/results.json').read_text())
    assert model['status']=='PASS' and not model['semantics_modified']
    for p,h in model['sha256'].items():assert sha(ROOT/p)==h,p
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    return json.loads((ROOT/'build/spike-model/catalog.json').read_text()),model


def encoded(entry,vm=1):
    name=entry['name'];form=(entry['match']>>12)&7
    scalar_form=form in [4,5,6]
    vs1=31 if name.endswith(('_vi','_wi','_vim')) else 1 if scalar_form else 24
    fields=(vm<<25)|(16<<20)|(vs1<<15)|(8<<7)
    return entry['match'] | fields & ~entry['mask']


def events_for(entries,compact=False,probe=False):
    rng=random.Random(0x50ab12864);events=[dict(kind='R',register=r,data=0) for r in range(32)];ident=0
    def instruction(name,raw,scalar=0,scalar2=0,avl=0,**metadata):
        nonlocal ident
        events.append(dict(kind='I',id=ident,name=name,instruction=raw,scalar=scalar&M64,scalar2=scalar2&M64,avl=avl&M64,**metadata));ident+=1
    def csr(address,value):instruction('csr',address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,address=address)
    # Deterministic undisturbed policy permits complete RF comparison. Do not
    # mask architectural bits merely because another implementation may vary.
    types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
    if compact:types=[(s,0) for s in range(4)]
    if probe:types=[(2,0)]
    for block,(s,m) in enumerate(types):
        typ=s<<3|m
        instruction('vsetvli',typ<<20|1<<15|7<<12|3<<7|0x57,avl=128 if not compact else 2,vtype_requested=typ)
        for address,value in [(0xf,2*(block%4)),(3,(block%5)<<5)]:csr(address,value)
        for reg in range(32):
            bits=8<<s;mask=(1<<bits)-1
            values=[0,1,mask,1<<(bits-1),(1<<(bits-1))-1,rng.getrandbits(bits)]
            data=sum(values[(reg+i)%len(values)]<<(bits*i) for i in range(128//bits))
            if reg==0:data=int('a596'*8,16)
            events.append(dict(kind='R',register=reg,data=data))
        for index,entry in enumerate(entries):
            name=entry['name']
            if probe and index>=40:break
            floating=((entry['match']>>12)&7) in [1,5]
            if floating:
                csr(1,0)
            if name.startswith(('vsadd','vssub','vsmul','vnclip')):csr(9,0)
            scalar=[M64,0,1<<63,1,0x80000001][index%5]
            if floating:
                scalar=0xffffffff3f800001 if s==2 else 0xbff0000000000001
            instruction(name,encoded(entry,vm=(index+block)%2),scalar=scalar,sew=8<<s,lmul=m,category='floating' if floating else 'integer')
        # Configuration and read-only CSR results are independently executed.
        for address in [0x008,0x009,0x00a,0x00f,0xc20,0xc21,0xc22]:
            instruction('csr-read',address<<20|2<<12|3<<7|0x73,address=address)
    # VSET immediate/register, x0 AVL rules, preserved VLMAX and CSR zero sources.
    for s in range(4):
        typ=s<<3
        instruction('vsetivli',3<<30|typ<<20|31<<15|7<<12|3<<7|0x57)
        instruction('vsetvl',0x40<<25|2<<20|1<<15|7<<12|3<<7|0x57,avl=3,scalar2=typ)
        instruction('vsetvli',typ<<20|7<<12|3<<7|0x57)
        instruction('vsetvli',typ<<20|7<<12|0x57)
    instruction('vsetvli',0x20<<20|1<<15|7<<12|3<<7|0x57,avl=3)
    instruction('vill-vadd',1<<25|16<<20|24<<15|8<<7|0x57)
    instruction('vsetvli',0x10<<20|1<<15|7<<12|3<<7|0x57,avl=4)
    for address,value in [(8,127),(0xf,7),(3,0x8f)]:csr(address,value)
    for address in [8,9,10,15,1,2,3,0xc20,0xc21,0xc22]:
        for action in [2,3]:instruction('csr-zero-source',address<<20|action<<12|3<<7|0x73,scalar=M64,address=address)
    for address in [0xc20,0xc21,0xc22]:instruction('csr-readonly-write',address<<20|1<<15|1<<12|3<<7|0x73,scalar=1,address=address)
    csr(8,0);csr(3,0)
    return events


def run_model(events,folder,model):
    input_path=folder/'spike-input.txt';output_path=folder/'spike-output.txt'
    lines=[]
    for event in events:
        if event['kind']=='R':lines.append(f'R {event["register"]} {event["data"]:032x}')
        else:lines.append('I '+ ' '.join(f'{event[k]:x}' for k in ['instruction','scalar','scalar2','avl']))
    input_path.write_text('\n'.join(lines)+'\n')
    with input_path.open() as input_file,output_path.open('w') as output,(folder/'spike-stderr.log').open('w') as err:
        subprocess.run([ROOT/model['binary']],stdin=input_file,stdout=output,stderr=err,cwd=ROOT,check=True,timeout=120)
    states=[]
    for line in output_path.read_text().splitlines():
        f=line.split();assert f[0]=='S' and len(f)==45,f
        assert int(f[1])==len(states)
        states.append(dict(illegal=int(f[2]),cause=int(f[3]),scalar=int(f[4],16),writes=int(f[5],16),vl=int(f[6],16),
                           vtype=int(f[7],16),vstart=int(f[8],16),vxrm=int(f[9],16),vxsat=int(f[10],16),frm=int(f[11],16),fflags=int(f[12],16),
                           registers=[int(x,16) for x in f[13:]]))
    assert len(states)==sum(e['kind']=='I' for e in events)
    return states


def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'])
    p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--bounded',action='store_true');p.add_argument('--probe',action='store_true');p.add_argument('--model-only',action='store_true');a=p.parse_args()
    tables,model=catalog();fp='Integer' not in a.top
    entries=tables['v_alu_int']+(tables['v_alu_fp'] if fp else [])
    if a.bounded:
        wanted={'vadd_vv','vsub_vx','vaadd_vv','vadc_vvm','vmadc_vim','vcompress_vm','vcpop_m','vfirst_m','viota_m','vid_v',
                'vdiv_vv','vmacc_vx','vmulh_vv','vnclip_wi','vnclipu_wv','vnsra_wx','vwmaccsu_vv','vwmaccus_vx',
                'vmsbf_m','vmsif_m','vmsof_m','vmv_s_x','vmv_x_s','vmv8r_v','vrgather_vv','vrgatherei16_vv','vslideup_vi','vslide1down_vx',
                'vredsum_vs','vwredsum_vs','vsadd_vx','vsmul_vv','vssra_vi','vzext_vf8',
                'vfmerge_vfm','vfmv_v_f','vfmv_f_s','vfmv_s_f','vfslide1up_vf','vfslide1down_vf','vfadd_vv','vfdiv_vf','vfmacc_vv',
                'vfclass_v','vfcvt_x_f_v','vfwcvt_f_x_v','vfncvt_rod_f_f_w','vfrec7_v','vfrsqrt7_v','vfwadd_wv','vfwmacc_vf','vfredosum_vs','vfwredosum_vs'}
        entries=[e for e in entries if e['name'] in wanted]
    events=events_for(entries,a.compact,a.probe)
    # Integer presets have no FP CSRs; keep the reference FP state at reset zero.
    if not fp:
        events=[e for e in events if not(e['kind']=='I' and e.get('address') in [1,2,3])]
        for i,e in enumerate(e for e in events if e['kind']=='I'):e['id']=i
    label=a.top+('-probe' if a.probe else '-bounded' if a.bounded else '-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl')
    folder=OUT/label;folder.mkdir(parents=True,exist_ok=True)
    states=run_model(events,folder,model)
    (folder/'inputs.json').write_text(json.dumps(events,indent=2)+'\n');(folder/'expected.json').write_text(json.dumps(states,indent=2)+'\n')
    if a.model_only:print(label,'model commands',len(states));return
    production=ROOT/f'build/rtl/{a.top}.sv';body=[]
    for event in events:
        if event['kind']=='R':
            for chunk in range(2):body.append(f"ctx_access({event['register']*2+chunk},1,64'h{event['data']>>(64*chunk)&M64:x});")
            continue
        state=states[event['id']];args=[str(event['id'])]+[f"32'h{event['instruction']:x}"]+[f"64'h{event[k]:x}" for k in ['scalar','scalar2','avl']]
        args += [str(state['illegal']),str(state['writes']),f"64'h{state['scalar']:x}"]
        args += [f"8'd{state['vl']}",f"64'h{state['vtype']:x}",f"7'd{state['vstart']}",f"2'd{state['vxrm']}",str(state['vxsat']),f"3'd{state['frm']}",f"5'd{state['fflags']}"]
        body.append('command('+','.join(args)+');')
        for reg,data in enumerate(state['registers']):
            for chunk in range(2):body.append(f"ctx_access({reg*2+chunk},0,64'h{data>>(64*chunk)&M64:x});")
    tb=folder/'tb.sv';template=ROOT/'tests/spike_differential_tb.sv'
    text=template.read_text().replace('// PIN_DECLARATIONS',pins(production,a.top)).replace('// EVENTS','\n'.join(body))
    text='`define FRM '+('io_core_frm' if fp else "3'd0")+'\n`define FLAGS '+('io_core_fflags' if fp else "5'd0")+'\n'+text
    tb.write_text(text);netlist=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv')
    files=[tb,netlist];options=[];assertion_sources=[]
    if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];options=['-s','glbl']
    else:
        module='RamVector'+('Fp' if fp else 'Integer')+'Memory'+('16' if 'Deep' in a.top else '')
        for mod,instance in [(module,'vpu.vpu'),('VectorMemoryEngine','vpu.engine')]:
            source=ROOT/f'build/rtl/verification/assert/{mod}_Verification_Assert.sv';monitor=folder/(mod+'-assert.sv')
            monitor.write_text(source.read_text().replace(mod+'.','tb.dut.'+instance+'.'));files.append(monitor);assertion_sources.append(source);options+=['-s',mod+'_Verification_Assert']
    with (folder/'compile.log').open('w') as log:
        subprocess.run([BIN/'iverilog','-g2012','-s','tb',*options,'-DTOP='+a.top,'-o',folder/'sim',*files],stdout=log,stderr=log,check=True,cwd=ROOT)
    with (folder/'run.log').open('w') as log:
        result=subprocess.run([BIN/'vvp',folder/'sim'],stdout=log,stderr=log,cwd=ROOT,timeout=3600)
    output=(folder/'run.log').read_text();assert result.returncode==0,output[-3500:]
    timings=[dict(id=int(f[1]),cycles=int(f[2])) for f in (line.split() for line in output.splitlines() if line.startswith('CMD '))]
    assert len(timings)==len(states)
    legal={};illegal={}
    for e in events:
        if e['kind']!='I' or e['name'] in ['csr','csr-read','vsetvli']:continue
        target=illegal if states[e['id']]['illegal'] else legal;target[e['name']]=target.get(e['name'],0)+1
    source_files=[Path(__file__).resolve(),template,ROOT/'tests/test_compiled_programs.py',ROOT/'tests/spike_adapter.cc',ROOT/'third_party/spike-reference.json']
    artifacts=[*files,*assertion_sources,folder/'inputs.json',folder/'expected.json',folder/'spike-input.txt',folder/'spike-output.txt',folder/'spike-stderr.log',folder/'compile.log',folder/'run.log',ROOT/'build/spike-model/results.json',ROOT/'build/spike-model/catalog.json']
    d=dict(status='PASS',top=a.top,compact=a.compact,mapped=a.mapped,bounded=a.bounded,probe=a.probe,commands=len(states),vector_encodings=len(entries),legal_encodings=legal,illegal_encodings=illegal,
           compared_registers_per_command=32,compared_csrs=['vl','vtype','vstart','vxrm','vxsat']+(['frm','fflags'] if fp else []),vstart_alu=False,
           memory_instructions=False,independent_isa_model='SPIKE',revision=model['revision'],semantics_modified=False,timings=timings,
           summary=next(x for x in output.splitlines() if x.startswith('PASS Spike')),
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source_files},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(label,d['summary'],len(legal),'encodings legally exercised',flush=True)

if __name__=='__main__':main()
