#!/usr/bin/env python3
"""Independent Python ABI/continuation oracle against real public GSIM ports."""
import argparse,hashlib,json,os,random,re,struct,subprocess,time,zlib
from pathlib import Path
from test_compiled_programs import ROOT,env
OUT=ROOT/'build/context-image';BYTES=576;MASK64=(1<<64)-1
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def image(regs,typ,vl,start,vcsr,fcsr,fp):
    data=bytearray(struct.pack('<8sHHIHHHHQQQIIII',b'SPINCTX1',1,fp,BYTES,128,64,32,8,vl,typ,start,vcsr,fcsr,0,0)+struct.pack('<64Q',*regs))
    assert len(data)==BYTES;struct.pack_into('<I',data,56,zlib.crc32(data));return bytes(data)
def crc_fix(data):
    data=bytearray(data);data[56:60]=b'\0'*4;struct.pack_into('<I',data,56,zlib.crc32(data));return bytes(data)
def prepare(folder,fp):
    rng=random.Random(0x53c07e);gold=folder/'gold';gold.mkdir(exist_ok=True);ram=bytes((i*13+7)&255 for i in range(8192));cases=[];lines=[]
    def write(name,data):p=gold/name;p.write_bytes(data);return p
    plain_ram=write('plain.ram',ram)
    def add(typ,vl,start,vcsr,fcsr,mode=0,negative=False):
        ident=len(cases);seed=[rng.getrandbits(64) for _ in range(64)];initial=bytearray(struct.pack('<64Q',*seed));saved=bytearray(initial);before=bytearray(ram);after=bytearray(ram)
        post=bytearray(initial);snapshot_start=start;post_start=0 if not(typ>>63) else start
        if mode in [1,2,3]:
            fields=3 if mode==2 else 1;snapshot_start=1
            for e in range(vl):
                for field in range(fields):
                    offset=(e*fields+field)*4;pos=(8+field)*16+e*4
                    if mode==3:
                        after[offset:offset+4]=initial[pos:pos+4]
                        if e<1:before[offset:offset+4]=initial[pos:pos+4]
                    else:
                        post[pos:pos+4]=ram[offset:offset+4]
                        if e<1 or (mode==2 and e==1 and field==0):saved[pos:pos+4]=ram[offset:offset+4]
        elif mode in [4,5]:
            width=1<<((typ>>3)&7);bits=8*width;rounding=(fcsr>>5) if mode==4 else vcsr>>1
            initial[:16]=b'\xff'*16
            for e in range(vl):
                if mode==4:
                    sign=(1<<(bits-1)) if negative else 0
                    one=(0x3f800000 if width==4 else 0x3ff0000000000000)|sign
                    half=(0x33800000 if width==4 else 0x3ca0000000000000)|sign
                    initial[16*16+e*width:16*16+(e+1)*width]=one.to_bytes(width,'little')
                    initial[24*16+e*width:24*16+(e+1)*width]=half.to_bytes(width,'little')
                else:initial[16*16+e*width:16*16+(e+1)*width]=(3 if e%2==0 else 5).to_bytes(width,'little')
            saved=bytearray(initial);post=bytearray(initial)
            for e in range(start,vl):
                if mode==4:value=one+int(rounding in ([2,4] if negative else [3,4]))
                else:
                    number=3 if e%2==0 else 5;base=number>>1
                    value=base+int(rounding==0 or rounding==1 and base&1 or rounding==3 and not(base&1))
                post[8*16+e*width:8*16+(e+1)*width]=value.to_bytes(width,'little')
        elif not typ>>63:
            width=1<<((typ>>3)&7);mask=(1<<(8*width))-1;vector_mask=int.from_bytes(initial[:16],'little')
            for e in range(start,vl):
                if vector_mask>>e&1:
                    src=int.from_bytes(initial[16*16+e*width:16*16+(e+1)*width],'little')
                    post[8*16+e*width:8*16+(e+1)*width]=((src+17)&mask).to_bytes(width,'little')
        fcsr=fcsr if fp else 0;post_fcsr=fcsr|1 if mode==4 else fcsr
        seed=struct.unpack('<64Q',initial)
        a=write(f'{ident:04d}-saved.bin',image(struct.unpack('<64Q',saved),typ,vl,snapshot_start,vcsr,fcsr,fp))
        b=write(f'{ident:04d}-resumed.bin',image(struct.unpack('<64Q',post),typ,vl,post_start,vcsr,post_fcsr,fp))
        c=write(f'{ident:04d}-before.ram',before) if mode==3 else plain_ram;d=write(f'{ident:04d}-after.ram',after) if mode==3 else plain_ram
        paths=[str(p.relative_to(ROOT)) for p in [a,b,c,d]]
        lines.append(' '.join(f'{v:x}' for v in [ident,typ,vl,start,vcsr,fcsr,mode])+' '+' '.join(paths)+' '+' '.join(f'{r:016x}' for r in seed))
        cases.append(dict(id=ident,vtype=typ,vl=vl,vstart=start,vcsr=vcsr,fcsr=fcsr,mode=mode,saved=str(a.relative_to(ROOT)),resumed=str(b.relative_to(ROOT))))
    for m in [0,1,2,3,5,6,7]:
        for s in range(4):
            if m>=4 and s>m-5:continue
            maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
            for vl in [0,1,maximum]:
                for start in [0,1,127]:
                    i=len(cases);add((s<<3|m)|((i%4)<<6),vl,start,i%8,(i*37+31)&255)
    for start in [0,1,127]:add(1<<63,0,start,5,0xe7)
    if fp:
        for fcsr in range(256):add(16,3,fcsr%4,fcsr%8,fcsr)
    if fp:
        for m in [0,1,2,3,7]:
            for s in [2,3]:
                if m==7 and s==3:continue
                maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
                for rm in range(5):
                    for negative in [False,True]:add(s<<3|m,maximum,1,5,(rm<<5)|16,4,negative)
    for m in [0,1,2,3,5,6,7]:
        for s in range(4):
            if m>=4 and s>m-5:continue
            maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
            for rm in range(4):
                for sat in [0,1]:add(s<<3|m,maximum,0,rm*2+sat,(len(cases)*37)&255,5)
    for mode in [1,2,3]:add(16,3 if mode==2 else 4,0,5,0xe7,mode)
    path=folder/'cases.txt';path.write_text('\n'.join(lines)+'\n');(folder/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    valid=Path(ROOT/cases[0]['saved']).read_bytes();bad=[]
    def malformed(name,off,fmt,value,code):
        data=bytearray(valid);struct.pack_into(fmt,data,off,value);p=write('bad-'+name+'.bin',crc_fix(data));bad.append((code,p))
    for name,off,fmt,value,code in [
        ('magic',0,'<B',0,-2),('version',8,'<H',2,-2),('features',10,'<H',fp^1,-2),('size',12,'<I',575,-2),('reserved',60,'<I',1,-2),
        ('vlen',16,'<H',256,-4),('elen',18,'<H',32,-4),('regs',20,'<H',16,-4),('chunk',22,'<H',4,-4),('vl',24,'<Q',129,-4),
        ('vstart',40,'<Q',128,-4),('vcsr',48,'<I',8,-4),('fcsr',52,'<I',256,-4),('sew',32,'<Q',32,-4),('lmul',32,'<Q',4,-4),
        ('fraction',32,'<Q',13,-4),('type-high',32,'<Q',256,-4),('vill-bits',32,'<Q',(1<<63)|1,-4)]:malformed(name,off,fmt,value,code)
    # A canonical vill must have VL0; this catches metadata, not merely CRC.
    data=bytearray(valid);struct.pack_into('<QQ',data,24,1,1<<63);p=write('bad-vill-vl.bin',crc_fix(data));bad.append((-4,p))
    if not fp:malformed('absent-fp',52,'<I',1,-4)
    bad_list=folder/'bad-list.txt';bad_list.write_text(''.join(f'{code} {p.relative_to(ROOT)}\n' for code,p in bad))
    return cases,path,bad_list,ROOT/cases[0]['saved']
def execute(command,log,timeout=600,environment=None):
    start=time.perf_counter()
    with log.open('w') as f:r=subprocess.run(list(map(str,command)),cwd=ROOT,env=environment or env(),stdout=f,stderr=f,timeout=timeout)
    assert r.returncode==0,(command,log.read_text()[-4000:]);return time.perf_counter()-start

def main():
    p=argparse.ArgumentParser();p.add_argument('--top',default='SpinorStandard',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']);a=p.parse_args();fp='Integer' not in a.top
    folder=OUT/a.top;folder.mkdir(parents=True,exist_ok=True);cases,stimulus,bad,valid=prepare(folder,int(fp))
    export=ROOT/'build/gsim-direct/rtl'/a.top;meta=json.loads((export/'results.json').read_text());assert meta['status']=='PASS'
    for key in ['source_sha256','artifact_sha256']:
        for rel,h in meta[key].items():assert sha(ROOT/rel)==h,rel
    library=ROOT/'software/context/spinor_context.c';header=ROOT/'software/context/spinor_context.h';obj=folder/'context.o'
    execute(['gcc','-std=c11','-O2','-ffreestanding','-fno-tree-vectorize','-Wall','-Wextra','-Werror','-pedantic','-c',library,'-o',obj],folder/'c-compile.log')
    compiler=ROOT/'tools/llvm-program/usr/bin/clang++-19';binary=folder/'run';harness=ROOT/'tests/context_gsim.cc'
    execute([compiler,'-std=c++20','-O2','-DENABLE_FP='+str(int(fp)),'-DDUT_CLASS=S'+a.top,'-DDUT_HEADER="'+a.top+'.h"','-I'+str(export),'-I'+str(ROOT/'software/context'),*sorted(export.glob(a.top+'[0-9]*.cpp')),harness,obj,'-ldl','-o',binary],folder/'compile.log',1200)
    wall=execute([binary,stimulus],folder/'run.log');text=(folder/'run.log').read_text();summary=next(x for x in text.splitlines() if x.startswith('PASS context GSIM'))
    negative={}
    for name,diagnostic in [('skip-vstart','independent image mismatch'),('unlock-on-error','failed restore released ownership')]:
        log=folder/(name+'.log')
        with log.open('w') as f:r=subprocess.run([binary,stimulus,name],cwd=ROOT,env=env(),stdout=f,stderr=f,timeout=120)
        assert r.returncode==1 and diagnostic in log.read_text(),(name,log.read_text());negative[name]='REJECTED'
    checker=folder/'validate';validation=ROOT/'tests/context_validation.c'
    execute(['gcc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-pedantic','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'software/context'),library,validation,'-o',checker],folder/'validation-compile.log')
    sanitized=env();sanitized['ASAN_OPTIONS']='detect_leaks=0';execute([checker,valid,bad,str(int(fp))],folder/'validation.log',environment=sanitized)
    metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',summary)};assert metrics['cases']==len(cases) and metrics['busy_memory']==3
    sources=[Path(__file__).resolve(),harness,library,header,validation,ROOT/'tests/gsim_spike_driver.cc',ROOT/'tests/test_compiled_programs.py']
    artifacts=[stimulus,folder/'cases.json',bad,*folder.glob('gold/*'),*folder.glob('*.log'),obj,binary,checker,export/'results.json']
    d=dict(status='PASS',top=a.top,hardware_changed=False,abi=1,image_bytes=BYTES,metrics=metrics,independent_oracle='PYTHON_STRUCT_ZLIB_AND_INTEGER_CONTINUATION',negative_controls=negative,run_wall_seconds=wall,summary=summary,validation_summary=(folder/'validation.log').read_text().strip(),
      source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(a.top,summary,d['validation_summary'],flush=True)
if __name__=='__main__':main()
