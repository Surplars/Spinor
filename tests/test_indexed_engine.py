#!/usr/bin/env python3
"""Independent indexed LSU oracle: full addresses, cross-width aliases and precise prefix."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/indexed-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x44a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
lines.append((ROOT/'tests/memory_engine_fixture.sv').read_text());cases=[];expected={};stopModels={}
coverage={k:0 for k in ['ordered','unordered','load','store','masked','restart','empty','fault','illegal','alias_legal','alias_illegal','index_v0','zero_extend','wrap64','stop','error_beats_stop']}
encodings=set();geometries=set()
def issue(t,iw,write,ordered,vl=None,start=0,pred=None,vr=8,ir=24,base=BASE+1024,offsets=None,kind=0,errorElement=None,stop=None,delay=0,bits=0):
 sew=t>>3&7;lm=(t&7) if t&7<4 else (t&7)-8;emul=lm+iw-sew;dregs=set(range(vr,vr+(1<<max(0,lm))));iregs=set(range(ir,ir+(1<<max(0,emul))))
 maximum=(16>>min(sew,3))*(1<<lm) if lm>=0 else (16>>min(sew,3))//(1<<-lm)
 vl=min(maximum,8 if a.compact else 128) if vl is None else vl
 overlap=bool(dregs&iregs);validconfig=not(t>>63 or sew>3 or (t&7)==4 or maximum==0)
 aligned=vr%(1<<max(0,lm))==0 and ir%(1<<max(0,emul))==0 and max(dregs|iregs)<32
 legalOverlap=sew==iw or sew<iw and vr==ir or sew>iw and emul>=0 and max(dregs)==max(iregs)
 bad=not(validconfig and -3<=emul<=3 and aligned) or bool(pred is not None and (vr==0 or ir==0)) or bool(overlap and (sew!=iw if write else not legalOverlap)) or bool(bits&0xf0000000)
 inst=((3 if ordered else 1)<<26)|(int(pred is None)<<25)|(ir<<20)|(1<<15)|([0,5,6,7][iw]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 ident=len(cases);rf=[rng.getrandbits(64) for _ in range(64)];mem=bytearray((j*13+7)&255 for j in range(N));dw=1<<min(sew,3);ixw=1<<iw
 offsets=offsets if offsets is not None else [((e*7)%max(1,vl))*dw for e in range(vl)]
 assert len(offsets)>=vl
 # Set each encoded index, then derive both data and addresses from the actual
 # shared architectural RF. This also models legal store-data/index aliases.
 if -3<=emul<=3 and max(iregs)<32:
  for e in range(vl):
   chunk=2*ir+e*ixw//8;shift=e*ixw%8*8
   if chunk>=64:break
   mask=((1<<(8*ixw))-1)<<shift;rf[chunk]=(rf[chunk]&~mask)|((offsets[e]&((1<<(8*ixw))-1))<<shift)
 if pred is not None:rf[0]=pred&M;rf[1]=pred>>64
 initial=rf.copy();initialMem=mem.copy();transfers=[];failure=None
 actualOffsets=[(rf[2*ir+e*ixw//8]>>(e*ixw%8*8))&((1<<(8*ixw))-1) for e in range(vl)] if not bad else offsets
 errorAddress=M if errorElement is None else (base+actualOffsets[errorElement])&M
 if not bad:
  for e in range(start,vl):
   if pred is not None and not(pred>>e&1):continue
   # Read the live vector RF, not a pre-decoded index snapshot.
   value=(rf[2*ir+e*ixw//8]>>(e*ixw%8*8))&((1<<(8*ixw))-1);addr=(base+value)&M
   if addr&(dw-1):failure=(e,6 if write else 4,addr);break
   if addr&~((1<<28)-1)!=BASE:failure=(e,7 if write else 5,addr);break
   chunk=2*vr+e*dw//8;shift=e*dw%8*8;data=(rf[chunk]>>shift)&((1<<(8*dw))-1)
   transfers.append((addr,sew,int(write),data))
   if kind and addr==errorAddress:failure=(e,7 if write else 5,addr);break
   pos=(addr-BASE)%N
   if write:mem[pos:pos+dw]=data.to_bytes(dw,'little')
   else:rf[chunk]=(rf[chunk]&~(((1<<(8*dw))-1)<<shift))|(int.from_bytes(mem[pos:pos+dw],'little')<<shift)
 for j,x in enumerate(initial):lines.append(f"rf[{j}]=64'h{x:x};")
 lines.append(f'for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={ident};kind={kind};latency={delay};errorAddress=64\'h{errorAddress:x};')
 f,c,tval=failure if failure else (0,0,0);nstart=start if bad else f if failure else 0
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'hdeadbeef,64'h{t:x},{vl},{start},{int(bad)},{int(bool(failure))},{c},{f},{nstart},{len(transfers)},64'h{tval:x},{-1 if stop is None else stop});")
 if stop is None:
  expected[ident]=transfers
  for j,x in enumerate(rf):lines.append(f"if(rf[{j}]!==64'h{x:x})$fatal(1,\"indexed RF {ident}/{j}\");")
  if write:
   for j in {((addr-BASE)%N)+b for addr,_,_,_ in transfers for b in range(dw)}:lines.append(f"if(mem[{j}]!==8'h{mem[j]:x})$fatal(1,\"indexed store {ident}/{j}\");")
 else:
  stopModels[ident]=dict(rf=initial,memory=initialMem,offsets=actualOffsets,base=base,pred=pred,vr=vr,width=dw,write=write,vl=vl,kind=kind)
  for j in range(64):lines.append(f'$display("RF {ident} {j} %016h",rf[{j}]);')
  for j in range(1024,1536):lines.append(f'$display("BYTE {ident} {j} %02h",mem[{j}]);')
 spec=dict(id=ident,vtype=t,index_eew=8<<iw,write=write,ordered=ordered,vl=vl,vstart=start,masked=pred is not None,vd_vs3=vr,vs2=ir,base=base,illegal=bad,stop=stop)
 cases.append(spec);encodings.add((iw,write,ordered));geometries.add((t,iw))
 for key,yes in [('ordered',ordered),('unordered',not ordered),('load',not write),('store',write),('masked',pred is not None),('restart',start>0),('empty',start>=vl),('fault',failure is not None),('illegal',bad),('alias_legal',overlap and not bad),('alias_illegal',overlap and bad),('index_v0',ir==0),('zero_extend',iw<3 and any(x>=(1<<(ixw*8-1)) for x in offsets)),('wrap64',any(base+x>M for x in offsets)),('stop',stop is not None),('error_beats_stop',stop is not None and bool(kind))]:coverage[key]+=int(yes)
types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
comb=[(t,i) for t in types for i in range(4) if -3<=((t&7) if t&7<4 else (t&7)-8)+i-(t>>3&7)<=3]
if a.compact:comb=[(0,0),(8,1),(16,2),(24,3),(0,3),(24,0),(3,0),(27,3),(10,0),(2,2)]
for t,iw in comb:
 for write in [False,True]:
  for ordered in [False,True]:
   for pred in ([None,0xa596a596a596a596a596a596a596a596] if not a.compact else [None]):issue(t,iw,write,ordered,pred=pred,start=1)
# All same-register and partial-group alias relations, including different EEWs.
for sew in range(4):
 for iw in range(4):
  for write in [False,True]:
   for vr,ir in [(8,8),(8,9),(9,8),(8,10),(8,11),(8,0),(0,0)]:
    issue(sew<<3|1,iw,write,bool((vr+ir)%2),vr=vr,ir=ir,vl=2)
   for vr,ir in [(0,8),(8,0)]:issue(sew<<3,iw,write,True,vr=vr,ir=ir,vl=0,pred=0)
# Zero-extend high-bit narrow offsets, full 64-bit offset/wrap, nonmonotonic
# and duplicate addresses, invalid geometry, mask fault suppression, restarts.
for sew in range(4):
 for iw in range(4):
  for write in [False,True]:
   t=sew<<3|1;w=1<<sew;hi=1<<((8<<iw)-1)
   issue(t,iw,write,True,vl=2,offsets=[hi,hi+w],base=(BASE+2048-hi)&M)
   issue(t,iw,write,False,vl=2,offsets=[0,0])
   for k in range(1,6):issue(t,iw,write,True,vl=2,offsets=[0,3*w],kind=k,errorElement=1,delay=3)
   issue(t,iw,write,False,vl=2,offsets=[0,1],base=BASE+1024)
   issue(t,iw,write,True,vl=2,offsets=[0,1],base=BASE+1024,pred=1)
   issue(t,iw,write,True,vl=0,base=BASE+1)
   issue(t,iw,write,False,vl=2,start=7,base=BASE+1)
   issue(t,iw,write,True,vl=2,start=1,offsets=[0,3*w])
   issue(t,iw,write,True,vl=2,bits=1<<28)
   issue(t,iw,write,True,vl=2,bits=1<<29)
# Reserved EMUL/LMUL/vill, index-group alignment/end, and restart limit.
for t,iw,vr,ir in [(3,3,8,24),(31,0,8,24),(4,0,8,24),(1<<63,0,8,24),(3,0,8,25),(3,0,8,30)]:
 for write in [False,True]:issue(t,iw,write,True,vl=0,vr=vr,ir=ir)
for write in [False,True]:issue(3,0,write,True,vl=128,start=127)
for write in [False,True]:
 for ordered in [False,True]:
  for delta in ([0,30,90] if a.compact else range(0,160,5)):
   issue(0,0,write,ordered,vl=16,pred=0xa596,offsets=[((i*7)%16)*2 for i in range(16)],stop=delta,delay=4)
  issue(0,0,write,ordered,vl=16,offsets=[i*2 for i in range(16)],kind=1,errorElement=0,stop=30,delay=80)
lines.append('$display("PASS indexed-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"leaked indexed response");$finish;end endmodule')
label=('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));files=[tb,rtl]
if a.mapped:files.append(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
bus={};stops={};actualRF={};actualByte={};performance={}
for line in r.stdout.splitlines():
 f=line.split()
 if not f:continue
 if f[0]=='BUS':bus.setdefault(int(f[1]),[]).append((int(f[2],16),int(f[3]),int(f[4]),int(f[5],16)))
 elif f[0]=='STOP':stops[int(f[1])]=tuple(map(int,f[2:]))
 elif f[0]=='RF':actualRF.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif f[0]=='BYTE':actualByte.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif f[0]=='PERF':performance[int(f[1])]=dict(cycles=int(f[2]),context_reads=int(f[3]))
for i,want in expected.items():
 got=bus.get(i,[]);assert len(got)==len(want),(i,len(got),len(want))
 for x,y in zip(got,want,strict=True):assert x[:3]==y[:3] and (not x[2] or x[3]&((1<<(8*(1<<x[1])))-1)==y[3]),(i,x,y)
for i,(end,count,start) in stops.items():
 spec=stopModels[i];rf=spec['rf'].copy();mem=spec['memory'].copy();addresses=[]
 for e in range(end):
  if spec['pred'] is not None and not(spec['pred']>>e&1):continue
  addr=(spec['base']+spec['offsets'][e])&M;addresses.append(addr);dw=spec['width'];chunk=spec['vr']*2+e*dw//8;shift=e*dw%8*8;pos=(addr-BASE)%N
  if spec['write']:mem[pos:pos+dw]=((rf[chunk]>>shift)&((1<<(8*dw))-1)).to_bytes(dw,'little')
  else:rf[chunk]=(rf[chunk]&~(((1<<(8*dw))-1)<<shift))|(int.from_bytes(mem[pos:pos+dw],'little')<<shift)
 assert actualRF[i]==dict(enumerate(rf)),(i,end)
 assert actualByte[i]=={j:mem[j] for j in range(1024,1536)},(i,end)
 got=[x[0] for x in bus.get(i,[])];assert got[:len(addresses)]==addresses,(i,end,got,addresses)
 assert len(got)==1 and got[0]==spec['base'] if spec['kind'] else len(got)==len(addresses) if spec['write'] else len(addresses)<=len(got)<=len(addresses)+1,(i,end,got)
assert all(coverage.values()),coverage;assert len(encodings)==16
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']
result=dict(status='PASS',cases=len(cases),encodings=sorted(encodings),geometries=sorted(geometries),coverage=coverage,case_specs=cases,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS indexed-engine')),scope='PHYSICAL_NORMAL_RAM; MODULO_8KIB_DATA_BACKING; INDEPENDENT_FULL_64BIT_ADDRESS_AND_RF_ORACLE; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
