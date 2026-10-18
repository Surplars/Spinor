#!/usr/bin/env python3
"""Execute RV64 ELF control flow against the real public VPU, not a trace replay.

Python and native scalar C independently check complete RAM images. The scalar
SV executor is a test adapter, not Orbital or an ISA reference model.
"""
import argparse
import ctypes
import hashlib
import json
import os
import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/programs'
LLVM = ROOT / 'tools/llvm-program/usr'
BIN = ROOT / 'tools/oss-cad-suite/bin'
BASE = 0x80000000
MASK64 = (1 << 64) - 1
AUTO = ['add_u8', 'add_u16', 'add_u32', 'add_u64', 'macc_u32', 'clamp_i32',
        'select_u32', 'sum_u32', 'dot_i16', 'gather_u32', 'aos2_u32', 'sar_i32', 'quotrem_i32']
STRIP = ['strip_u32', 'strip_u8m8', 'strip_f32', 'strip_f64']
FLAGS = ['--target=riscv64-unknown-elf', '-march=rv64gv', '-mabi=lp64d', '-O3',
         '-ffreestanding', '-fno-builtin', '-fno-unroll-loops']
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def env():
    result = os.environ.copy()
    result['LD_LIBRARY_PATH'] = str(LLVM / 'lib/x86_64-linux-gnu') + (
        ':' + result['LD_LIBRARY_PATH'] if result.get('LD_LIBRARY_PATH') else '')
    return result


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'software/programs/toolchain.lock.json').read_text())
    for spec in lock.values():
        assert sha(ROOT / 'tools/llvm-program' / spec['file']) == spec['sha256']
    cc = LLVM / 'bin/clang-19'
    version = subprocess.check_output([cc, '--version'], env=env(), text=True)
    assert '19.1.7' in version
    outputs = []
    for name in ['kernels', 'stripmine']:
        source = f'software/programs/{name}.c'
        target = OUT / (name + '.s')
        subprocess.run([cc, *FLAGS, '-S', source, '-o', target], cwd=ROOT, env=env(), check=True)
        outputs.append(target)
    elf = OUT / 'kernels.elf'
    command = [str(cc), *FLAGS, '-nostdlib', '-fuse-ld=' + str(LLVM / 'bin/ld.lld-19'),
               '-Wl,-T,software/programs/link.ld', '-Wl,-e,add_u32',
               'software/programs/kernels.c', 'software/programs/stripmine.c', '-o', str(elf)]
    subprocess.run(command, cwd=ROOT, env=env(), check=True)
    subprocess.run(['gcc', '-O2', '-fno-tree-vectorize', '-shared', '-fPIC',
                    'software/programs/kernels.c', '-o', str(OUT / 'native.so')], cwd=ROOT, check=True)
    manifest = dict(status='PASS',compiler=version.splitlines()[0],flags=FLAGS,
                    link_command=command,host_compiler=subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],
                    sha256={str(p.relative_to(ROOT)):sha(p) for p in outputs+[elf,OUT/'native.so']},
                    source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [
                        ROOT/'software/programs/toolchain.lock.json',ROOT/'software/programs/kernels.c',
                        ROOT/'software/programs/stripmine.c',ROOT/'software/programs/link.ld',Path(__file__).resolve()]})
    (OUT/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def elf_image(path):
    raw = path.read_bytes()
    assert raw[:6] == b'\x7fELF\x02\x01'
    h = struct.unpack_from('<HHIQQQIHHHHHH', raw, 16)
    assert h[1] == 243 and h[8] == 56 and h[10] == 64
    code = bytearray(0x4000)
    for i in range(h[9]):
        typ,flags,off,va,pa,filesz,memsz,align = struct.unpack_from('<IIQQQQQQ',raw,h[4]+56*i)
        if typ != 1: continue
        assert BASE <= va and va+memsz <= BASE+len(code)
        code[va-BASE:va-BASE+filesz] = raw[off:off+filesz]
    sections = [struct.unpack_from('<IIQQQQIIQQ',raw,h[5]+64*i) for i in range(h[11])]
    symbols = {}
    for sec in sections:
        if sec[1] != 2: continue
        strings = sections[sec[6]]
        names = raw[strings[4]:strings[4]+strings[5]]
        for off in range(sec[4],sec[4]+sec[5],sec[9]):
            name,info,other,idx,value,size = struct.unpack_from('<IBBHQQ',raw,off)
            if info & 15 == 2 and idx:
                symbols[names[name:names.index(0,name)].decode()] = (value,size)
    assert set(AUTO+STRIP+['fof_copy']) <= symbols.keys()
    return code,symbols


def width(name):
    return 1 if name in ['add_u8','strip_u8m8','fof_copy'] else 2 if name in ['add_u16','dot_i16'] else 8 if name in ['add_u64','strip_f64'] else 4


def signed(value,bits):
    return value-(1<<bits) if value>>(bits-1) else value


def prepare_case(name,n,seed,code,available=0):
    data = bytearray((i*13+seed*29+(i>>5)*7)&255 for i in range(65536))
    data[:len(code)] = code
    w=width(name);mask=(1<<(8*w))-1
    edge=[0,1,mask,1<<(8*w-1),(1<<(8*w-1))-1,37,91,92,mask-36]
    for i in range(512):
        a=(edge[i] if i<len(edge) else (i*0x9e3779b97f4a7c15+seed*0xd1b54a32d192ed03))&mask
        b=(edge[-i-1] if i<len(edge) else (i*0x94d049bb133111eb+seed*0x369dea0f31a53f85))&mask
        if name=='gather_u32': b=(i*37+seed)%251
        if name=='quotrem_i32' and (b==0 or (a==0x80000000 and b==0xffffffff)): b=3
        if name in ['strip_f32','strip_f64']:
            fmt='<f' if w==4 else '<d'
            data[0x6000+i*w:0x6000+(i+1)*w]=struct.pack(fmt,(i-139)*0.5)
            data[0x8000+i*w:0x8000+(i+1)*w]=struct.pack(fmt,(seed-3*i)*0.25)
        else:
            data[0x6000+i*w:0x6000+(i+1)*w]=a.to_bytes(w,'little')
            data[0x8000+i*w:0x8000+(i+1)*w]=b.to_bytes(w,'little')
    expected=bytearray(data);ret=None;total=0
    get=lambda pos,ew=w:int.from_bytes(data[pos:pos+ew],'little')
    if name=='fof_copy':
        actual=min(n,128,available);ret=actual
        expected[0x4000:0x4000+actual]=data[0xc000-available:0xc000-available+actual]
    else:
        for i in range(n):
            a=get(0x6000+i*w);b=get(0x8000+i*w)
            if name=='gather_u32':value=get(0x6000+4*b)
            elif name=='aos2_u32':value=get(0x6000+8*i)+get(0x6000+8*i+4)
            elif name=='macc_u32':value=7*a+b
            elif name=='clamp_i32':value=max(-37,min(91,signed(a,32)))
            elif name=='select_u32':value=a+b if a>0x7fffffff else b^0x13579bdf
            elif name=='sar_i32':value=signed(a,32)>>(b&31)
            elif name=='quotrem_i32':
                av,bv=signed(a,32),signed(b,32)
                quotient=(abs(av)//abs(bv))*(-1 if (av<0)!=(bv<0) else 1)
                value=quotient+(av-quotient*bv)
            elif name=='sum_u32':total=(total+a)&0xffffffff;continue
            elif name=='dot_i16':total=(total+signed(a,16)*signed(b,16))&0xffffffff;continue
            elif name in ['strip_f32','strip_f64']:
                fmt='<f' if w==4 else '<d'
                a=struct.unpack(fmt,data[0x6000+i*w:0x6000+(i+1)*w])[0]
                b=struct.unpack(fmt,data[0x8000+i*w:0x8000+(i+1)*w])[0]
                expected[0x4000+i*w:0x4000+(i+1)*w]=struct.pack(fmt,a+b);continue
            else:value=a+b
            expected[0x4000+i*w:0x4000+(i+1)*w]=(value&mask).to_bytes(w,'little')
        if name in ['sum_u32','dot_i16']:ret=signed(total,32)&MASK64
    if name in AUTO:
        native=bytearray(data);buf=(ctypes.c_ubyte*len(native)).from_buffer(native);base=ctypes.addressof(buf)
        fn=getattr(ctypes.CDLL(str(OUT/'native.so')),name)
        fn.argtypes=[ctypes.c_void_p]*3+[ctypes.c_ulong];fn.restype=ctypes.c_uint
        result=fn(base+0x4000,base+0x6000,base+0x8000,n)
        assert native==expected,('native/Python memory disagreement',name,n)
        if ret is not None:assert result==(ret&0xffffffff),(name,n,result,ret)
    return data,expected,ret


def pins(rtl,top):
    header=rtl.read_text().split('module '+top+'(',1)[1].split(');',1)[0]
    result=['module tb;'];direction=None;size=''
    for item in header.split(','):
        item=item.strip()
        match=re.fullmatch(r'(input|output)\s+(\[\d+:0\]\s+)?(\w+)',item)
        if match:direction,size,name=match.groups();size=size or ''
        else:
            assert re.fullmatch(r'\w+',item),item
            name=item
        wire=direction=='output' or name=='io_tl_a_ready'
        result.append(f'{"wire" if wire else "reg"} {size}{name}'+(';' if wire else '=0;'))
    return '\n'.join(result)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--top',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'],default='SpinorStandard')
    p.add_argument('--mapped',action='store_true');p.add_argument('--smoke',action='store_true')
    p.add_argument('--compact',action='store_true',help='Per-kernel vector threshold plus one tail, zero and scalar path')
    p.add_argument('--negative-control',action='store_true',help='Also corrupt every TL read response and require oracle rejection')
    p.add_argument('--only',help='Comma-separated kernels for development runs')
    args=p.parse_args()
    assert not (args.compact and args.smoke)
    if args.build_only:build();return
    manifest=json.loads((OUT/'build.json').read_text())
    for key in ['source_sha256','sha256']:
        for rel,h in manifest[key].items():assert sha(ROOT/rel)==h,rel
    code,symbols=elf_image(OUT/'kernels.elf')
    fp='Integer' not in args.top
    names=AUTO+['strip_u32','strip_u8m8']+(['strip_f32','strip_f64'] if fp else [])+['fof_copy']
    if args.only:names=[n for n in names if n in args.only.split(',')]
    lengths=[0,1,7,8,9,17,33,129] if args.smoke else [0,1,2,3,4,7,8,9,15,16,17,31,32,33,63,64,65,127,128,129]
    label=args.top+('-compact' if args.compact else '-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl')+('-dev' if args.only else '')
    folder=OUT/label;folder.mkdir(parents=True,exist_ok=True)
    calls=[];specs=[];expected_outputs=[]
    for name in names:
        threshold={'add_u8':32,'add_u16':16,'add_u64':4,'strip_u32':4,'strip_u8m8':128,'strip_f32':4,'strip_f64':2}.get(name,8)
        current_lengths=[0,1,threshold+1] if args.compact else lengths
        variants=[(n,0) for n in current_lengths] if name!='fof_copy' else [(n,a) for n,a in ([(0,8),(1,8),(129,8),(129,1),(129,128)] if args.compact else [(0,8),(1,8),(7,8),(8,8),(9,8),(129,8),(129,1),(129,64),(129,128)])]
        for n,available in variants:
            ident=len(specs);seed=ident+1
            data,expected,ret=prepare_case(name,n,seed,code,available)
            image=folder/f'{ident}.hex';image.write_text(''.join(f'{b:02x}\n' for b in data))
            dump=folder/f'{ident}.bin';dump.unlink(missing_ok=True)
            argA=0x90000000-available if name=='fof_copy' else BASE+0x6000
            calls.append(f'run_case({ident},64\'h{symbols[name][0]:x},64\'h{argA:x},{n},"{image.relative_to(ROOT)}","{dump.relative_to(ROOT)}");')
            specs.append(dict(id=ident,kernel=name,n=n,seed=seed,available=available,
                              input_sha256=hashlib.sha256(data).hexdigest(),expected_ram_sha256=hashlib.sha256(expected[:0xd000]).hexdigest(),expected_return=ret,
                              source='AUTO_VECTORIZED_C' if name in AUTO else 'RVV_INTRINSICS_C'))
            expected_outputs.append(expected[:0xd000])
    source=ROOT/f'build/rtl/{args.top}.sv'
    tb=folder/'tb.sv';tb.write_text((ROOT/'tests/program_runner.sv').read_text().replace('// PIN_DECLARATIONS',pins(source,args.top)).replace('// RUN_CASES','\n'.join(calls)).replace('// FP_STATE_CHECK','if(io_core_fflags!==0 || io_core_frm!==0)$fatal(1,"unexpected FP flags/mode");' if fp else ''))
    model=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv')
    files=[tb,model];options=[];assertion_sources=[]
    if not args.mapped:
        module='RamVector'+('Fp' if fp else 'Integer')+'Memory'+('16' if 'Deep' in args.top else '')
        for mod,instance in [(module,'vpu.vpu'),('VectorMemoryEngine','vpu.engine')]:
            source_assert=ROOT/f'build/rtl/verification/assert/{mod}_Verification_Assert.sv'
            assertion_sources.append(source_assert)
            monitor=folder/(mod+'-assert.sv')
            monitor.write_text(source_assert.read_text().replace(mod+'.','tb.dut.'+instance+'.'))
            files.append(monitor);options+=['-s',mod+'_Verification_Assert']
    if args.mapped:
        files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];options=['-s','glbl']
    exe=folder/'sim'
    with (folder/'compile.log').open('w') as log:
        subprocess.run([BIN/'iverilog','-g2012','-s','tb',*options,f'-DTOP={args.top}','-o',exe,*files],stdout=log,stderr=log,check=True,cwd=ROOT)
    with (folder/'run.log').open('w') as log:
        result=subprocess.run([BIN/'vvp',exe],stdout=log,stderr=log,cwd=ROOT,timeout=1800)
    output=(folder/'run.log').read_text()
    assert result.returncode==0,output[-4000:]
    metrics=[];traces={s['id']:[] for s in specs}
    for line in output.splitlines():
        f=line.split()
        if f[0]=='CASE':
            ident=int(f[1]);spec=specs[ident];ret=int(f[2],16)
            actual=(folder/f'{ident}.bin').read_bytes();expect=expected_outputs[ident]
            assert len(actual)==len(expect),(spec,len(actual))
            if actual!=expect:
                mismatch=next(i for i,(a,b) in enumerate(zip(actual,expect)) if a!=b)
                raise AssertionError((args.top,spec,'RAM mismatch',hex(BASE+mismatch),actual[mismatch:mismatch+16].hex(),expect[mismatch:mismatch+16].hex()))
            if spec['expected_return'] is not None:assert ret==spec['expected_return'],(spec,hex(ret))
            metrics.append(dict(id=ident,return_value=ret,cycles=int(f[3]),commands=int(f[4]),requests=int(f[5]),scalar_instructions=int(f[6]),ram_sha256=hashlib.sha256(actual).hexdigest()))
        if f[0]=='VEC':traces[int(f[1])].append(dict(pc=f[2],instruction=f[3],vl=int(f[4]),scalar=f[5],writes=bool(int(f[6]))))
    assert len(metrics)==len(specs)
    negative=None
    if args.negative_control:
        with (folder/'negative.log').open('w') as log:
            bad=subprocess.run([BIN/'vvp',exe,'+bad-tl'],stdout=log,stderr=log,cwd=ROOT,timeout=1800)
        assert bad.returncode==0,'Negative control must finish normally, not fail for an unrelated tool error'
        rejected=[s['id'] for s,e in zip(specs,expected_outputs) if (folder/f'{s["id"]}.bin.bad').read_bytes()!=e]
        assert rejected,'Corrupting TL reads escaped the RAM oracle'
        negative=dict(status='PASS',mutation='XOR_BIT0_EVERY_TL_RESPONSE_DATA',rejected_cases=rejected)
    families=next(line for line in output.splitlines() if line.startswith('FAMILIES '))
    families=dict(zip(['vset','csr','whole','segment','indexed','fof','masked','fp'],map(int,families.split()[1:])))
    if not args.only:
        assert all(v>0 for k,v in families.items() if k!='fp' or fp),families
        for name in names:
            assert any(metrics[s['id']]['commands']>0 for s in specs if s['kernel']==name),name
    sources=[Path(__file__).resolve(),ROOT/'tests/program_runner.sv',ROOT/'software/programs/kernels.c',ROOT/'software/programs/stripmine.c',ROOT/'software/programs/link.ld',ROOT/'software/programs/toolchain.lock.json']
    artifacts=[model,tb,folder/'compile.log',folder/'run.log',OUT/'build.json',OUT/'kernels.elf',OUT/'kernels.s',OUT/'stripmine.s',OUT/'native.so',*files[2:],*assertion_sources]
    artifacts += [folder/f'{s["id"]}{suffix}' for s in specs for suffix in ['.hex','.bin']]
    if negative:artifacts.append(folder/'negative.log')
    d=dict(status='PASS',top=args.top,mapped=args.mapped,smoke=args.smoke,compact=args.compact,development_subset=bool(args.only),cases=len(specs),
           scope='RV64_ELF_SCALAR_TEST_ADAPTER_AND_PUBLIC_VPU_NOT_ORBITAL_OR_ARCHITECTURAL_DIFFERENTIAL',
           native_scalar_crosscheck_cases=sum(s['kernel'] in AUTO for s in specs),families=families,case_specs=specs,metrics=metrics,traces=traces,
           assertions_enabled=not args.mapped,negative_control=negative,
           compared_ram_bytes_per_case=0xd000,stack_excluded=True,compiler=manifest['compiler'],flags=FLAGS,
           source_sha256={str(f.relative_to(ROOT)):sha(f) for f in sources},
           artifact_sha256={str(f.relative_to(ROOT)):sha(f) for f in artifacts})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n')
    print(label,'PASS',len(specs),'program calls',sum(r['commands'] for r in metrics),'VPU commands',sum(r['cycles'] for r in metrics),'cycles',flush=True)


if __name__=='__main__':main()
