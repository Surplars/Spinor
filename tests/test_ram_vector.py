#!/usr/bin/env python3
"""Independent architectural state, LMUL groups, CSR and version-map oracle."""
import argparse,hashlib
import json
from pathlib import Path
import random
import subprocess
from test_lane import golden
from test_vector import HEADER

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
MASK=(1<<128)-1;VILL=1<<63

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mapped-only',action='store_true');parser.add_argument('--top',choices=['RamVectorFp16'])
    parser.add_argument('--divide',action='store_true')
    parser.add_argument('--divide-smoke',action='store_true')
    parser.add_argument('--multiply',action='store_true')
    parser.add_argument('--fp',action='store_true',help='integer regression on FP-enabled engine')
    args=parser.parse_args()
    if args.top:assert args.fp,"candidate requires --fp"
    OUT.mkdir(parents=True,exist_ok=True)
    header=HEADER.replace('wire [4:0] io_vl;',
        'wire [7:0] io_vl; wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;')
    header=header.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','3000000')
    if args.fp:header=header.replace('wire [7:0] io_vl;','wire [7:0] io_vl;wire [2:0] io_frm;wire [4:0] io_fflags;')
    header=header.replace('reg [31:0] saved;','reg [31:0] saved, originalVersions;')
    header=header.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',
        'originalVersions=io_versions;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;')
    header=header.replace('while(!io_completion_valid) tick();',
        'while(!io_completion_valid)begin tick();if(io_versions !== originalVersions)$fatal(1,"early commit");end',1)
    header=header.replace('repeat(stall) begin','repeat(stall) begin\n if(io_versions !== originalVersions)$fatal(1,"commit during reply stall");',1)
    rng=random.Random(0x2a15e62)
    regs=[rng.getrandbits(128) for _ in range(32)]
    vl=0;vtype=VILL;vstart=0;vxrm=0;vxsat=0;versions=0;case=0
    lines=[header];coverage={'vector_ops':0,'csr_ops':0,'configs':0,'flushes':0,'illegal_ops':0,'group_regs':[1,2,4,8]}
    def ctx(r,write=False):
        for chunk in range(2):
            value=(regs[r]>>(64*chunk))&((1<<64)-1)
            lines.append(f"ctx({2*r+chunk},1'b{int(write)},64'h{value:x},64'h{value:x});")
    def state_check():
        lines.append(f"if(io_vstart !== 7'd{vstart} || io_vxrm !== 2'd{vxrm} || io_vxsat !== 1'b{vxsat} || "
                     f"io_versions !== 32'h{versions:x}) $fatal(1,\"state case {case} map=%h\",io_versions);")
    def command(inst,scalar=0,scalar2=0,avl=0,result=0,writes=False,illegal=False):
        nonlocal case
        lines.append(f"// CASE {case}\ncommand(32'h{inst:08x},64'h{scalar&((1<<64)-1):x},64'h{scalar2:x},64'h{avl:x},"
                     f"80'h{((0xe321<<64)|case):x},1'b{int(illegal)},64'h{result:x},1'b{int(writes)},"
                     f"{rng.randrange(7)},8'd{vl},64'h{vtype:x});")
        case+=1
        if illegal:coverage['illegal_ops']+=1
        state_check()
    def vlmax(t):
        enc=t&7;s=(t>>3)&7
        return (16>>s)*(1<<enc) if enc<=3 else (16>>s)//(1<<(8-enc)) if enc>=5 else 0
    def settype(t,avl,kind=0,rs=1,rd=3):
        nonlocal vl,vtype,vstart
        oldtype=vtype;oldvl=vl
        if kind==0:inst=(t<<20)|(rs<<15)|(7<<12)|(rd<<7)|0x57;scalar2=0
        elif kind==1:inst=(3<<30)|(t<<20)|((avl&31)<<15)|(7<<12)|(rd<<7)|0x57;scalar2=0
        else:inst=(0x40<<25)|(2<<20)|(rs<<15)|(7<<12)|(rd<<7)|0x57;scalar2=t
        enc=t&7;s=(t>>3)&7
        legal=(t>>8)==0 and s<=3 and (enc<=3 or enc>=5 and s<=enc-5)
        if kind!=1 and rs==0 and rd==0:legal=legal and oldtype!=VILL and vlmax(t)==vlmax(oldtype)
        aval=(avl&31) if kind==1 else oldvl if rs==0 and rd==0 else (1<<64)-1 if rs==0 else avl
        vl=min(aval,vlmax(t)) if legal else 0;vtype=t if legal else VILL;vstart=0
        command(inst,scalar2=scalar2,avl=avl,result=vl,writes=rd!=0)
        coverage['configs']+=1
    def csr(address,source=0,action=1,rs=1,rd=3):
        nonlocal vstart,vxrm,vxsat
        table={0x008:vstart,0x009:vxsat,0x00a:vxrm,0x00f:(vxrm<<1)|vxsat,0xc20:vl,0xc21:vtype,0xc22:16}
        old=table.get(address,0)
        mode=action&3;value=rs if action&4 else source
        write=mode==1 or mode!=0 and rs!=0
        illegal=address not in table or mode==0 or write and address>=0xc00
        new=value if mode==1 else old|value if mode==2 else old&~value
        if write and not illegal:
            if address==0x008:vstart=new&127
            elif address==0x009:vxsat=new&1
            elif address==0x00a:vxrm=new&3
            elif address==0x00f:vxrm=(new>>1)&3;vxsat=new&1
        inst=(address<<20)|(rs<<15)|(action<<12)|(rd<<7)|0x73
        command(inst,scalar=source,result=0 if illegal else old,writes=rd!=0 and not illegal,illegal=illegal)
        coverage['csr_ops']+=1
    def getgroup(base,n):return sum(regs[base+j]<<(128*j) for j in range(n))
    def vec(f6,op,form,vd,vs2,vs1,vm,scalar=0,illegal=False):
        nonlocal versions,vstart
        illegal=illegal or (not vm and ((op!=18 and vs2==0) or (form in [0,2] and vs1==0)))
        inst=(f6<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(form<<12)|(vd<<7)|0x57
        n=(1<<(vtype&7)) if vtype&7<=3 else 1
        dc=1 if 12<=op<=17 else n
        if not illegal:
            w=8<<((vtype>>3)&7);sew=(vtype>>3)&7
            av=getgroup(vs2,n);bv=getgroup(vs1,n) if form in [0,2] else 0
            dest=getgroup(vd,dc);mask=regs[0]
            for e in range(vstart,vl):
                selected=(mask>>e)&1
                if not vm and not selected and op!=19:continue
                x=(av>>(e*w))&((1<<w)-1)
                y=(bv>>(e*w)) if form in [0,2] else scalar if form in [4,6] else vs1 if op in [5,6,7] or vs1<16 else vs1-32
                z=golden(x,y,sew,op,selected)
                if 12<=op<=17:dest=(dest&~(1<<e))|((z&1)<<e)
                else:dest=(dest&~(((1<<w)-1)<<(e*w)))|(z<<(e*w))
            if vl>vstart:
                for r in range(dc):regs[vd+r]=(dest>>(128*r))&MASK
                versions^=((1<<dc)-1)<<vd
            vstart=0
        command(inst,scalar=scalar,illegal=illegal)
        coverage['vector_ops']+=1
        for r in range(dc):ctx(vd+r)
    for r in range(32):ctx(r,True)
    csr(0xc22,action=2,rs=0)
    csr(0xc20,source=0,action=2,rs=1) # encoded write is illegal even if value is zero
    csr(0x777,action=2,rs=0)
    settype(0,5)
    for address in [0x008,0x009,0x00a,0x00f]:
        for action in [1,2,3,5,6,7]:csr(address,rng.getrandbits(64),action,rng.randrange(1,32))
    # vset reset and AVL special-register behavior.
    settype(0,3);settype(0,0,rs=0,rd=3);settype(0,0,rs=0,rd=0)
    settype(8,0,rs=0,rd=0) # different VLMAX -> permitted vill choice
    defs=[(0x00,0,True),(0x02,1,False),(0x09,2,True),(0x0a,3,True),(0x0b,4,True),
          (0x25,5,True),(0x28,6,True),(0x29,7,True),(0x05,8,False),(0x04,9,False),
          (0x07,10,False),(0x06,11,False),(0x18,12,True),(0x19,13,True),
          (0x1b,14,False),(0x1a,15,False),(0x1d,16,True),(0x1c,17,True),(0x17,18,True),(0x17,19,True)]
    types=[(s<<3)|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<=3 or s<=m-5]
    if args.divide_smoke:types=[0,16,24]
    for typ in types:
        n=(1<<(typ&7)) if typ&7<=3 else 1
        for j in range(24):
            if j%6==0:
                v=vlmax(typ) if j==0 else rng.randrange(vlmax(typ)+1)
                settype(typ|(rng.randrange(4)<<6),v,kind=(j//6)%3)
            if j%5==0:csr(0x008,source=rng.randrange(min(128,vl+4)))
            f6,op,immok=defs[j%20]
            form=rng.choice([0,3,4] if immok else [0,4])
            s2=0 if op==18 else rng.randrange(32//n)*n
            s1=rng.randrange(32//n)*n if form==0 else rng.randrange(32)
            vm=1 if op==18 else 0 if op==19 else rng.randrange(2)
            legal=[]
            for d in range(32):
                if 12<=op<=17:
                    if s2<d<s2+n or form==0 and s1<d<s1+n:continue
                elif d%n or d+n>32 or not vm and d==0:continue
                legal.append(d)
            d=rng.choice(legal)
            vec(f6,op,form,d,s2,s1,vm,rng.getrandbits(64))
        if n>1:
            vec(0,0,0,n,n+1,2*n,1,illegal=True) # misaligned source group
            vec(0x18,12,0,n+1,n,2*n,1,illegal=True) # bad narrowing overlap
    if args.multiply:
        coverage['multiply_forms']={};coverage['multiply_flushes']=0
        for typ in types:
            for code,op in [(0x25,20),(0x27,25),(0x24,26),(0x26,27)]:
                for form in [2,6]:
                    settype(typ,vlmax(typ))
                    if op%2:csr(0x008,source=min(1,vl))
                    vd=rng.choice([8,16,24]);vm=rng.randrange(2)
                    vec(code,op,form,vd,8,16,vm,rng.getrandbits(64))
                    key=f'{op}:{form}';coverage['multiply_forms'][key]=coverage['multiply_forms'].get(key,0)+1
        settype(3<<3,2)
        mulinst=(0x27<<26)|(1<<25)|(8<<20)|(16<<15)|(2<<12)|(8<<7)|0x57
        for delay in [15,20,30,50,90,120,180,230]:
            lines.append(f"cancel(32'h{mulinst:x},{delay},1'b0);")
            coverage['multiply_flushes']+=1;state_check();ctx(8)
        lines.append(f"cancel(32'h{mulinst:x},0,1'b1);")
        coverage['multiply_flushes']+=1;state_check();ctx(8)
        vec(0x27,25,2,8,8,16,1)
    if args.divide:
        coverage['divide_forms']={};coverage['divide_flushes']=0
        for typ in types:
            for code,op in [(0x20,21),(0x21,22),(0x22,23),(0x23,24)]:
                for form in [2,6]:
                    settype(typ,vlmax(typ))
                    if op%2:csr(0x008,source=min(1,vl))
                    vd=rng.choice([8,16,24]);vm=rng.randrange(2)
                    vec(code,op,form,vd,8,16,vm,rng.getrandbits(64))
                    key=f'{op}:{form}';coverage['divide_forms'][key]=coverage['divide_forms'].get(key,0)+1
        settype(3<<3,2)
        divinst=(0x21<<26)|(1<<25)|(8<<20)|(16<<15)|(2<<12)|(8<<7)|0x57
        for delay in [15,20,30,50,90,120,180,230,270,400,550]:
            lines.append(f"cancel(32'h{divinst:x},{delay},1'b0);")
            coverage['divide_flushes']+=1;state_check();ctx(8)
        lines.append(f"cancel(32'h{divinst:x},0,1'b1);")
        coverage['divide_flushes']+=1;state_check();ctx(8)
        vec(0x21,22,2,8,8,16,1)
    # Reserved LMUL / too-wide fractional configurations set vill.
    for typ in [4,(3<<3)|5,(3<<3)|6,(3<<3)|7,1<<8]:settype(typ,3)
    settype(3,128) # m8/e8
    # Check abort after candidate copies and after actual result writes, plus stalled completion.
    for delay in [0,2,8,20,40,80]:
        inst=(1<<25)|(8<<20)|(16<<15)|(8<<7)|0x57
        lines.append(f"cancel(32'h{inst:x},{delay},1'b0);");coverage['flushes']+=1;state_check()
        for r in range(8,16):ctx(r)
    lines.append(f"cancel(32'h{inst:x},0,1'b1);");coverage['flushes']+=1;state_check()
    for r in range(8,16):ctx(r)
    # Stale candidate contents from the aborted instruction must not leak.
    vec(0,0,0,8,8,16,1)
    for r in range(32):ctx(r)
    lines.append('$display("PASS ram-vector commands=%0d reads=%0d cycles=%0d",cmds,reads,cycles);$finish;end endmodule\n')
    tb=OUT/((('m7-div-fp' if args.fp else 'm7-div')+('-smoke' if args.divide_smoke else '')+'-tb.sv') if args.divide else ('m6_mul_fp_vector_tb.sv' if args.fp else 'm6_mul_vector_tb.sv') if args.multiply else 'ram_vector_fp_integer_tb.sv' if args.fp else 'ram_vector_tb.sv')
    if args.top:tb=tb.with_name(tb.stem+'-candidate16'+tb.suffix)
    tb.write_text('\n'.join(lines))
    path=OUT/((('m7-div-fp' if args.fp else 'm7-div')+('-smoke' if args.divide_smoke else '')+'-results.json') if args.divide else ('m6-multiply-fp-vector-results.json' if args.fp else 'm6-multiply-vector-results.json') if args.multiply else 'fp-integer-results.json' if args.fp else 'ram-vector-results.json')
    if args.top:path=path.with_name(path.stem+'-candidate16'+path.suffix)
    results=json.loads(path.read_text()) if args.mapped_only else {'coverage':coverage,'commands':case,'models':{}}
    tops=[('RamVectorFp' if args.fp else 'RamVector')+'-mapped'] if args.mapped_only else ['RamVectorFp'] if args.fp else ['RamVector','RamVector16','RamVectorFlops']
    if args.top:tops=[args.top+('-mapped' if args.mapped_only else '')]
    for name in tops:
        mapped=name.endswith('-mapped');top=name.removesuffix('-mapped');exe=OUT/name
        files=[str(tb),str(ROOT/f'build/synth/{top}/mapped.v')] if mapped else [str(tb),str(ROOT/f'build/rtl/{top}.sv')]
        if mapped:files += [str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'),str(ROOT/'third_party/xilinx-unisim/DSP48E2.v'),str(ROOT/'tests/fp_mapped_global.sv')]
        with (OUT/f'{name}.compile.log').open('w') as log:
            subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',*(['-s','glbl'] if mapped else []),f'-DTOP={top}','-o',str(exe)]+files,
                           stdout=log,stderr=log,check=True)
        run=subprocess.run([str(BIN/'vvp'),str(exe)],cwd=ROOT,capture_output=True,text=True)
        (OUT/f'{name}.log').write_text(run.stdout+run.stderr)
        if run.returncode:raise RuntimeError(run.stdout+run.stderr)
        results.setdefault('input_sha256',{})[name]={'rtl':hashlib.sha256(Path(files[1]).read_bytes()).hexdigest(),'testbench':hashlib.sha256(tb.read_bytes()).hexdigest()};results['models'][name]=run.stdout.strip();print(name,run.stdout.strip(),flush=True)
    path.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(coverage),flush=True)

if __name__=='__main__':main()
