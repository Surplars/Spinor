"""Independent typed-register interval rules and snapshot element semantics.

No RTL selector numbers or group Boolean equations are imported. FP comes from
separately compiled Berkeley SoftFloat; integer arithmetic uses Python integers.
"""
from fractions import Fraction
from m57_isa_catalog import catalog
from reference_fp import Reference
from reference_fp_resize_m54 import ResizeReference

M128=(1<<128)-1
DESCRIPTORS={
 'vadd_vv':(0,0,0,'add'), 'vmseq_vv':('mask',0,0,'eq'),
 'vwaddu_vv':(1,0,0,'add'), 'vwadd_vv':(1,0,0,'signed-add'),
 'vwaddu_wv':(1,1,0,'add'), 'vwmulu_vv':(1,0,0,'mul'),
 'vwmaccu_vv':(1,0,0,'mac'), 'vnsrl_wv':(0,1,0,'srl'),
 'vnclipu_wv':(0,1,0,'clipu'),
 **{f'v{kind}ext_vf{factor}':(0,-(factor.bit_length()-1),None,'sext' if kind=='s' else 'zext') for kind in ('s','z') for factor in (2,4,8)},
 'vfadd_vv':(0,0,0,'fp-add'), 'vfmacc_vv':(0,0,0,'fp-mac'),
 'vfwadd_vv':(1,0,0,'fp-add'), 'vfwadd_wv':(1,1,0,'fp-add'),
 'vfwmacc_vv':(1,0,0,'fp-mac'),
 'vfwcvt_f_f_v':(1,0,None,'fp-wide'), 'vfncvt_f_f_w':(0,1,None,'fp-narrow'),
 'vrgather_vv':(0,0,0,'gather'), 'vrgatherei16_vv':(0,0,'index16','gather'),
 'vslideup_vx':(0,0,None,'slide-up'), 'vslidedown_vx':(0,0,None,'slide-down'),
}
ENTRIES={e['name']:e for e in catalog() if e['name'] in DESCRIPTORS}
assert set(ENTRIES)==set(DESCRIPTORS) and len(ENTRIES)==26
LAYOUTS=[(8,16,24),(8,8,24),(8,9,24),(8,12,24),(8,15,24),(16,8,24),
         (9,8,24),(8,16,8),(8,16,16),(0,16,24),(8,0,24),(8,16,0),
         (31,16,24),(8,31,24),(8,16,25),(24,16,24)]


def groups(c):
    w=c['sew'];lm=Fraction(2**c['lmul']) if c['lmul']<4 else Fraction(1,2**(8-c['lmul']))
    ds,a,b,op=DESCRIPTORS[c['name']]
    def group(base,shift):
        if shift=='mask':return dict(base=base,width=1,emul=Fraction(1),count=1,role='mask')
        width=16 if shift=='index16' else w*2**shift if shift>=0 else w//2**-shift
        emul=lm*Fraction(width,w);count=max(1,(emul.numerator+emul.denominator-1)//emul.denominator)
        return dict(base=base,width=width,emul=emul,count=count,role='data')
    dest=group(c['vd'],ds);sources=[group(c['vs2'],a)]
    if b is not None:sources.append(group(c['vs1'],b))
    if op in ('mac','fp-mac'):sources.append(dict(dest))
    if c['vm']==0:sources.append(group(0,'mask'))
    return dest,sources


def overlaps(a,b):
    return max(a['base'],b['base'])<min(a['base']+a['count'],b['base']+b['count'])


def reasons(c):
    d,sources=groups(c);op=DESCRIPTORS[c['name']][3];bad=[]
    for g in [d,*sources]:
        if g['role']!='mask' and not (8<=g['width']<=64 and Fraction(1,8)<=g['emul']<=8):bad.append('geometry')
        if g['base']%g['count'] or g['base']+g['count']>32:bad.append('alignment-range')
    if c['name'].startswith('vf'):
        allowed=(16,32) if op in ('fp-wide','fp-narrow') else (32,) if DESCRIPTORS[c['name']][0]==1 else (32,64)
        if c['sew'] not in allowed:bad.append('fp-width')
    for i,a in enumerate(sources):
        for b in sources[i+1:]:
            if a['width']!=b['width'] and overlaps(a,b):bad.append('source-eew')
    for s in sources:
        if not overlaps(d,s):continue
        if d['width']==s['width']:continue
        if d['width']<s['width'] and d['base']==s['base']:continue
        if d['width']>s['width'] and s['emul']>=1 and d['base']+d['count']==s['base']+s['count']:continue
        bad.append('destination-overlap')
    if c['vm']==0 and d['role']!='mask' and d['base']==0:bad.append('mask-destination')
    if op=='gather' and any(overlaps(d,s) for s in sources if s['role']!='mask'):bad.append('gather-overlap')
    if op=='slide-up' and overlaps(d,sources[0]):bad.append('slide-up-overlap')
    return sorted(set(bad))


def signed(x,w):return x-(1<<w) if x>>(w-1) else x


def rounded(x,d,rm):
    q,r=divmod(x,1<<d)
    if not d:return q
    h=1<<(d-1)
    inc=(r>=h) if rm==0 else (r>h or r==h and q&1) if rm==1 else (r!=0 and q&1==0) if rm==3 else False
    return q+int(inc)


class Model:
    def __init__(self):self.fp=Reference();self.resize=ResizeReference()
    def execute(self,c):
        bad=reasons(c)
        if bad:return dict(registers=list(c['registers']),fflags=c['flags'],vxsat=c['vcsr']&1,vstart=c['start'],illegal=1,reasons=bad)
        d,src=groups(c);op=DESCRIPTORS[c['name']][3];w=c['sew'];ow=d['width'];mask=(1<<ow)-1
        snapshot=sum(v<<(128*r) for r,v in enumerate(c['registers']));output=snapshot
        def read(base,index,bits):return (snapshot>>(base*128+index*bits))&((1<<bits)-1)
        flags=c['flags'];sat=c['vcsr']&1
        def widened(x,bits):
            if bits==64:return x,0
            assert bits==32
            return self.resize(28,1,True,c['frm'],x)
        for i in range(c['start'],c['vl']):
            if not c['vm'] and not(c['registers'][0]>>i&1):continue
            a=read(c['vs2'],i,src[0]['width'])
            b=read(c['vs1'],i,src[1]['width']) if DESCRIPTORS[c['name']][2] is not None else c['scalar']
            z=read(c['vd'],i,ow);f=0
            if op=='add':v=a+b
            elif op=='signed-add':v=signed(a,w)+signed(b,w)
            elif op=='eq':v=int(a==b)
            elif op=='mul':v=a*b
            elif op=='mac':v=a*b+z
            elif op=='srl':v=a>>(b&(2*w-1))
            elif op=='clipu':
                v=rounded(a,b&(2*w-1),(c['vcsr']>>1)&3);sat|=int(v>mask);v=min(mask,v)
            elif op=='sext':v=signed(a,src[0]['width'])
            elif op=='zext':v=a
            elif op in ('fp-add','fp-mac'):
                if ow==64:
                    a,fa=widened(a,src[0]['width']);b,fb=widened(b,w);f|=fa|fb
                v,ff=self.fp(5 if op=='fp-mac' else 0,ow==64,c['frm'],a,b,z);f|=ff
            elif op in ('fp-wide','fp-narrow'):
                mode=(1 if op=='fp-wide' else 2)|(4 if w==16 else 0)
                v,f=self.resize(28,mode,ow==64,c['frm'],a)
            elif op=='gather':v=read(c['vs2'],b,w) if b<c['maximum'] else 0
            elif op=='slide-up':
                if i<c['scalar']:continue
                v=read(c['vs2'],i-c['scalar'],w)
            elif op=='slide-down':
                idx=i+c['scalar'];v=read(c['vs2'],idx,w) if idx<c['maximum'] else 0
            else:raise AssertionError(op)
            flags|=f;position=c['vd']*128+i*ow
            output=(output&~(mask<<position))|((v&mask)<<position)
        return dict(registers=[(output>>(128*r))&M128 for r in range(32)],fflags=flags,vxsat=sat,vstart=0,illegal=0,reasons=[])


def cases(sew):
    s=(sew//8).bit_length()-1;seq=0
    for m in (0,1,2,3,5,6,7):
        if m>=4 and s>m-5:continue
        maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
        for name,e in ENTRIES.items():
            for layout,(vd,a,b) in enumerate(LAYOUTS):
                for profile,(start,vm,length) in enumerate([(0,1,maximum),(1,0,maximum),(min(2,maximum),1,maximum),(127,0,maximum),(1,0,0)]):
                    regs=[]
                    for r in range(32):
                        pool={8:[0,1,127,128,255,33],16:[0,1,0x7fff,0x8000,0xffff,0x3c01],
                              32:[0,1,0x3f800001,0x80000000,0x7f800001,0x7f7fffff,0xffffffff],
                              64:[0,1,0x3ff0000000000001,0x8000000000000000,0x7ff0000000000001,0x7fefffffffffffff,(1<<64)-1]}[sew]
                        regs.append(sum(pool[(r+k+layout+profile+seq)%len(pool)]<<(sew*k) for k in range(128//sew)))
                    regs[0]=int('a596'*8,16) if profile!=3 else 0
                    rs1=1 if DESCRIPTORS[name][3] in ('slide-up','slide-down') else b
                    raw=e['match']|((vm<<25|a<<20|rs1<<15|vd<<7)&~e['mask'])
                    yield dict(name=name,instruction=raw,sew=sew,lmul=m,vd=vd,vs2=a,vs1=b,vm=(raw>>25)&1,
                               vl=length,maximum=maximum,start=start,scalar=1,frm=(layout+profile)%5,flags=0,
                               vcsr=((layout%4)<<1),vtype=(s<<3)|m|((profile%4)<<6),registers=regs,profile=profile,layout=layout)
                    seq+=1
