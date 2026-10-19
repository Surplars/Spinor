"""Public ISA cases; actual instruction legality/state comes from upstream Spike."""
import random
def events_for():
    rng=random.Random(0x54ab16);events=[];ident=0
    def ins(name,raw,scalar=0,scalar2=0,avl=0,**meta):
        nonlocal ident
        events.append(dict(kind='I',id=ident,name=name,instruction=raw,scalar=scalar,scalar2=scalar2,avl=avl,category='half-conversion',**meta));ident+=1
    def csr(a,v):ins('csr',a<<20|1<<15|1<<12|3<<7|0x73,scalar=v)
    halves=[0,0x8000,1,0x3ff,0x400,0x3c00,0xbc00,0x7bff,0xfbff,0x7c00,0xfc00,0x7c01,0x7e00,0x7fff]
    singles=[0,0x80000000,1,0x007fffff,0x33800000,0x33000000,0x38800000,0x3f800000,0x3f801000,0x3f803000,0x477fe000,0x477ff000,0x7f800000,0x7f800001,0x7fc00000,0xff800001]
    legal=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
    def case(s,m,vl,rm,sub,vm=1,vd=8,src=16):
        typ=s<<3|m;ins('vsetvli',typ<<20|1<<15|7<<12|3<<7|0x57,avl=vl)
        csr(3,rm<<5|16);csr(15,5)
        for r in range(32):
            bits=16 if sub<16 else 32;pool=halves if bits==16 else singles
            value=sum(pool[(r*3+k+ident)%len(pool)]<<(bits*k) for k in range(128//bits))
            if r==0:value=int('a596'*8,16)
            events.append(dict(kind='R',register=r,data=value))
        ins('vfwcvt_f_f_v' if sub==12 else 'vfncvt_f_f_w' if sub==20 else 'other-conversion',
            0x12<<26|vm<<25|src<<20|sub<<15|1<<12|vd<<7|0x57,sew=8<<s,lmul=m,selector=sub,frm=rm)
    for s,m in legal:
        maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
        for length in [0,1,maximum]:
            for rm in range(8):
                for sub in [12,20]:case(s,m,length,rm,sub,vm=rm%2)
    for m in [0,1,2,3,6,7]:
        for sub in [12,20]:
            for vd,src,vm in [(8,16,0),(9,16,1),(8,17,1),(16,16,1),(8,9,1),(0,16,0)]:case(1,m,128,0,sub,vm,vd,src)
    # Zvfhmin must not enable other half operations, odd conversion or reserved selectors.
    for sub in [0,1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,21,22,23,24,31]:case(1,0,4,0,sub)
    for code in [0x00,0x24,0x2c]:
        ins('unsupported-half-arithmetic',code<<26|1<<25|16<<20|24<<15|1<<12|8<<7|0x57)
    return events
