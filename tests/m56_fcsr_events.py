"""Cases for a software CPU CSR owner and an unmodified Spike numeric oracle."""
import random
from test_spike_differential import catalog,encoded
from m55_zvbb_events import catalog as bit_catalog
M64=(1<<64)-1
def cases():
    tables,_=catalog();rng=random.Random(0x56fc51);out=[]
    def add(entry,s,m,rm,length=128,mutate=False,seedflags=None):
        i=len(out);bits=8<<s;mask=(1<<bits)-1
        values={8:[0,1,0x7f,0x80,0xff],16:[0,1,0x3c00,0xbc00,0x7bff,0x7c00,0x7c01,0xffff],
          32:[0,1,0x3f800000,0x33800000,0x7f800001,0x7fc00000,0x7f800000,0x7f7fffff,0xff800000,0xffffffff],
          64:[0,1,0x3ff0000000000000,0x3ca0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7ff0000000000000,0x7fefffffffffffff,M64]}
        regs=[sum(rng.choice(values[bits])<<(bits*k) for k in range(128//bits)) for _ in range(32)];regs[0]=int('a596'*8,16)
        raw=encoded(entry,vm=i%2)
        scalar=0xffffffff3f800001 if s==2 else 0xbff0000000000001
        if (raw>>12&7) not in [1,5]:scalar=[0,1,M64,1<<63,63][i%5]
        out.append(dict(name=entry['name'],instruction=raw,sew=8<<s,lmul=m,frm=rm,initial_flags=i%32 if seedflags is None else seedflags,
                        length=length,mutate=mutate,scalar=scalar,registers=regs,vcsr=i%8))
    entries=tables['v_alu_int']+tables['v_alu_fp']+bit_catalog()
    for s in range(4):
        for i,e in enumerate(entries):add(e,s,0,i%5,mutate=i%3==0)
    for s in [2,3]:
        for e in tables['v_alu_fp']:
            for rm in range(5):add(e,s,0,rm,mutate=True)
    wanted={'vfadd_vv','vfsub_vf','vfmul_vv','vfdiv_vv','vfsqrt_v','vfmacc_vv','vfclass_v','vfcvt_x_f_v',
            'vfcvt_rtz_x_f_v','vfwcvt_f_f_v','vfncvt_f_f_w','vfncvt_rod_f_f_w','vfwadd_vv','vfredosum_vs','vfwredosum_vs','vfrec7_v'}
    for s,m in [(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]:
        for e in tables['v_alu_fp']:
            if e['name'] in wanted:
                for rm in [0,4]:add(e,s,m,rm,mutate=True,seedflags=31)
    for e in tables['v_alu_fp']:
        if e['name'] in ['vfwcvt_f_f_v','vfncvt_f_f_w']:
            for rm in range(8):
                for vl in [0,1,4]:add(e,1,0,rm,vl,mutate=True,seedflags=31)
    # For reserved frm, compare only the implementation's common rejecting
    # arithmetic policy. RTZ/ROD and bit transfers may legally differ from Spike.
    for e in tables['v_alu_fp']:
        if e['name'] in ['vfadd_vv','vfmul_vv','vfdiv_vv','vfsqrt_v']:
            for rm in [5,6,7]:add(e,2,0,rm,mutate=True)
    return out

def fp_execution(raw):
    f3=raw>>12&7;f6=raw>>26;vm=raw>>25&1;vs1=raw>>15&31;vs2=raw>>20&31
    transfer=(f3==1 and f6==0x10 and vm and vs1==0) or (f3==5 and f6==0x10 and vm and vs2==0) or (f3==5 and f6 in [0xe,0xf]) or (f3==5 and f6==0x17 and (not vm or vs2==0))
    return f3 in [1,5] and not transfer
