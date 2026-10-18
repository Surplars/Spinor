#!/usr/bin/env python3
"""Real RVV encodings, independent arch-state/SoftFloat oracle and commit checks."""
import argparse,hashlib
import json
from pathlib import Path
import random
import subprocess
from reference_fp import Reference
from test_vector import HEADER

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
MASK128=(1<<128)-1
# Hand-audited against the pinned rv_v encoding reference; not imported from RTL.
# name, funct6, oracle operation, comparison, unary selector (or -1)
OPS=[('vfadd',0x00,0,False,-1),('vfsub',0x02,1,False,-1),
     ('vfmin',0x04,9,False,-1),('vfmax',0x06,10,False,-1),
     ('vfsgnj',0x08,17,False,-1),('vfsgnjn',0x09,18,False,-1),('vfsgnjx',0x0a,19,False,-1),
     ('vmfeq',0x18,11,True,-1),('vmfle',0x19,14,True,-1),('vmflt',0x1b,13,True,-1),('vmfne',0x1c,12,True,-1),
     ('vfdiv',0x20,3,False,-1),('vfmul',0x24,2,False,-1),
     ('vfmadd',0x28,5,False,-1),('vfnmadd',0x29,8,False,-1),('vfmsub',0x2a,6,False,-1),('vfnmsub',0x2b,7,False,-1),
     ('vfmacc',0x2c,5,False,-1),('vfnmacc',0x2d,8,False,-1),('vfmsac',0x2e,6,False,-1),('vfnmsac',0x2f,7,False,-1),
     ('vfsqrt',0x13,4,False,0),('vfclass',0x13,20,False,16)]
EXTRA=[('vfrdiv',0x21,3,False,-1),('vfrsub',0x27,1,False,-1),('vmfgt',0x1d,15,True,-1),('vmfge',0x1f,16,True,-1)]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mapped',action='store_true');parser.add_argument('--top',choices=['RamVectorFp','RamVectorFp16'],default='RamVectorFp');parser.add_argument('--multiply',action='store_true');parser.add_argument('--divide',action='store_true');parser.add_argument('--convert',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);ref=Reference();rng=random.Random(0xf015e63)
    header=HEADER.replace('wire [4:0] io_vl;',
      'wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;')
    header=header.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','3000000')
    header=header.replace('reg [31:0] saved;','reg [31:0] saved, originalVersions;reg [4:0] originalFlags;reg [2:0] originalFrm;')
    header=header.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',
      'originalVersions=io_versions;originalFlags=io_fflags;originalFrm=io_frm;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;')
    guard='if(io_versions !== originalVersions || io_fflags !== originalFlags || io_frm !== originalFrm)$fatal(1,"FP state committed before acknowledgement");'
    header=header.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
    header=header.replace('repeat(stall) begin','repeat(stall) begin\n'+guard,1)
    context_flush_task='''task context_write_flush(input integer addr,input [63:0] value);
begin
io_context_valid=1;io_context_bits_write=1;io_context_bits_address=addr;io_context_bits_data=value;
#1;if(!io_context_ready)$fatal(1,"context write/flush start blocked");
tick();io_context_valid=0;io_flush=1;tick();io_flush=0;tick();
end endtask
'''
    header=header.replace('initial begin',context_flush_task+'initial begin',1)
    lines=[header];regs=[rng.getrandbits(128) for _ in range(32)]
    vl=0;vtype=1<<63;vstart=0;versions=0;frm=0;fflags=0;case=0
    coverage={'FP32':0,'FP64':0,'vf':0,'vv':0,'masked':0,'alias':0,'illegal':0,'flushes':0,
              'ops':{},'lmul_types':[],'rounding_modes':[],'csr':0,'integer_interleave':0,'context_write_flush':0}
    def ctx(r,write=False):
        for k in range(2):
            value=(regs[r]>>(64*k))&((1<<64)-1)
            lines.append(f"ctx({2*r+k},1'b{int(write)},64'h{value:x},64'h{value:x});")
    def state_check():
        lines.append(f'if(io_fflags !== 5\'d{fflags} || io_frm !== 3\'d{frm} || io_vstart !== 7\'d{vstart} || '
          f'io_versions !== 32\'h{versions:x})$fatal(1,"FP architectural state case {case} flags=%h map=%h",io_fflags,io_versions);')
    def command(inst,scalar=0,avl=0,value=0,writes=False,illegal=False):
        nonlocal case
        lines.append(f"command(32'h{inst:08x},64'h{scalar&((1<<64)-1):x},0,64'h{avl:x},80'h{((0xf032<<64)|case):x},"
          f"1'b{int(illegal)},64'h{value:x},1'b{int(writes)},{rng.randrange(8)},8'd{vl},64'h{vtype:x});")
        case+=1;coverage['illegal']+=int(illegal);state_check()
    def config(t,length):
        nonlocal vl,vtype,vstart
        enc=t&7;s=(t>>3)&7
        limit=((16>>s)<<enc) if enc<=3 else ((16>>s)>>(8-enc))
        vl=min(length,limit);vtype=t;vstart=0
        command((t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,avl=length,value=vl,writes=True)
    def csr(address,value=0,action=1,rs=1,rd=3,illegal=False):
        nonlocal fflags,frm,vstart
        old={1:fflags,2:frm,3:(frm<<5)|fflags,8:vstart}.get(address,0)
        source=rs if action&4 else value;mode=action&3
        new=source if mode==1 else old|source if mode==2 else old&~source
        write=mode==1 or rs!=0 and mode!=0
        if write and not illegal:
            if address==1:fflags=new&31
            if address==2:frm=new&7
            if address==3:fflags=new&31;frm=(new>>5)&7
            if address==8:vstart=new&127
        command((address<<20)|(rs<<15)|(action<<12)|(rd<<7)|0x73,scalar=value,
          value=0 if illegal else old,writes=rd!=0 and not illegal,illegal=illegal)
        coverage['csr']+=1
    def group(r,n):return sum(regs[r+k]<<(128*k) for k in range(n))
    def vector(desc,vd,vs2,vs1,vm=1,scalar=None,illegal=False):
        nonlocal versions,fflags,vstart
        name,f6,op,comparison,unary=desc
        vf=scalar is not None;f3=5 if vf else 1
        rs=unary if unary>=0 else vs1
        illegal=illegal or (not vm and (vs2==0 or (not vf and unary<0 and vs1==0)))
        inst=(f6<<26)|(vm<<25)|(vs2<<20)|(rs<<15)|(f3<<12)|(vd<<7)|0x57
        w=8<<((vtype>>3)&7);n=(1<<(vtype&7)) if (vtype&7)<=3 else 1
        dc=1 if comparison else n
        if not illegal:
            a=group(vs2,n);b=group(vs1,n) if not vf and unary<0 else 0
            dest=group(vd,dc);old=dest;mask=regs[0];ew=(1<<w)-1
            for e in range(vstart,vl):
                if not vm and not (mask>>e)&1:continue
                x=(a>>(e*w))&ew
                if vf:y=scalar if w==64 or scalar>>32==0xffffffff else 0x7fc00000
                else:y=(b>>(e*w))&ew
                z=(old>>(e*w))&ew
                if 0x28<=f6<=0x2b:x,z=z,x
                if vf and f6 in [0x21,0x27]:x,y=y,x
                value,flags=ref(op,w==64,frm,x,y,z)
                fflags|=flags
                if comparison:dest=(dest&~(1<<e))|((value&1)<<e)
                else:dest=(dest&~(ew<<(e*w)))|((value&ew)<<(e*w))
            if vl>vstart:
                for k in range(dc):regs[vd+k]=(dest>>(128*k))&MASK128
                versions^=((1<<dc)-1)<<vd
            vstart=0
        command(inst,scalar=scalar or 0,illegal=illegal)
        coverage['ops'][name]=coverage['ops'].get(name,0)+1
        coverage['FP64' if w==64 else 'FP32']+=1
        coverage['vf' if vf else 'vv']+=1;coverage['masked']+=int(not vm)
        coverage['alias']+=int(vd==vs2 or not vf and unary<0 and vd==vs1)
        for k in range(dc):ctx(vd+k)
    for r in range(32):ctx(r,True)
    # All FCSR CSR forms, source-index write rules, and aliases.
    for a in [1,2,3]:
        for action in [1,2,3,5,6,7]:csr(a,rng.getrandbits(64),action,rs=rng.randrange(1,32))
        csr(a,action=2,rs=0);csr(a,action=3,rs=0)
    csr(3,0)
    types=[(s<<3)|m for s in [2,3] for m in [0,1,2,3,7] if m<=3 or s<=m-5]
    coverage['lmul_types']=types;coverage['rounding_modes']=[0,1,2,3,4]
    for t in types:
        w=8<<((t>>3)&7);n=1<<(t&7) if (t&7)<=3 else 1
        one=0x3ff0000000000000 if w==64 else 0x3f800000
        inf=0x7ff0000000000000 if w==64 else 0x7f800000
        sign=1<<(w-1);quiet=1<<(51 if w==64 else 22)
        values=[one,inf|1,0,one|sign,1,inf-1,inf|quiet,sign,one+1,one-2,inf]
        for base in [8,16]:
            for k in range(n):
                regs[base+k]=sum(values[(k*4+j+base)%len(values)]<<(w*j) for j in range(128//w));ctx(base+k,True)
        for rm in range(5):
            csr(3,rm<<5)
            config(t|0xc0,(128//w)*n)
            for j,desc in enumerate(OPS+EXTRA):
                if j%9==8:config(t|0x40,rng.randrange((128//w)*n+1))
                if j%7==6:csr(8,rng.randrange(min(128,vl+3)))
                vf=desc in EXTRA or desc[4]<0 and rng.randrange(2)==1
                vm=rng.randrange(2)
                s2=rng.choice([8,16,24]);s1=rng.choice([8,16,24])
                if desc[3]:
                    choices=[d for d in range(32) if not(s2<d<s2+n) and not(not vf and s1<d<s1+n)]
                else:choices=[d for d in range(0,32,n) if vm or d!=0]
                d=rng.choice(choices)
                scalar=rng.choice(values)
                if w==32:
                    scalar|=(0xffffffff if rng.randrange(6) else 0x12345678)<<32
                vector(desc,d,s2,s1,vm,scalar if vf else None)
    # Known active-mask/tail/prestart flag behavior, with zero divisor and sNaN.
    for w in [32,64]:
        t=(2 if w==32 else 3)<<3;one=0x3f800000 if w==32 else 0x3ff0000000000000
        snan=0x7f800001 if w==32 else 0x7ff0000000000001
        config(t,2);csr(3,0)
        regs[8]=one|(snan<<w);regs[16]=0;regs[0]=1
        for r in [0,8,16]:ctx(r,True)
        vector(OPS[11],24,8,16,0) # only 1/0 active -> DZ, no NV from masked sNaN
        assert fflags==8
        csr(1,0);csr(8,1);vector(OPS[11],24,8,16,0);assert fflags==0
        regs[0]=0;ctx(0,True);vector(OPS[11],24,8,16,0);assert fflags==0
        config(t,1);vector(OPS[11],24,8,16,1);assert fflags==8
        config(t,0);csr(1,0);vector(OPS[11],24,8,16,1);assert fflags==0
        if w==32:
            config(t,1);regs[8]=one;ctx(8,True)
            vector(OPS[0],24,8,0,1,scalar=0x123456787f800001);assert fflags==0
    # Illegal rounding / SEW / forms are precise and leave flags/data unchanged.
    config(2<<3,4)
    for rm in [5,6,7]:
        csr(2,rm);vector(OPS[0],24,8,16,illegal=True)
    csr(2,0)
    for t in [0,8]:config(t,1);vector(OPS[0],24,8,16,illegal=True)
    config(2<<3,4)
    vector(EXTRA[2],24,8,16,illegal=True) # no vmfgt.vv encoding
    vector(('bad-unary',0x13,4,False,1),24,8,0,illegal=True)
    config((2<<3)|1,8);vector(OPS[0],24,9,16,illegal=True)
    # Interleave integer instructions with live FP flags; no accidental FP accrual.
    config(2<<3,4);csr(1,0x1b)
    old=regs[8];src=regs[16];regs[24]=sum((((old>>(32*k))+(src>>(32*k)))&0xffffffff)<<(32*k) for k in range(4))
    versions^=1<<24
    command((1<<25)|(8<<20)|(16<<15)|(24<<7)|0x57);ctx(24);coverage['integer_interleave']+=1
    if args.multiply:
        coverage['multiply_interleave']=0
        for code,signedA,signedB,high in [(0x25,False,False,False),(0x27,True,True,True),
                                       (0x24,False,False,True),(0x26,True,False,True)]:
            for form in [2,6]:
                scalar=rng.getrandbits(64);answer=0
                for k in range(4):
                    x=(regs[8]>>(32*k))&0xffffffff
                    y=((regs[16]>>(32*k)) if form==2 else scalar)&0xffffffff
                    if signedA and x>>31:x-=1<<32
                    if signedB and y>>31:y-=1<<32
                    z=((x*y)>>32 if high else x*y)&0xffffffff
                    answer|=z<<(32*k)
                regs[24]=answer;versions^=1<<24
                inst=(code<<26)|(1<<25)|(8<<20)|(16<<15)|(form<<12)|(24<<7)|0x57
                command(inst,scalar=scalar);ctx(24);coverage['multiply_interleave']+=1
                vector(OPS[0],24,8,16) # same destination switches back to FP
    if args.divide:
        coverage['divide_interleave']=0
        for code,signed,remainder in [(0x20,False,False),(0x21,True,False),(0x22,False,True),(0x23,True,True)]:
            for form in [2,6]:
                scalar=rng.getrandbits(64);answer=0
                for k in range(4):
                    x=(regs[8]>>(32*k))&0xffffffff
                    y=((regs[16]>>(32*k)) if form==2 else scalar)&0xffffffff
                    if signed and x>>31:x-=1<<32
                    if signed and y>>31:y-=1<<32
                    if y==0:q=-1;rem=x
                    else:
                        q=abs(x)//abs(y)
                        if (x<0)!=(y<0):q=-q
                        rem=x-q*y
                    answer|=((rem if remainder else q)&0xffffffff)<<(32*k)
                regs[24]=answer;versions^=1<<24
                inst=(code<<26)|(1<<25)|(8<<20)|(16<<15)|(form<<12)|(24<<7)|0x57
                command(inst,scalar=scalar);ctx(24);coverage['divide_interleave']+=1
                vector(OPS[0],24,8,16)
    if args.convert:
        coverage['conversions']=0
        conversions=[('vfcvt.xu.f',0x12,21,False,0),('vfcvt.x.f',0x12,22,False,1),
                     ('vfcvt.f.xu',0x12,23,False,2),('vfcvt.f.x',0x12,24,False,3),
                     ('vfcvt.rtz.xu.f',0x12,25,False,6),('vfcvt.rtz.x.f',0x12,26,False,7)]
        for t in types:
            w=8<<((t>>3)&7);n=1<<(t&7) if (t&7)<=3 else 1
            for base in [8,16]:
                for k in range(n):regs[base+k]=rng.getrandbits(128);ctx(base+k,True)
            for rm in range(5):
                csr(3,rm<<5);config(t,(128//w)*n)
                for j,desc in enumerate(conversions):
                    if j%3==0:csr(8,min(1,vl))
                    vector(desc,8 if j%2 else 24,8,0,vm=j%2)
                    coverage['conversions']+=1
        config(2<<3,2)
        for rm in [5,6,7]:
            csr(2,rm)
            for desc in conversions:
                vector(desc,24,8,0,illegal=desc[2]<25)
        csr(2,0)
        for desc in [('reserved-convert',0x12,21,False,4),('reserved-convert-13',0x12,21,False,13)]:
            vector(desc,24,8,0,illegal=True)
        convinst=(0x12<<26)|(1<<25)|(8<<20)|(2<<15)|(1<<12)|(24<<7)|0x57
        for delay in list(range(90))+[100,140,180]:
            lines.append(f"cancel(32'h{convinst:x},{delay},0);");coverage['flushes']+=1;state_check();ctx(24)
        lines.append(f"cancel(32'h{convinst:x},0,1);");coverage['flushes']+=1;state_check();ctx(24)
        vector(conversions[2],24,8,0)
    # Flush after flags/results are produced, during iterative divide, and at reply.
    config(2<<3,4);regs[8]=sum(0x3f800000<<(32*k) for k in range(4));regs[16]=0
    for r in [8,16]:ctx(r,True)
    csr(3,0)
    divinst=(0x20<<26)|(1<<25)|(8<<20)|(16<<15)|(1<<12)|(24<<7)|0x57
    for delay in list(range(96))+[100,160]:
        lines.append(f"cancel(32'h{divinst:x},{delay},0);");coverage['flushes']+=1;state_check();ctx(24)
    lines.append(f"cancel(32'h{divinst:x},0,1);");coverage['flushes']+=1;state_check();ctx(24)
    for address in [1,2,3]:
        inst=(address<<20)|(1<<15)|(1<<12)|(3<<7)|0x73
        lines.append(f"cancel(32'h{inst:x},0,1);");coverage['flushes']+=1;state_check()
    vector(OPS[11],24,8,16,1) # aborted candidate data/flags cannot leak into next owner
    # Context writes are already architectural on fire. A later flush must not
    # discard an accepted write even when candidate writes use another stage.
    for chunk in range(2):
        value=rng.getrandbits(64)
        regs[31]=(regs[31]&~(((1<<64)-1)<<(64*chunk)))|(value<<(64*chunk))
        lines.append(f"context_write_flush({62+chunk},64'h{value:x});")
        coverage['context_write_flush']+=1
        state_check()
    ctx(31)
    for r in range(32):ctx(r)
    lines.append('$display("PASS fp-vector commands=%0d reads=%0d cycles=%0d",cmds,reads,cycles);$finish;end endmodule\n')
    stem='fp-vector-m9-convert' if args.convert else 'fp-vector-m7-mixed' if args.divide else 'fp-vector-multiply' if args.multiply else 'fp-vector'
    stem+=('-16' if args.top.endswith('16') else '')
    tb=OUT/(stem+'-tb.sv');tb.write_text('\n'.join(lines));name=stem+'-mapped' if args.mapped else stem
    exe=OUT/name
    rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv')
    files=[str(tb),str(rtl)]
    assertion_tops=[]
    assertions=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
    if not args.mapped and assertions.exists():
        # Chisel 7 emits assertions as a separate verification layer. Attach
        # that layer to this testbench's actual DUT hierarchy for Icarus.
        monitor=OUT/(args.top+'-fp-vector-write-stage-assertions.sv')
        monitor.write_text(assertions.read_text().replace(args.top+'.','tb.dut.'))
        files.append(str(monitor))
        assertion_tops=['-s',args.top+'_Verification_Assert']
    if args.mapped:files += [str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'),
        str(ROOT/'third_party/xilinx-unisim/DSP48E2.v'),str(ROOT/'tests/fp_mapped_global.sv')]
    with (OUT/(name+'.compile.log')).open('w') as log:
        tops=['-s','tb']+(['-s','glbl'] if args.mapped else [])+assertion_tops
        subprocess.run([str(BIN/'iverilog'),'-g2012']+tops+[f'-DTOP={args.top}','-o',str(exe)]+files,stdout=log,stderr=log,check=True)
    run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True,cwd=ROOT)
    (OUT/(name+'.log')).write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError(run.stdout+run.stderr)
    assert 'PASS fp-vector' in run.stdout
    result={'rtl_or_netlist_sha256':hashlib.sha256(rtl.read_bytes()).hexdigest(),'testbench_sha256':hashlib.sha256(tb.read_bytes()).hexdigest(),'status':'PASS','mapped':args.mapped,'commands':case,'coverage':coverage,
            'write_stage_assertions_enabled':bool(assertion_tops),
            'known_answer_anchors':ref.anchors,'test_summary':run.stdout.strip()}
    (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
