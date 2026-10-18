#!/usr/bin/env python3
"""Independent upstream Spike LSU differential through the production TL port."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_compiled_programs import ROOT,BIN,pins
OUT=ROOT/'build/spike-memory';BASE=0x80010000;N=8192;M64=(1<<64)-1
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
RAM=r'''
reg [7:0] mem[0:8191],expectedMem[0:8191];reg [63:0] expectedRf[0:63];
reg pending=0;integer waits=0,requests=0,responses=0,j,beat;reg [63:0] pa,pdata;reg [7:0] pmask;reg [2:0] psz,pop;reg denied;
reg [63:0] faultAddress=0,faultLength=0;
assign io_tl_a_ready=!pending && !io_tl_d_valid && cycles%3!=1;
always @(posedge clock)if(!reset)begin
 if(io_tl_a_valid && io_tl_a_ready)begin
  if(pending || io_tl_a_bits_source!==0 || io_tl_a_bits_param!==0 || io_tl_a_bits_corrupt || io_tl_a_bits_size>3 ||
   (io_tl_a_bits_opcode!==0 && io_tl_a_bits_opcode!==4) || (io_tl_a_bits_address & ((1<<io_tl_a_bits_size)-1)) ||
   io_tl_a_bits_mask!==(((1<<(1<<io_tl_a_bits_size))-1)<<(io_tl_a_bits_address&7)))$fatal(1,"invalid TileLink A");
  pa<=io_tl_a_bits_address;pdata<=io_tl_a_bits_data;pmask<=io_tl_a_bits_mask;psz<=io_tl_a_bits_size;pop<=io_tl_a_bits_opcode;
  denied<=io_tl_a_bits_address<64'h80010000 || io_tl_a_bits_address+(1<<io_tl_a_bits_size)>64'h80012000 ||
   (faultLength!=0 && io_tl_a_bits_address<faultAddress+faultLength && faultAddress<io_tl_a_bits_address+(1<<io_tl_a_bits_size));
  pending<=1;waits<=cycles%4;requests=requests+1;
 end
 if(pending && !io_tl_d_valid)begin
  if(waits>0)waits<=waits-1;
  else begin
   io_tl_d_valid<=1;io_tl_d_bits_opcode<=pop==4?1:0;io_tl_d_bits_size<=psz;io_tl_d_bits_source<=0;
   io_tl_d_bits_denied<=denied;io_tl_d_bits_corrupt<=0;io_tl_d_bits_data<=0;
   if(!denied)begin beat=(pa-64'h80010000)&~7;for(j=0;j<8;j=j+1)io_tl_d_bits_data[8*j+:8]<=mem[beat+j] ^ ((j==0 && $test$plusargs("corrupt-read"))?8'h1:8'h0);end
  end
 end
 if(io_tl_d_valid && io_tl_d_ready)begin
  if(pop!=4 && !denied)begin beat=(pa-64'h80010000)&~7;for(j=0;j<8;j=j+1)if(pmask[j])mem[beat+j]<=pdata[8*j+:8];end
  io_tl_d_valid<=0;pending<=0;responses=responses+1;
 end
end

task check_state(input string rf,input string ram);
integer k;begin
 $readmemh(rf,expectedRf);$readmemh(ram,expectedMem);
 for(k=0;k<64;k=k+1)ctx_access(k,0,expectedRf[k]);
 for(k=0;k<8192;k=k+1)if(mem[k]!==expectedMem[k])$fatal(1,"Spike RAM mismatch id=%0d byte=%0d got=%h expected=%h",commands-1,k,mem[k],expectedMem[k]);
 if(pending || io_tl_d_valid || requests!=responses)$fatal(1,"undrained bus");
end endtask
'''
def events_for(entries,compact=False):
    rng=random.Random(0x51ad12864);events=[];ident=0
    def ins(name,raw,scalar=0,scalar2=0,avl=0,**metadata):
        nonlocal ident
        events.append(dict(kind='I',id=ident,name=name,instruction=raw,scalar=scalar&M64,scalar2=scalar2&M64,avl=avl,**metadata));ident+=1
    def csr(value):ins('vstart',8<<20|1<<15|1<<12|3<<7|0x73,scalar=value)
    def config(s,m=0,vl=3):ins('vsetvli',(s<<3|m)<<20|1<<15|7<<12|3<<7|0x57,avl=vl)
    def fixture(s,nf,index_width=None):
        events.append(dict(kind='M',data=bytes((i*13+7)&255 for i in range(N)).hex()))
        events.append(dict(kind='F',address=0,length=0))
        for r in range(32):
            data=rng.getrandbits(128) if r else int('a596'*8,16)
            if r>=24 and index_width:
                width=index_width;first=(r-24)*16//width;data=sum(((first+k)*(1<<s)*nf)%(1<<(width*8))<<(k*width*8) for k in range(16//width))
            events.append(dict(kind='R',register=r,data=data))
    types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
    if compact:types=[(2,0)]
    forms=[(e,nf) for e in entries for nf in ([1] if e['mask']&(7<<29) else [1,2,3,4,5,6,7,8])]
    for block,(s,m) in enumerate(types):
        current=[(e,1) for e in entries] if block else forms
        for index,(entry,nf) in enumerate(current):
            raw=entry['match'];indexed=(raw>>26&3) in [1,3];strided=(raw>>26&3)==2
            width=1<<([0,5,6,7].index(raw>>12&7))
            fixture(s,nf,width if indexed else None);config(s,m)
            fields=((index+block)%2<<25)|(24<<20 if indexed else 2<<20 if strided else 0)|(1<<15)|(8<<7)|((nf-1)<<29)
            raw |= fields&~entry['mask']
            stride=-(1<<s)*nf*2 if index%3==0 else (1<<s)*nf*2 if index%3==1 else 0
            ins(entry['name'],raw,BASE+2048,stride,nf=nf,sew=8<<s,lmul=m)
    # Fault/retry and restart preserve partial RF/RAM and current vstart.
    names={e['name']:e for e in entries}
    for name,nf in [('vle32_v',1),('vse32_v',1),('vle32ff_v',1),('vle32ff_v',3),('vle8_v',3),('vse8_v',3),('vlm_v',1),('vsm_v',1),('vl8re8_v',1),('vs8r_v',1)]:
        if name not in names:continue
        e=names[name];raw=e['match']|((1<<25)|(1<<15)|(8<<7)|((nf-1)<<29))&~e['mask']
        width=1<<[0,5,6,7].index(raw>>12&7)
        for fault_index in [0,1]:
            fixture(2,nf);config(2,0,4)
            addr=BASE+2048+fault_index*nf*width
            events.append(dict(kind='F',address=addr,length=width));ins(name+'-fault',raw,BASE+2048,fault_index=fault_index,nf=nf)
            events.append(dict(kind='F',address=0,length=0));ins(name+'-retry',raw,BASE+2048,nf=nf)
        fixture(2,nf);config(2,0,4);csr(1);ins(name+'-restart',raw,BASE+2048,nf=nf)
    # Pre-access address checks must trap without emitting a TileLink request.
    for name in ['vle32_v','vse32_v']:
        e=names[name];raw=e['match']|1<<25|1<<15|8<<7
        for addr in [BASE+2049,0x70000000]:
            fixture(2,1);config(2);ins(name+'-address-fault',raw,addr)
    return events

def reference(events,folder,model):
    lines=[]
    for e in events:
        if e['kind']=='R':lines.append(f'R {e["register"]} {e["data"]:032x}')
        elif e['kind']=='M':lines.append('M 0 '+e['data'])
        elif e['kind']=='F':lines.append(f'F {e["address"]:x} {e["length"]:x}')
        else:lines.append('I '+' '.join(f'{e[k]:x}' for k in ['instruction','scalar','scalar2','avl']))
    inp=folder/'spike-input.txt';outp=folder/'spike-output.txt';inp.write_text('\n'.join(lines)+'\n')
    with inp.open() as inp,outp.open('w') as out,(folder/'spike-stderr.log').open('w') as err:subprocess.run([ROOT/model['binary']],stdin=inp,stdout=out,stderr=err,cwd=ROOT,check=True,timeout=180)
    states=[];gold=folder/'gold';gold.mkdir(exist_ok=True)
    def save(text):
        path=gold/(hashlib.sha256(text.encode()).hexdigest()+'.hex')
        if not path.exists():path.write_text(text)
        return str(path.relative_to(ROOT))
    for line in outp.read_text().splitlines():
        f=line.split()
        if f[0]=='S':
            assert len(f)==46 and int(f[1])==len(states)
            regs=[int(x,16) for x in f[14:]]
            states.append(dict(illegal=int(f[2]) and int(f[3])==2,cause=int(f[3]),tval=int(f[4],16),scalar=int(f[5],16),writes=int(f[6],16),vl=int(f[7],16),vtype=int(f[8],16),vstart=int(f[9],16),vxrm=int(f[10],16),vxsat=int(f[11],16),frm=int(f[12],16),fflags=int(f[13],16),rf=save(''.join(f'{r>>(64*k)&M64:016x}\n' for r in regs for k in range(2)))))
        else:
            assert f[0]=='D' and int(f[1])==len(states)-1 and len(f[2])==2*N
            states[-1]['ram']=save('\n'.join(f[2][i:i+2] for i in range(0,len(f[2]),2))+'\n')
    assert len(states)==sum(e['kind']=='I' for e in events)
    return states

def main():
    p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--model-only',action='store_true');p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args()
    model=json.loads((ROOT/'build/spike-memory-model/results.json').read_text());assert model['status']=='PASS' and not model['semantics_modified']
    assert sha(ROOT/model['binary'])==model['binary_sha256']
    for rel,h in model['sha256'].items():assert sha(ROOT/rel)==h,rel
    entries=json.loads((ROOT/'build/spike-memory-model/catalog.json').read_text());events=events_for(entries,a.compact)
    label=a.top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');folder=OUT/label;folder.mkdir(parents=True,exist_ok=True)
    states=reference(events,folder,model);(folder/'inputs.json').write_text(json.dumps(events,indent=2)+'\n');(folder/'expected.json').write_text(json.dumps(states,indent=2)+'\n')
    if a.model_only:print('PASS model',label,len(states));return
    body=[]
    for e in events:
        if e['kind']=='R':body += [f"ctx_access({e['register']*2+k},1,64'h{e['data']>>(64*k)&M64:x});" for k in range(2)]
        elif e['kind']=='M':body.append('for(j=0;j<8192;j=j+1)mem[j]=(j*13+7)&255;')
        elif e['kind']=='F':body.append(f"faultAddress=64'h{e['address']:x};faultLength=64'h{e['length']:x};")
        else:
            st=states[e['id']];args=[str(e['id']),f"32'h{e['instruction']:x}"]+[f"64'h{e[k]:x}" for k in ['scalar','scalar2','avl']]+[str(int(st['illegal'])),str(st['writes']),f"64'h{st['scalar']:x}",str(st['cause']),f"64'h{st['tval']:x}"]
            args += [f"8'd{st['vl']}",f"64'h{st['vtype']:x}",f"7'd{st['vstart']}",str(st['vxrm']),str(st['vxsat']),str(st['frm']),str(st['fflags'])]
            body.append('command('+','.join(args)+');');body.append(f'check_state("{st["rf"]}","{st["ram"]}");')
    production=ROOT/f'build/rtl/{a.top}.sv';fp='Integer' not in a.top;template=ROOT/'tests/spike_memory_tb.sv';tb=folder/'tb.sv'
    text=template.read_text().replace('// PIN_DECLARATIONS',pins(production,a.top)).replace('// RAM_MODEL',RAM).replace('// EVENTS','\n'.join(body))
    text='`define FRM '+('io_core_frm' if fp else "3'd0")+'\n`define FLAGS '+('io_core_fflags' if fp else "5'd0")+'\n'+text;tb.write_text(text)
    netlist=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,netlist];options=[];assertion_sources=[]
    if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];options=['-s','glbl']
    else:
        module='RamVector'+('Fp' if fp else 'Integer')+'Memory'+('16' if 'Deep' in a.top else '')
        for mod,instance in [(module,'vpu.vpu'),('VectorMemoryEngine','vpu.engine')]:
            source=ROOT/f'build/rtl/verification/assert/{mod}_Verification_Assert.sv';monitor=folder/(mod+'-assert.sv');monitor.write_text(source.read_text().replace(mod+'.','tb.dut.'+instance+'.'));files.append(monitor);assertion_sources.append(source);options+=['-s',mod+'_Verification_Assert']
    with (folder/'compile.log').open('w') as log:subprocess.run([BIN/'iverilog','-g2012','-s','tb',*options,'-DTOP='+a.top,'-o',folder/'sim',*files],stdout=log,stderr=log,check=True,cwd=ROOT)
    with (folder/'run.log').open('w') as log:r=subprocess.run([BIN/'vvp',folder/'sim'],stdout=log,stderr=log,cwd=ROOT,timeout=3600)
    output=(folder/'run.log').read_text();assert r.returncode==0,output[-3000:]
    with (folder/'negative.log').open('w') as log:negative=subprocess.run([BIN/'vvp',folder/'sim','+corrupt-read'],stdout=log,stderr=log,cwd=ROOT,timeout=120)
    assert negative.returncode==1 and 'Spike RF mismatch' in (folder/'negative.log').read_text()
    timings=[dict(id=int(f[1]),cycles=int(f[2])) for f in (line.split() for line in output.splitlines() if line.startswith('CMD '))];assert len(timings)==len(states)
    legal=sorted({e['name'] for e in events if e['kind']=='I' and not states[e['id']]['cause'] and e['name'] in {x['name'] for x in entries}})
    sources=[Path(__file__).resolve(),template,ROOT/'tests/spike_memory_adapter.cc',ROOT/'scripts/bootstrap_spike_memory.py',ROOT/'third_party/spike-reference.json',ROOT/'tests/test_compiled_programs.py']
    artifacts=[*files,*assertion_sources,*folder.glob('gold/*.hex'),folder/'inputs.json',folder/'expected.json',folder/'spike-input.txt',folder/'spike-output.txt',folder/'spike-stderr.log',folder/'compile.log',folder/'run.log',folder/'negative.log',ROOT/'build/spike-memory-model/results.json']
    result=dict(status='PASS',top=a.top,compact=a.compact,mapped=a.mapped,commands=len(states),canonical_memory_encodings=len(entries),legally_exercised_encodings=legal,segment_forms=310,
      memory_faults=sum(s['cause'] not in [0,2] for s in states),illegal_commands=sum(s['cause']==2 for s in states),compared_registers_per_command=32,compared_ram_bytes_per_command=N,
      negative_control='CORRUPT_TL_READ_REJECTED',independent_isa_model='SPIKE',revision=model['revision'],semantics_modified=False,timings=timings,summary=next(x for x in output.splitlines() if x.startswith('PASS Spike memory')),
      scope='Physical normal RAM with variable A/D stalls; no VM/PMP/coherence or asynchronous interrupts',source_sha256={str(x.relative_to(ROOT)):sha(x) for x in sources},artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in artifacts})
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(label,result['summary'],len(legal),'legal encodings',flush=True)
if __name__=='__main__':main()
