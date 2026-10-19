"""Independent opcode catalog from pinned Spike, plus public architectural cases."""
import re,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def catalog():
    src=next((ROOT/'tools/spike').glob('riscv-isa-sim-*'))/'riscv'
    make=(src/'riscv.mk.in').read_text();encoding=(src/'encoding.h').read_text()
    block=re.search(r'riscv_insn_ext_zvbb\s*=\s*\\\n(.*?)(?=\n\w+\s*[:?+]?=)',make,re.S)[1]
    names=re.findall(r'^\s*(\w+)\s*\\?$',block,re.M)
    entries=[dict(name=n,match=int(re.search(r'^#define MATCH_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16),
                  mask=int(re.search(r'^#define MASK_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16)) for n in names]
    assert len(entries)==16
    return entries

def encoded(e,vm=1,vd=8,src=16,operand=24):
    fields=vm<<25|src<<20|(operand&31)<<15|vd<<7
    if e['name']=='vror_vi':fields=(fields&~(31<<15))|((operand&31)<<15)|((operand>>5&1)<<26)
    return e['match']|(fields&~e['mask'])

def events_for():
    rng=random.Random(0x55bb128);events=[];ident=0;entries=catalog()
    def ins(name,raw,scalar=0,avl=0,**meta):
        nonlocal ident
        events.append(dict(kind='I',id=ident,name=name,instruction=raw,scalar=scalar&((1<<64)-1),scalar2=0,avl=avl,category='zvbb',**meta));ident+=1
    def case(e,s,m,length,vm=1,vd=8,src=16,operand=24,scalar=0,pattern=None):
        ins('vsetvli',(s<<3|m)<<20|1<<15|7<<12|3<<7|0x57,avl=length)
        ins('csr',15<<20|1<<15|1<<12|3<<7|0x73,scalar=ident%8)
        bits=8<<s;mask=(1<<bits)-1
        pool=[0,mask,1,1<<(bits-1),int('a5'*(bits//8),16),rng.getrandbits(bits)]
        for r in range(32):
            value=sum((pool[(r+k+ident)%len(pool)] if pattern is None else pattern&mask)<<(bits*k) for k in range(128//bits))
            if r==0:value=int('a596'*8,16)
            events.append(dict(kind='R',register=r,data=value))
        ins(e['name'],encoded(e,vm,vd,src,operand),scalar=scalar,sew=bits,lmul=m,vm=vm,operand=operand)
    legal=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
    for s,m in legal:
        maximum=((16>>s)<<m) if m<4 else (16>>s)>>(8-m)
        for e in entries:
            for i,length in enumerate([0,1,maximum]):case(e,s,m,length,vm=(ident+i)%2,scalar=[0,-1,63][i])
    # Operand boundaries, including vror.vi bit26 and zero/nonzero count anchors.
    for s in range(4):
        for e in entries:
            for i,amount in enumerate([0,1,7,15,31,32,63,64,127,(1<<64)-1]):
                operand=amount&63 if e['name']=='vror_vi' else amount&31 if e['name'].endswith('_vi') else 24
                case(e,s,0,16,vm=i%2,operand=operand,scalar=amount,pattern=[0,-1,1,1<<((8<<s)-1)][i%4])
    # Alignment, both source overlap edges, high-part widening overlap and v0 aliases.
    for e in entries:
        for m in [0,1,2,3,6,7]:
            for vd,src,operand,vm in [(16,16,24,1),(16,17,24,1),(24,16,24,1),(8,16,25,1),(9,16,24,1),(8,17,24,1),(0,16,24,0)]:
                case(e,1,m,128,vm,vd,src,operand,scalar=33)
    # Neighbour selectors are reserved; no accidental alias to extension or FP unary.
    for selector in [11,15,24,31]:
        ins('reserved-unary',0x12<<26|1<<25|16<<20|selector<<15|2<<12|8<<7|0x57)
    return events
