#!/usr/bin/env python3
"""Independent strided/indexed segment oracle: all RF bytes, addresses, partial fields and restart units."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/addressed-segment-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x47a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
fixture=(ROOT/'tests/memory_engine_fixture.sv').read_text().replace('if(io_context_bits_write)rf[io_context_bits_address]<=io_context_bits_data;', 'if(io_context_bits_write)begin rf[io_context_bits_address]<=io_context_bits_data;$display("WRITE %0d %0d %016h",caseid,io_context_bits_address,io_context_bits_data);end ')
lines.append(fixture);specs=[];models={};encodings=set();coverage={k:0 for k in ['load','store','masked','restart','empty','fractional','grouped','last_register','v0','fault','partial_field_fault','illegal','stop','error_beats_stop','wrap64','positive_stride','negative_stride','zero_x0','zero_register','ordered','unordered','index_v0','zero_extend','alias_legal','alias_illegal']}
def issue(mode,ew,n,write,typ=None,vl=2,start=0,vr=8,pred=None,base=BASE+1024,kind=0,error=None,stop=None,bits=0,stride=None,rs2=2,ir=24,offsets=None):
 typ=ew<<3 if typ is None else typ;sew=typ>>3&7;lm=(typ&7) if typ&7<4 else (typ&7)-8;indexed=mode!='stride'
 dataew=min(sew,3) if indexed else ew;emul=lm+ew-sew;dataemul=lm if indexed else emul
 group=1<<max(0,dataemul);ig=1<<max(0,emul);w=1<<dataew;ixw=1<<ew
 dregs=set(range(vr,vr+n*group));iregs=set(range(ir,ir+ig));overlap=indexed and bool(dregs&iregs)
 bad=typ>>63!=0 or sew>3 or typ&7==4 or lm<0 and sew>3+lm or emul not in range(-3,4) or group*n>8 or vr%group!=0 or vr+group*n>32 or pred is not None and vr==0 or bool(bits)
 if indexed:bad|=ir%ig!=0 or ir+ig>32 or pred is not None and ir==0 or overlap and (not write or dataew!=ew)
 stride=n*w+2*w if stride is None else stride;effectiveStride=0 if rs2==0 else stride
 mop={'stride':2,'indexed':1,'ordered':3}[mode];ident=len(specs)
 inst=((n-1)<<29)|(mop<<26)|(int(pred is None)<<25)|((ir if indexed else rs2)<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 rf=[rng.getrandbits(64) for _ in range(64)];mem=bytearray((j*13+7)&255 for j in range(N))
 offsets=offsets if offsets is not None else [((e*5)%max(1,vl))*n*w for e in range(vl)]
 if indexed and -3<=emul<=3 and ir+ig<=32:
  for e in range(vl):
   chunk=2*ir+e*ixw//8;shift=e*ixw%8*8
   if chunk>=64:break
   mask=((1<<(8*ixw))-1)<<shift;rf[chunk]=(rf[chunk]&~mask)|((offsets[e]&((1<<(8*ixw))-1))<<shift)
 if pred is not None:rf[0]=pred&((1<<64)-1);rf[1]=pred>>64
 initial=rf.copy();initialMem=mem.copy();seq=[];failure=None
 actualOffsets=[(rf[2*ir+e*ixw//8]>>(e*ixw%8*8))&((1<<(8*ixw))-1) for e in range(vl)] if indexed and not bad else offsets
 def elementBase(e):return base+(actualOffsets[e] if indexed else e*effectiveStride)
 errorAddress=M if error is None else (elementBase(error[0])+error[1]*w)&M
 if not bad:
  for e in range(start,vl):
   if pred is not None and not(pred>>e&1):continue
   for f in range(n):
    addr=(elementBase(e)+f*w)&M;chunk=2*(vr+f*group)+e*w//8;shift=e*w%8*8;entry=(e,f,addr,chunk,shift)
    if addr&(w-1):failure=(e,6 if write else 4,addr);break
    if addr>>28!=BASE>>28:failure=(e,7 if write else 5,addr);break
    seq.append(entry)
    if kind and addr==errorAddress:failure=(e,7 if write else 5,addr);break
   if failure:break
 for j,x in enumerate(initial):lines.append(f"rf[{j}]=64'h{x:x};")
 lines.append(f"for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={ident};kind={kind};latency={3 if kind else 1};errorAddress=64'h{errorAddress:x};")
 e,c,tval=failure or (0,0,0);ns=start if bad else e if failure else 0
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'h{stride&M:x},64'h{typ:x},{vl},{start},{int(bad)},{int(failure is not None)},{c},{e},{ns},{len(seq)},64'h{tval:x},{-1 if stop is None else stop});")
 # Read back all chunks/changed memory, including masked/prestart/tail and guards.
 for j in range(64):lines.append(f'$display("RF {ident} {j} %016h",rf[{j}]);')
 touched={((x[2]-BASE)%N)+b for x in seq for b in range(w)}
 for j in sorted(touched):lines.append(f'$display("BYTE {ident} {j} %02h",mem[{j}]);')
 spec=dict(id=ident,mode=mode,index_offsets=actualOffsets if indexed else None,index_eew=(8<<ew) if indexed else None,stride=effectiveStride,vs2=ir if indexed else None,eew=8*w,nfields=n,write=write,vtype=typ,vl=vl,vstart=start,vr=vr,masked=pred is not None,base=base,illegal=bool(bad),error=error,kind=kind,stop=stop)
 specs.append(spec);models[ident]=dict(rf=initial,memory=initialMem,sequence=seq,width=w,write=write,failure=failure,stop=stop,vl=vl,start=start,pred=pred,touched=touched)
 if not bad:encodings.add((mode,ew,n,write))
 for k,v in [('load',not write),('store',write),('masked',pred is not None),('restart',start>0),('empty',start>=vl),('fractional',emul<0 and not bad),('grouped',group>1 and not bad),('last_register',vr+group*n==32 and not bad),('v0',vr==0 and not bad),('fault',failure is not None),('partial_field_fault',failure is not None and error is not None and error[1]>0),('illegal',bad),('stop',stop is not None),('error_beats_stop',stop is not None and kind),('wrap64',any(elementBase(e)>M or elementBase(e)<0 for e in range(start,vl))),('positive_stride',not indexed and effectiveStride>0),('negative_stride',not indexed and effectiveStride<0),('zero_x0',not indexed and rs2==0),('zero_register',not indexed and rs2!=0 and stride==0),('ordered',mode=='ordered'),('unordered',mode=='indexed'),('index_v0',indexed and ir==0 and not bad),('zero_extend',indexed and ew<3 and any(o>=(1<<(ixw*8-1)) for o in actualOffsets)),('alias_legal',overlap and not bad),('alias_illegal',overlap and bad)]:coverage[k]+=int(bool(v))
types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for mode in ['stride','indexed','ordered']:
 for n in range(2,9):
  for ew in range(4):
   for write in [False,True]:
    issue(mode,ew,n,write)
    issue(mode,ew,n,write,start=1,pred=0b10)
    if not a.compact:
     for typ in types:
      if typ==ew<<3:continue
      sew=typ>>3&7;lm=(typ&7) if typ&7<4 else (typ&7)-8;emul=lm+ew-sew;dg=1<<max(0,lm if mode!='stride' else emul)
      if emul not in range(-3,4) or dg*n>8:continue
      maximum=int(16/(1<<sew)*2**lm)
      issue(mode,ew,n,write,typ,vl=min(maximum,3),start=0)
# Stride seeks, repeats, overlaps and whole-segment mask suppression.
for ew,n in [(0,3),(1,4),(2,2),(3,8)]:
 vl=min(3,16//(1<<ew));w=1<<ew
 for write in [False,True]:
  for stride,rs2 in [(0,0),(0,2),(999,0),(-n*w,2),(w,2)]:issue('stride',ew,n,write,vl=vl,stride=stride,rs2=rs2,start=1)
  issue('stride',ew,n,write,vl=vl,pred=0,base=BASE+1)
  issue('stride',ew,n,write,vl=vl,vr=32-n)
  issue('stride',ew,n,write,vl=vl,vr=0)
for mode in ['indexed','ordered']:
 for sew in range(4):
  for iw in range(4):
   for write in [False,True]:
    w=1<<sew;hi=1<<((8<<iw)-1)
    issue(mode,iw,2,write,typ=sew<<3,offsets=[hi,hi+2*w],base=(BASE+1024-hi)&M)
    issue(mode,iw,2,write,typ=sew<<3,offsets=[0,0])
    issue(mode,iw,2,write,typ=sew<<3,vr=0,ir=24)
    issue(mode,iw,2,write,typ=sew<<3,ir=0)
# Mask gaps must advance the segment base, and must suppress a later misaligned segment.
for write in [False,True]:
 for mode in ['stride','indexed','ordered']:
  for stride in ([5,-5,0] if mode=='stride' else [5]):
   issue(mode,0,3,write,vl=4,pred=0b1010,stride=stride,base=BASE+2048,offsets=[9,0,6,3])
 for ew in [1,2,3]:
  issue('stride',ew,2,write,stride=1)
  issue('stride',ew,2,write,stride=1,pred=1)
# Every field of an indexed load is checked, even with no active elements.
for mode in ['indexed','ordered']:
 for n in range(2,9):
  for field in range(n):
   for write in [False,True]:
    issue(mode,0,n,write,ir=8+field,vl=2)
    issue(mode,0,n,write,ir=8+field,vl=0,start=127)
 for sew,iw,typ,vr,ir in [(0,1,0,8,9),(1,0,8,8,9),(0,0,1,10,12),(0,0,1,10,16)]:
  for write in [False,True]:issue(mode,iw,3,write,typ,vl=2,vr=vr,ir=ir)
# Response and local faults at middle/last fields preserve segment vstart.
for mode in ['stride','indexed','ordered']:
 for ew,n in [(0,3),(3,2)]:
  w=1<<ew
  for write in [False,True]:
   for kind in range(1,6):issue(mode,ew,n,write,kind=kind,error=(1,n-1))
   if ew:issue(mode,ew,n,write,base=BASE+1)
   issue(mode,ew,n,write,base=BASE+(1<<28)-w)
   issue(mode,ew,n,write,vl=0,start=127)
   issue(mode,ew,n,write,start=127)
# Geometry/opcode checks do not depend on VL or mask activity.
for mode in ['stride','indexed','ordered']:
 for write in [False,True]:
  for typ,ew,n,vr,ir,pred,bits in [(2,0,3,8,24,None,0),(1,0,8,8,24,None,0),(1,0,4,9,24,None,0),(0,0,8,25,24,None,0),(1<<63,0,2,8,24,None,0),(4,0,2,8,24,None,0),(0,0,2,0,24,0,0),(0,0,2,8,24,None,1<<28)]:issue(mode,ew,n,write,typ,vl=0,start=127,vr=vr,ir=ir,pred=pred,bits=bits)
for mode in ['stride','indexed','ordered']:
 for ew,n in [(0,3),(3,2)]:
  for write in [False,True]:
   for delay in ([0,60,160] if a.compact else range(0,241,20)):
    issue(mode,ew,n,write,vl=min(4,16//(1<<ew)),stop=delay)
   issue(mode,ew,n,write,vl=2,kind=1,error=(0,0),stop=30)
lines.append('$display("PASS addressed-segment-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"leaked response");$finish;end endmodule')
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
 assert not specs[i]['illegal'] or performance[i]['context_reads']==0,(i,'illegal context read')
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
assert all(coverage.values()),coverage;assert len(encodings)==168,encodings
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']
d=dict(status='PASS',cases=len(specs),encodings=sorted(encodings),coverage=coverage,case_specs=specs,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS addressed-segment-engine')),scope='STRIDED_AND_INDEXED_SEGMENTS_168_ENCODINGS_2_TO_8; ALL_64_RF_CHUNKS; INDEPENDENT_FIELD_PREFIX_ORACLE; FULL_64BIT_ADDRESSES; 8KIB_MODULO_MEMORY; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
