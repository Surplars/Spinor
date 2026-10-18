#!/usr/bin/env python3
"""Independent unit-stride segment oracle: all RF bytes, addresses, partial fields and restart units."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/segment-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x46a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
fixture=(ROOT/'tests/memory_engine_fixture.sv').read_text().replace('if(io_context_bits_write)rf[io_context_bits_address]<=io_context_bits_data;', 'if(io_context_bits_write)begin rf[io_context_bits_address]<=io_context_bits_data;$display("WRITE %0d %0d %016h",caseid,io_context_bits_address,io_context_bits_data);end ')
lines.append(fixture);specs=[];models={};encodings=set();coverage={k:0 for k in ['load','store','masked','restart','empty','fractional','grouped','last_register','v0','fault','partial_field_fault','illegal','stop','error_beats_stop','wrap64']}
def issue(ew,n,write,typ=0,vl=3,start=0,vr=8,pred=None,base=BASE+1024,kind=0,error=None,stop=None,bits=0):
 ident=len(specs);inst=((n-1)<<29)|(int(pred is None)<<25)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 sew=typ>>3&7;lm=(typ&7) if typ&7<4 else (typ&7)-8;emul=lm+ew-sew;group=1<<max(0,emul)
 bad=typ>>63!=0 or sew>3 or typ&7==4 or lm<0 and sew>3+lm or emul not in range(-3,4) or group*n>8 or vr%group!=0 or vr+group*n>32 or pred is not None and vr==0 or bool(bits)
 rf=[rng.getrandbits(64) for _ in range(64)];mem=bytearray((j*13+7)&255 for j in range(N))
 if pred is not None:rf[0]=pred&((1<<64)-1);rf[1]=pred>>64
 initial=rf.copy();initialMem=mem.copy();seq=[];failure=None;w=1<<ew;errorAddress=M if error is None else (base+(error[0]*n+error[1])*w)&M
 if not bad:
  for e in range(start,vl):
   if pred is not None and not(pred>>e&1):continue
   for f in range(n):
    addr=(base+(e*n+f)*w)&M;chunk=2*(vr+f*group)+e*w//8;shift=e*w%8*8
    entry=(e,f,addr,chunk,shift)
    if addr&(w-1):failure=(e,6 if write else 4,addr);break
    if addr>>28!=BASE>>28:failure=(e,7 if write else 5,addr);break
    seq.append(entry)
    if kind and addr==errorAddress:failure=(e,7 if write else 5,addr);break
   if failure:break
 for j,x in enumerate(initial):lines.append(f"rf[{j}]=64'h{x:x};")
 lines.append(f"for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={ident};kind={kind};latency={3 if kind else 1};errorAddress=64'h{errorAddress:x};")
 e,c,tval=failure or (0,0,0);ns=start if bad else e if failure else 0
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'hdeadbeef,64'h{typ:x},{vl},{start},{int(bad)},{int(failure is not None)},{c},{e},{ns},{len(seq)},64'h{tval:x},{-1 if stop is None else stop});")
 # Read back all chunks/changed memory, including masked/prestart/tail and guards.
 for j in range(64):lines.append(f'$display("RF {ident} {j} %016h",rf[{j}]);')
 touched={((x[2]-BASE)%N)+b for x in seq for b in range(w)}
 for j in sorted(touched):lines.append(f'$display("BYTE {ident} {j} %02h",mem[{j}]);')
 spec=dict(id=ident,eew=8*w,nfields=n,write=write,vtype=typ,vl=vl,vstart=start,vr=vr,masked=pred is not None,base=base,illegal=bool(bad),error=error,kind=kind,stop=stop)
 specs.append(spec);models[ident]=dict(rf=initial,memory=initialMem,sequence=seq,width=w,write=write,failure=failure,stop=stop,vl=vl,start=start,pred=pred,touched=touched)
 if not bad:encodings.add((ew,n,write))
 for k,v in [('load',not write),('store',write),('masked',pred is not None),('restart',start>0),('empty',start>=vl),('fractional',emul<0 and not bad),('grouped',group>1 and not bad),('last_register',vr+group*n==32 and not bad),('v0',vr==0 and not bad),('fault',failure is not None),('partial_field_fault',failure is not None and error is not None and error[1]>0),('illegal',bad),('stop',stop is not None),('error_beats_stop',stop is not None and kind),('wrap64',base+(start*n)*w>M)]:coverage[k]+=int(bool(v))
types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for n in range(2,9):
 for ew in range(4):
  for write in [False,True]:
   for typ in ([ew<<3] if a.compact else types):
    sew=typ>>3&7;lm=(typ&7) if typ&7<4 else (typ&7)-8;emul=lm+ew-sew;group=1<<max(0,emul)
    if emul not in range(-3,4) or n*group>8:continue
    maximum=int(16/(1<<sew)*2**lm)
    for start,pred in ([(0,None),(1,0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)] if a.compact else [(0,None),(1,None),(0,0x55555555555555555555555555555555),(maximum,None),(127,None),(0,0)]):issue(ew,n,write,typ,maximum,start,pred=pred)
   issue(ew,n,write,ew<<3,2,vr=32-n)
   issue(ew,n,write,ew<<3,2,vr=0)
# Explicit fractional/group geometries and base aligned to EMUL, not total span.
for typ,ew,n,vr in [(0,0,4,12),(1,0,4,10),(2,0,2,4),(8,0,8,8),(5,0,8,8),(14,0,8,8),(23,0,8,8)]:
 for write in [False,True]:issue(ew,n,write,typ,1,vr=vr)
# Faults at fields of the same element must keep whole-element vstart.
for ew,n in [(0,3),(1,4),(2,2),(3,8)]:
 for write in [False,True]:
  for kind in range(1,6):
   for field in ([n-1] if a.compact else [0,1,n-1]):issue(ew,n,write,ew<<3,3,kind=kind,error=(1,field))
  if ew:issue(ew,n,write,ew<<3,2,base=BASE+1)
  issue(ew,n,write,ew<<3,2,base=BASE+(1<<28)-(n-1)*(1<<ew))
  issue(ew,n,write,ew<<3,2,base=M-(n*(1<<ew))+1,start=1)
  issue(ew,n,write,ew<<3,2,pred=0,base=BASE+1)
# Illegal geometry must still reject at empty VL / restart beyond VL.
for ew,n,typ,vr,pred,bits in [(0,3,2,8,None,0),(0,8,1,8,None,0),(0,4,1,9,None,0),(0,8,0,25,None,0),(0,2,1<<63,8,None,0),(0,2,4,8,None,0),(0,2,24|5,8,None,0),(3,2,3,8,None,0),(0,2,0,0,1,0),(0,2,0,8,None,1<<28),(0,2,0,8,None,16<<20)]:
 for write in [False,True]:issue(ew,n,write,typ,0,127,vr,pred,bits=bits)
for ew,n in [(0,3),(3,2)]:
 for write in [False,True]:
  for delay in ([0,35,100,180] if a.compact else range(0,221,5)):
   issue(ew,n,write,ew<<3,4,pred=0b1101 if delay%2 else None,stop=delay)
  issue(ew,n,write,ew<<3,4,kind=1,error=(0,1),stop=35)
lines.append('$display("PASS segment-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"leaked response");$finish;end endmodule')
label=('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));files=[tb,rtl]
if a.mapped:files.append(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
bus={};writes={};stops={};actualRF={};actualMem={};performance={}
for line in r.stdout.splitlines():
 f=line.split()
 if not f:continue
 i=int(f[1]) if f[0] in ['BUS','WRITE','STOP','RF','BYTE','PERF'] else 0
 if f[0]=='BUS':bus.setdefault(i,[]).append((int(f[2],16),int(f[3]),int(f[4]),int(f[5],16)))
 elif f[0]=='WRITE':writes.setdefault(i,[]).append((int(f[2]),int(f[3],16)))
 elif f[0]=='STOP':stops[i]=tuple(map(int,f[2:]))
 elif f[0]=='RF':actualRF.setdefault(i,{})[int(f[2])]=int(f[3],16)
 elif f[0]=='BYTE':actualMem.setdefault(i,{})[int(f[2])]=int(f[3],16)
 elif f[0]=='PERF':performance[i]=dict(cycles=int(f[2]),context_reads=int(f[3]))
for i,model in models.items():
 rf=model['rf'].copy();mem=model['memory'].copy();seq=model['sequence'];got=bus.get(i,[]);wr=writes.get(i,[]);w=model['width'];failure=model['failure']
 if model['stop'] is None:
  assert len(got)==len(seq),(i,len(got),len(seq))
  successful=len(seq)-(1 if failure and seq and seq[-1][2]==failure[2] and specs[i]['kind'] else 0)
  assert len(wr)==(0 if model['write'] else successful),(i,len(wr),successful)
 else:
  assert len(got)<=len(seq),(i,len(got),len(seq))
  successful=len(got)-(1 if failure and got and got[-1][0]==failure[2] and specs[i]['kind'] else 0) if model['write'] else len(wr)
  assert not model['write'] or not wr
  assert model['write'] or successful<=len(got)<=successful+1,(i,successful,len(got))
  end,requests,start=stops[i];assert requests==len(got)
  assert all(e<end or e==end for e,_,_,_,_ in seq[:successful]),(i,end,successful)
  assert sum(e<end for e,_,_,_,_ in seq)<=successful,(i,end,successful)
  if end==model['vl']:assert successful==len(seq) and start==0,(i,successful,len(seq))
 for j,(e,f,addr,chunk,shift) in enumerate(seq[:len(got)]):
  actual=got[j];assert actual[:3]==(addr,(w.bit_length()-1),int(model['write'])),(i,j,actual,addr)
  value=rf[chunk]>>shift&((1<<(w*8))-1)
  if model['write']:assert actual[3]&((1<<(w*8))-1)==value,(i,j,'store data')
  if j>=successful:continue
  pos=(addr-BASE)%N
  if model['write']:mem[pos:pos+w]=value.to_bytes(w,'little')
  else:
   mask=((1<<(w*8))-1)<<shift;rf[chunk]=(rf[chunk]&~mask)|(int.from_bytes(mem[pos:pos+w],'little')<<shift)
   assert wr[j]==(chunk,rf[chunk]),(i,j,'RF write',wr[j],chunk,rf[chunk])
 assert actualRF[i]==dict(enumerate(rf)),(i,'RF state')
 assert actualMem.get(i,{})=={b:mem[b] for b in model['touched']},(i,'memory state')
assert all(coverage.values()),coverage;assert len(encodings)==56,encodings
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']
d=dict(status='PASS',cases=len(specs),encodings=sorted(encodings),coverage=coverage,case_specs=specs,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS segment-engine')),scope='UNIT_STRIDE_SEGMENTS_2_TO_8; ALL_64_RF_CHUNKS; INDEPENDENT_FIELD_PREFIX_ORACLE; FULL_64BIT_ADDRESSES; 8KIB_MODULO_MEMORY; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
