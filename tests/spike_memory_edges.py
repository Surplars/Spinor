#!/usr/bin/env python3
"""Deterministic architectural LSU boundaries, independent of DUT decode code."""
import random
from test_spike_memory import BASE,N,M64

def events_for(entries):
    catalog={e['name']:e for e in entries};events=[];ident=0;rng=random.Random(0x52ed12864)
    def instruction(name,raw,scalar=0,scalar2=0,avl=0,**metadata):
        nonlocal ident
        events.append(dict(kind='I',id=ident,name=name,instruction=raw,scalar=scalar&M64,scalar2=scalar2&M64,avl=avl,**metadata));ident+=1
    def configure(s,m=0,avl=3):instruction('vsetvli',((s<<3|m)<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,avl=avl,sew=8<<s,lmul=m)
    def start(value):instruction('vstart',(8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value)
    def fixture(mask=(1<<128)-1,index_width=1,index_step=0):
        events.extend([dict(kind='M',data=bytes((i*13+7)&255 for i in range(N)).hex()),dict(kind='F',address=0,length=0)])
        for reg in range(32):
            value=rng.getrandbits(128)
            if reg==0:value=mask
            if reg>=24:
                first=(reg-24)*16//index_width
                value=sum((((first+k)*index_step)% (1<<(8*index_width)))<<(8*index_width*k) for k in range(16//index_width))
            events.append(dict(kind='R',register=reg,data=value))
    def encoding(name,nf=1,vm=1,vr=8,index=24,stride_reg=2):
        e=catalog[name];raw=e['match'];mode=raw>>26&3
        bits=(nf-1)<<29|vm<<25|1<<15|vr<<7
        if mode in [1,3]:bits|=index<<20
        if mode==2:bits|=stride_reg<<20
        return raw|bits&~e['mask']
    def fault_case(name,s,nf,element,field,vm=1,mask=(1<<128)-1,vstart=0,category='segment-field-fault'):
        raw=encoding(name,nf,vm);mode=raw>>26&3;width=1<<s
        # Indexed variants use byte indices; data width is SEW. Non-unit modes
        # leave a gap between segments, making field and element errors distinct.
        step=nf*width*(2 if mode else 1);stride=step
        fixture(mask,1,step);configure(s)
        if vstart:start(vstart)
        fault=BASE+1024+element*step+field*width
        events.append(dict(kind='F',address=fault,length=width))
        metadata=dict(category=category,nf=nf,sew=8<<s,fault_element=element,fault_field=field,masked=not vm,initial_vstart=vstart)
        instruction(name+'-fault',raw,BASE+1024,stride,**metadata)
        events.append(dict(kind='F',address=0,length=0))
        instruction(name+'-retry',raw,BASE+1024,stride,**metadata)
    # Every field in every NF2..8, element0/later, all data widths. Normal
    # unit loads/stores and FOF are independent encodings in upstream Spike.
    for s in range(4):
        for nf in range(2,9):
            for prefix in ['vle','vse','fof']:
                name=f'vle{8<<s}ff_v' if prefix=='fof' else f'{prefix}{8<<s}_v'
                for element in [0,1]:
                    for field in range(nf):fault_case(name,s,nf,element,field)
    # Addressed segments: every field, every NF, two element positions, SEW32;
    # 8-bit indices exercise independent data/index EEW and fractional EMUL.
    for name in ['vlse32_v','vsse32_v','vluxei8_v','vloxei8_v','vsuxei8_v','vsoxei8_v']:
        for nf in range(2,9):
            for element in [0,1]:
                for field in range(nf):fault_case(name,2,nf,element,field,category='addressed-field-fault')
    # Masked-off faults, first active element after zero, and nonzero restart.
    for s in range(4):
        for nf in [1,2,3,4,8]:
            for prefix in ['vle','vse','fof']:
                name=f'vle{8<<s}ff_v' if prefix=='fof' else f'{prefix}{8<<s}_v'
                for mask,element,vstart in [(0,0,0),(0b101,1,0),(0b110,1,0),((1<<128)-1,1,1)]:
                    fault_case(name,s,nf,element,nf-1,0,mask,vstart,'mask-and-restart')
    # The full canonical catalogue at empty and maximum VL, plus AVL>VLMAX.
    # No copied DUT decoder determines legality; Spike executes every raw word.
    types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
    for s,m in types:
        exponent=m if m<4 else m-8
        maximum=(16>>s)*(1<<exponent) if exponent>=0 else (16>>s)//(1<<-exponent)
        for avl in sorted({0,maximum,maximum+1}):
            fixture(mask=int('a596'*8,16));configure(s,m,avl)
            for e in entries:instruction(e['name'],encoding(e['name'],vm=0 if e['mask']&(1<<25)==0 else 1),BASE+2048,16,category='vl-boundary',sew=8<<s,lmul=m,avl_requested=avl)
    # Negative/zero stride and rs2=x0, with nonzero vstart. Indexed order may
    # have duplicate byte offsets; the current DUT serializes all accesses.
    for s in range(4):
        for nf in [1,2,3,4,8]:
            for store in [False,True]:
                name=('vsse' if store else 'vlse')+str(8<<s)+'_v'
                for stride in [-2*nf*(1<<s),0,2*nf*(1<<s)]:
                    for rs2 in [0,2]:
                        fixture();configure(s);start(1)
                        instruction(name,encoding(name,nf,stride_reg=rs2),BASE+4096,stride,category='stride-restart',nf=nf,sew=8<<s,rs2=rs2)
    # Whole-register transfers operate under vill; mask accesses must reject it.
    for e in entries:
        special=(e['match']>>26&3)==0 and (e['match']>>20&31) in [8,11]
        if not special:continue
        for value in [0,1,15,127]:
            fixture();configure(4,0,0);start(value)
            instruction(e['name'],encoding(e['name']),BASE+1024,category='special-vill',initial_vstart=value)
    # Reserved and overlap checks at VL0 and after start has passed the body.
    for avl,vstart in [(0,0),(3,3)]:
        for nf in [1,2,3,4,8]:
            for load in [True,False]:
                for same_width in ([True,False] if load else [True]):
                    # Cross-EEW store-source aliases are reserved by Vector
                    # Operands; Spike executes them. The existing normative
                    # directed oracle checks DUT rejection separately.
                    fixture();configure(2,0,avl);start(vstart)
                    name=('vluxei' if load else 'vsuxei')+('32' if same_width else '8')+'_v'
                    instruction(name,encoding(name,nf,index=8),BASE+2048,category='index-overlap',nf=nf,index_alias=True)
        for name,changes in [('vle32_v',1<<28),('vse32_v',1<<28),('vlm_v',1<<25),('vsm_v',1<<25),('vl2re8_v',1<<29),('vs1r_v',5<<12)]:
            fixture();configure(2,0,avl);start(vstart)
            instruction(name+'-reserved',encoding(name)^changes,BASE+2048,category='reserved-encoding')
    return events

def bounded_events_for(entries):
    """Same deterministic subset for an independent SV-driver cross-check."""
    blocks=[]
    for event in events_for(entries):
        if event['kind']=='M':blocks.append([])
        blocks[-1].append(event)
    selected=[]
    for block in blocks:
        keep=False
        for e in block:
            if e['kind']!='I':continue
            category=e.get('category');nf=e.get('nf');sew=e.get('sew')
            if category in ['segment-field-fault','addressed-field-fault'] and nf==3 and sew==32 and e.get('fault_element')==1:keep=True
            if category=='mask-and-restart' and nf==3 and sew==32:keep=True
            if category=='vl-boundary' and ((sew==8 and e.get('lmul')==3 and e.get('avl_requested')==129) or (sew==64 and e.get('lmul')==0 and e.get('avl_requested')==3)):keep=True
            if category=='stride-restart' and nf==3 and sew==32:keep=True
            if category=='special-vill' and e.get('initial_vstart')==127:keep=True
        if keep:selected+=block
    for ident,e in enumerate(e for e in selected if e['kind']=='I'):e['id']=ident
    return selected
