#!/usr/bin/env python3
"""Cycle-for-cycle GSIM replay of a Spike-checked Icarus run.

The replay checks every defined public output at each rising edge, qualifying
payloads by valid. This compares backends; Spike remains the independent ISA
oracle. Undefined Icarus bits are recorded explicitly, never coerced to zero.
"""
import argparse,hashlib,json,re,struct,subprocess,time,statistics
from pathlib import Path
from test_compiled_programs import ROOT,BIN,env
OUT=ROOT/'build/gsim-benchmark'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def ports(top):
    header=(ROOT/f'build/rtl/{top}.sv').read_text().split('module '+top+'(',1)[1].split(');',1)[0]
    result=[];direction=None;size=1
    for item in header.split(','):
        m=re.fullmatch(r'(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)',item.strip())
        if m:
            direction,hi,name=m.groups();size=int(hi)+1 if hi else 1
        else:name=item.strip()
        if name!='clock':result.append((direction,size,name))
    return result

def execute(command,log,timeout=600):
    start=time.perf_counter()
    with log.open('w') as out:r=subprocess.run(list(map(str,command)),cwd=ROOT,env=env(),stdout=out,stderr=out,timeout=timeout)
    elapsed=time.perf_counter()-start
    assert r.returncode==0,(command,log.read_text()[-2500:])
    return elapsed

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=['arithmetic','memory'],default='arithmetic');p.add_argument('--top',default='SpinorStandard');p.add_argument('--case',default='bounded');p.add_argument('--repeats',type=int,default=3);p.add_argument('--prepare-only',action='store_true');p.add_argument('--run-only',action='store_true');a=p.parse_args()
    suite='spike-differential' if a.suite=='arithmetic' else 'spike-memory'
    base=ROOT/f'build/{suite}/{a.top}-{a.case}-rtl'
    receipt=json.loads((base/'results.json').read_text());assert receipt['status']=='PASS'
    for key in ['source_sha256','artifact_sha256']:
        for rel,h in receipt[key].items():assert sha(ROOT/rel)==h,rel
    folder=OUT/(a.top+'-'+a.case+('-memory' if a.suite=='memory' else ''));folder.mkdir(parents=True,exist_ok=True)
    pp=ports(a.top);inputs=[x for x in pp if x[0]=='input'];outputs=[x for x in pp if x[0]=='output'];order=inputs+outputs
    if not a.run_only:
        template=(base/'tb.sv').read_text()
        if a.suite=='arithmetic':template=template.replace('`TOP dut(.*);','assign io_tl_a_ready=0;\n`TOP dut(.*);')
        trace=folder/'trace.txt'
        (folder/'baseline_tb.sv').write_text(template)
        declaration=f'integer trace_fd; initial trace_fd=$fopen("{trace}","w");\n'
        statement='$fdisplay(trace_fd,"'+' '.join('%h' for x in order)+'",'+','.join(x[2] for x in order)+');'
        template=template.replace('integer cycles=0',declaration+'integer cycles=0').replace('#5;clock=1;',f'#5;{statement}clock=1;')
        tb=folder/'trace_tb.sv';tb.write_text(template)
        source=[tb,ROOT/f'build/rtl/{a.top}.sv',*sorted(base.glob('*-assert.sv'))]
        execute([BIN/'iverilog','-g2012','-s','tb',*[y for path in sorted(base.glob('*-assert.sv')) for y in ['-s',path.stem.replace('-assert','')+'_Verification_Assert']],'-DTOP='+a.top,'-o',folder/'trace_sim',*source],folder/'trace-compile.log')
        execute([BIN/'iverilog','-g2012','-s','tb',*[y for path in sorted(base.glob('*-assert.sv')) for y in ['-s',path.stem.replace('-assert','')+'_Verification_Assert']],'-DTOP='+a.top,'-o',folder/'baseline_sim',folder/'baseline_tb.sv',*source[1:]],folder/'baseline-compile.log')
        execute([BIN/'vvp',folder/'trace_sim'],folder/'trace-run.log',3600)
        assert receipt['summary'] in (folder/'trace-run.log').read_text()
        expected=folder/'trace.bin';negative=folder/'negative.bin';cycles=0;checks=0;flipped=False
        with trace.open() as lines,expected.open('wb') as out,negative.open('wb') as bad:
            for line in lines:
                values=line.split();assert len(values)==len(order)
                parsed=[]
                for value,(_,width,name) in zip(values,order):
                    mask=(1<<width)-1
                    for digit,ch in enumerate(reversed(value)):
                        if ch.lower() in 'xz':mask&=~(15<<(4*digit))
                    value=int(re.sub('[xzXZ]','0',value),16);parsed.append((value,mask))
                signals={p[2]:v[0] for p,v in zip(order,parsed)};row=bytearray();badrow=None
                for j,((direction,width,name),(value,mask)) in enumerate(zip(order,parsed)):
                    if direction=='input':assert mask==(1<<width)-1,name
                    else:
                        if cycles<3:mask=0
                        qualifiers=[('io_core_completion_bits_','io_core_completion_valid'),('io_core_contextResult_bits','io_core_contextResult_valid'),('io_tl_a_bits_','io_tl_a_valid'),('io_memoryStatus_bits_','io_memoryStatus_valid'),('io_monitor_d_bits_','io_monitor_d_valid')]
                        if any(name.startswith(prefix) and not signals[valid] for prefix,valid in qualifiers):mask=0
                        checks+=bool(mask)
                    row.extend(struct.pack('<QQ',value&((1<<64)-1),value>>64))
                    if direction=='output':
                        row.extend(struct.pack('<QQ',mask&((1<<64)-1),mask>>64))
                        if not flipped and name=='io_core_contextResult_bits' and signals['io_core_contextResult_valid'] and not signals['io_core_context_bits_write'] and mask:
                            badrow=(len(row)-32,bytes(row));flipped=True
                out.write(row)
                corrupted=bytearray(row)
                if badrow:corrupted[badrow[0]]^=1
                bad.write(corrupted);cycles+=1
        assert flipped
        meta=dict(cycles=cycles,output_checks=checks,ports=order,commands=receipt['commands'],source_receipt=str((base/'results.json').relative_to(ROOT)),source_receipt_sha256=sha(base/'results.json'),trace_sha256=sha(folder/'trace.bin'))
        (folder/'trace.json').write_text(json.dumps(meta,indent=2)+'\n')
        trace.unlink() # Binary preserves every value/mask in a smaller form.
    if a.prepare_only:print('PASS trace prepared',folder);return
    meta=json.loads((folder/'trace.json').read_text());gdir=ROOT/f'build/gsim/{a.top}'
    assert sha(base/'results.json')==meta['source_receipt_sha256']
    assert sha(folder/'trace.bin')==meta['trace_sha256']
    for manifest in [ROOT/'build/gsim-model/results.json',gdir/'results.json']:
        d=json.loads(manifest.read_text());assert d['status']=='PASS'
        for key in ['source_sha256','artifact_sha256','external_source_sha256']:
            for rel,h in d.get(key,{}).items():assert sha(ROOT/rel)==h,rel
        if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256']
    cxx=[]
    for i,(direction,width,name) in enumerate(order):
        method=name.replace('_','$$');typ='uint64_t' if width<=64 else f'unsigned _BitInt({width})'
        if direction=='input':cxx.append(f'dut.set_{method}(({typ})data[pos++]);')
    lines=['#include "'+a.top+'.h"','#include <chrono>','#include <fstream>','#include <iostream>','#include <vector>','#include <stdexcept>','#include <cstring>','using W=unsigned _BitInt(128);',
      'int main(int argc,char**argv){try{if(argc!=2)throw std::runtime_error("trace argument");std::ifstream in(argv[1],std::ios::binary|std::ios::ate);if(!in)throw std::runtime_error("trace open");auto bytes=in.tellg();if(bytes<=0 || bytes%16)throw std::runtime_error("trace size");std::vector<W>data((size_t)bytes/16);in.seekg(0);in.read((char*)data.data(),bytes);if(!in)throw std::runtime_error("trace read");',
      'S'+a.top+' dut;size_t pos=0,cycles=0,checks=0;auto start=std::chrono::steady_clock::now();while(pos<data.size()){']+cxx+['dut.step();']
    for direction,width,name in outputs:
        method=name.replace('_','$$')
        lines.append('{W expected=data[pos++],mask=data[pos++];if(mask){++checks;if(((W)dut.get_'+method+'()^expected)&mask){std::cerr<<"mismatch cycle="<<cycles<<" port='+name+' expected="<<(uint64_t)expected<<" got="<<(uint64_t)dut.get_'+method+'()<<"\\n";return 1;}}}')
    lines+=['++cycles;}auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();std::cout<<"PASS GSIM replay cycles="<<cycles<<" checks="<<checks<<" seconds="<<seconds<<"\\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<"\\n";return 2;}}']
    harness=folder/'harness.cpp';harness.write_text('\n'.join(lines)+'\n')
    compile_seconds=execute([ROOT/'tools/llvm-program/usr/bin/clang++-19','-std=c++20','-O2','-I'+str(gdir),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),harness,'-ldl','-o',folder/'run'],folder/'compile.log',1200)
    times={'icarus_wall_seconds':[],'gsim_wall_seconds':[],'gsim_sim_seconds':[]}
    for i in range(a.repeats):
        times['icarus_wall_seconds'].append(execute([BIN/'vvp',folder/'baseline_sim'],folder/f'icarus-{i}.log',3600))
        assert receipt['summary'] in (folder/f'icarus-{i}.log').read_text()
        times['gsim_wall_seconds'].append(execute([folder/'run',folder/'trace.bin'],folder/f'gsim-{i}.log',3600))
        text=(folder/f'gsim-{i}.log').read_text();m=re.search(r'PASS GSIM replay cycles=(\d+) checks=(\d+) seconds=(\S+)',text);assert m
        assert int(m[1])==meta['cycles'] and int(m[2])==meta['output_checks']
        times['gsim_sim_seconds'].append(float(m[3]))
    with (folder/'negative.log').open('w') as out:r=subprocess.run([folder/'run',folder/'negative.bin'],cwd=ROOT,env=env(),stdout=out,stderr=out,timeout=120)
    assert r.returncode==1 and 'port=io_core_contextResult_bits' in (folder/'negative.log').read_text()
    sources=[ROOT/'scripts/bootstrap_gsim.py',ROOT/'scripts/emit_gsim.py',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/generate/sim/GenerateGsim.scala',ROOT/'third_party/gsim-reference.json']
    artifacts=[ROOT/'build/gsim-model/results.json',gdir/'results.json',folder/'trace_tb.sv',folder/'baseline_tb.sv',folder/'baseline_sim',folder/'trace_sim',base/'results.json',folder/'trace.bin',folder/'trace.json',folder/'negative.bin',folder/'negative.log',harness,folder/'run',gdir/(a.top+'.fir'),gdir/(a.top+'.h'),*sorted(gdir.glob(a.top+'[0-9]*.cpp')),*sorted(folder.glob('*.log'))]
    result=dict(status='PASS',kind='cycle replay of independently Spike-checked Icarus stimulus',top=a.top,suite=a.suite,commands=meta['commands'],cycles=meta['cycles'],output_checks=meta['output_checks'],times=times,gsim_cpp_compile_seconds=compile_seconds,
      median_wall_speedup=statistics.median(times['icarus_wall_seconds'])/statistics.median(times['gsim_wall_seconds']),negative_control='WRONG_RF_BIT_REJECTED',
      limitations=['Single-thread RTL only; not FPGA mapped/SDF simulation','Replay is a backend equivalence/performance test; not an adaptive GSIM LSU driver','Icarus runs original SV oracle; GSIM replays inputs and checks defined public outputs; workloads differ in checking overhead','GSIM wall includes trace loading; GSIM sim timer excludes loading; Icarus time includes process startup','No FPGA timing or new hardware functionality claim'],
      source_sha256={str(x.relative_to(ROOT)):sha(x) for x in sources},artifact_sha256={str(x.relative_to(ROOT)):sha(x) for x in artifacts})
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS',a.top,result['median_wall_speedup'],'wall speedup',times,flush=True)
if __name__=='__main__':main()
