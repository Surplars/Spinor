#!/usr/bin/env python3
"""Independent integer arithmetic oracle plus exact-cycle elastic-pipeline model."""
import collections
import json
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "tools/oss-cad-suite/bin"
OUT = ROOT / "build/test"

def golden(a, b, sew, op, select):
    w = 8 << sew
    mask = (1 << w)-1
    a &= mask; b &= mask
    sa = a-(1 << w) if a >> (w-1) else a
    sb = b-(1 << w) if b >> (w-1) else b
    n = b & (w-1)
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
    OUT.mkdir(parents=True,exist_ok=True)
    rng=random.Random(0x15e62)
    rows=[]
    for sew in range(4):
        w=8<<sew
        for op in range(20):
            for a,b in [(0,0),((1<<w)-1,1),(1<<(w-1),(1<<w)-1),((1<<w)-1,(1<<w)-1)]:
                rows.append((1,1,0,a,b,sew,op,op&1,len(rows)%256))
    for i in range(6000):
        rows.append((int(rng.random()<.85),int(rng.random()<.7),int(rng.random()<.015),
                     rng.getrandbits(64),rng.getrandbits(64),rng.randrange(4),rng.randrange(20),rng.randrange(2),i%256))
    rows += [(0,1,0,0,0,0,0,0,0)]*20
    (OUT/'lane.stim').write_text(''.join(f'{iv} {rd} {fl} {a:x} {b:x} {s} {op} {sel} {tag}\n'
                                        for iv,rd,fl,a,b,s,op,sel,tag in rows))
    result={}
    for top,lat in [('IntegerLaneBaseline',2),('IntegerLaneSplit',6),('IntegerLaneSplit16',7)]:
        exe=OUT/top
        subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}','-o',str(exe),
                        str(ROOT/'tests/lane_tb.sv'),str(ROOT/f'build/rtl/{top}.sv')],check=True,
                       stdout=subprocess.DEVNULL,stderr=(OUT/f'{top}.compile.log').open('w'))
        run=subprocess.run([str(BIN/'vvp'),str(exe)],cwd=ROOT,check=True,capture_output=True,text=True)
        (OUT/f'{top}.trace').write_text(run.stdout)
        trace=[s for s in run.stdout.splitlines() if s.startswith('T ')]
        assert len(trace)==len(rows)
        assert all(int(s.split()[1])==i for i,s in enumerate(trace))
        result[top]=check(rows,trace,lat,top!='IntegerLaneBaseline')
        # Negative control: a real observable DUT-result corruption must fail.
        bad=trace.copy()
        at=next(i for i,s in enumerate(bad) if s.split()[3]=='1')
        tokens=bad[at].split();tokens[4]=f'{int(tokens[4],16)^1:x}';bad[at]=' '.join(tokens)
        try: check(rows,bad,lat,top!='IntegerLaneBaseline')
        except AssertionError: result[top]['corrupt_result_rejected']=True
        else: raise AssertionError('oracle accepted corruption')
    (OUT/'lane-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
