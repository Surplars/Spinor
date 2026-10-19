#!/usr/bin/env python3
"""Independent integer arithmetic oracle plus exact-cycle elastic-pipeline model."""
import argparse,hashlib
import collections
import json
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "tools/oss-cad-suite/bin"
OUT = ROOT / "build/m55/lane"

def golden(a, b, sew, op, select):
    w = 8 << sew
    mask = (1 << w)-1
    a &= mask; b &= mask
    sa = a-(1 << w) if a >> (w-1) else a
    sb = b-(1 << w) if b >> (w-1) else b
    n = b & (w-1)
    if op==29:return a&~b&mask
    if op==30:return int.from_bytes(bytes(int(f'{x:08b}'[::-1],2) for x in a.to_bytes(w//8,'little')),'little')
    if op==31:return int(f'{a:0{w}b}'[::-1],2)
    if op==32:return int.from_bytes(a.to_bytes(w//8,'little'),'big')
    if op==33:return w-a.bit_length()
    if op==34:return (a&-a).bit_length()-1 if a else w
    if op==35:return a.bit_count()
    if op==36:return ((a<<n)|(a>>((-n)&(w-1))))&mask
    if op==37:return ((a>>n)|(a<<((-n)&(w-1))))&mask
    values = [a+b, a-b, a&b, a|b, a^b, a<<n, a>>n, sa>>n,
              min(sa,sb), min(a,b), max(sa,sb), max(a,b),
              int(a==b), int(a!=b), int(sa<sb), int(a<b), int(sa<=sb), int(a<=b),
              b, b if select else a]
    if op in [21,22,23,24]:
        x,y=(sa,sb) if op in [22,24] else (a,b)
        if y==0:q=-1;rem=x
        else:
            q=abs(x)//abs(y)
            if (x<0)!=(y<0):q=-q
            rem=x-q*y
        return (q if op in [21,22] else rem)&mask
    if op==20:return (a*b)&mask
    if op==25:return ((sa*sb)>>w)&mask
    if op==26:return ((a*b)>>w)&mask
    if op==27:return ((sa*b)>>w)&mask
    return values[op] & mask

def check(rows, trace, latency, reserved=False):
    pipe = [None]*latency
    fifo=collections.deque()
    accepted = retired = killed = stalls = 0
    for row, obs in zip(rows,trace,strict=True):
        iv, ready, flush, a,b,sew,op,select,tag = row
        _, cycle, ir, ov, data, otag = obs.split()
        occupied=sum(x is not None for x in pipe)+len(fifo)
        en = occupied < latency+2 if reserved else pipe[-1] is None or ready
        offered=fifo[0] if reserved and fifo else None if reserved else pipe[-1]
        assert int(ir) == int(en and not flush), (cycle,"ready")
        assert int(ov) == int(offered is not None and not flush), (cycle,"valid")
        if offered is not None and not flush:
            assert (int(data,16),int(otag)) == offered, (cycle,"data",data,offered)
            if ready: retired += 1
            else: stalls += 1
        if flush:
            killed += occupied
            pipe = [None]*latency
            fifo.clear()
        elif reserved or en:
            if reserved:
                if offered is not None and ready:fifo.popleft()
                if pipe[-1] is not None:fifo.append(pipe[-1])
            item = (golden(a,b,sew,op,select),tag) if iv and en else None
            if iv and en: accepted += 1
            pipe = [item]+pipe[:-1]
    assert not any(x is not None for x in pipe)
    assert not fifo
    assert accepted == retired+killed
    return dict(accepted=accepted,retired=retired,flushed=killed,output_stall_cycles=stalls)

def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
    if args.mapped:OUT=ROOT/'build/m55/lane-mapped'
    OUT.mkdir(parents=True,exist_ok=True);rng=random.Random(0x55bb15e6);rows=[]
    ops=list(range(20))+list(range(29,38))
    # Exhaust all byte inputs for each new unary/boolean/rotate selector.
    for op in range(29,38):
        for a in range(256):rows.append((1,1,0,a,255-a,0,op,0,len(rows)%256))
    for sew in range(4):
        w=8<<sew
        for op in ops:
            amounts=[0,1,w-1,w,w+1,63,64,127]
            for a in [0,(1<<w)-1,1,1<<(w-1),0xa5966a59a5966a59]:
                for b in amounts:rows.append((1,1,0,a,b,sew,op,op&1,len(rows)%256))
    if args.mapped:rows=rows[:2304]+rows[2304::8]
    for i in range(1000 if args.mapped else 12000):
        rows.append((int(rng.random()<.88),int(rng.random()<.65),int(rng.random()<.025),rng.getrandbits(64),rng.getrandbits(64),rng.randrange(4),rng.choice(ops),rng.randrange(2),i%256))
    rows += [(0,1,0,0,0,0,0,0,0)]*25
    fixtures=OUT/'lane.stim';fixtures.write_text(''.join(f'{iv} {rd} {fl} {a:x} {b:x} {s} {op} {sel} {tag}\n' for iv,rd,fl,a,b,s,op,sel,tag in rows))
    tb=OUT/'tb.sv';tb.write_text((ROOT/'tests/lane_tb.sv').read_text().replace('[4:0] io_in_bits_op','[5:0] io_in_bits_op').replace('build/test/lane.stim',str(fixtures.relative_to(ROOT))))
    result={};artifacts=[fixtures,tb];bin=ROOT/'tools/oss-cad-suite/bin'
    tops=[('IntegerLaneSplit',6),('IntegerLaneSplit16',7)]
    if not args.mapped:tops.insert(0,('IntegerLaneBaseline',2))
    for top,lat in tops:
        exe=OUT/top;rtl=ROOT/(f'build/m55/synth/{top}/mapped.v' if args.mapped else f'build/m55/rtl/{top}.sv')
        extra=[ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'] if args.mapped else []
        with (OUT/f'{top}.compile.log').open('w') as log:subprocess.run([str(bin/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}','-o',exe,tb,rtl,*extra],cwd=ROOT,stdout=log,stderr=log,check=True)
        with (OUT/f'{top}.trace').open('w') as log:subprocess.run([bin/'vvp',exe],cwd=ROOT,stdout=log,stderr=log,check=True,timeout=120)
        trace=[s for s in (OUT/f'{top}.trace').read_text().splitlines() if s.startswith('T ')]
        assert len(trace)==len(rows);result[top]=check(rows,trace,lat,top!='IntegerLaneBaseline')
        for field in [4,5]:
            bad=trace.copy();at=next(i for i,s in enumerate(bad) if s.split()[3]=='1');tokens=bad[at].split()
            tokens[field]=f'{int(tokens[field],16)^1:x}' if field==4 else str(int(tokens[field])^1);bad[at]=' '.join(tokens)
            try:check(rows,bad,lat,top!='IntegerLaneBaseline')
            except AssertionError:pass
            else:raise AssertionError('oracle accepted data/tag corruption')
        result[top]['corrupt_data_and_tag_rejected']=True
        artifacts.extend([exe,rtl,OUT/f'{top}.trace',OUT/f'{top}.compile.log',*extra])
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    d=dict(status='PASS',mapped=args.mapped,cycles_per_top=len(rows),exhaustive_byte_inputs=True,results=result,
       source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/lane_tb.sv']},
       artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (OUT/'results.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
