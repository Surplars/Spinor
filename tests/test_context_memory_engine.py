#!/usr/bin/env python3
"""Independent byte oracle for whole-register/mask LSU, including restart and stop."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/context-memory-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x45a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;','integer effectiveLength;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
fixture=(ROOT/'tests/memory_engine_fixture.sv').read_text().replace('io_status_element:length','io_status_element:effectiveLength');lines.append(fixture)
cases=[];expected={};stopModels={};encodings=set()
coverage={k:0 for k in ['whole','mask','load','store','vill_ignored','vill_reject','vl_ignored','v0','restart','empty','partial_byte','fault','illegal','stop','error_beats_stop','wrap64','whole8','whole16','whole32','whole64']}
def issue(mode,ew=0,nregs=1,write=False,typ=0,vl=0,start=0,vr=8,base=BASE+1024,vm=True,bits=0,kind=0,errorElement=None,stop=None,delay=0):
 ident=len(cases);sel=8 if mode=='whole' else 11;inst=((nregs-1)<<29)|(int(vm)<<25)|(sel<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 nf=inst>>29&7;group=nf+1;bad=bool(not vm or inst&(1<<28) or inst>>26&3)
 if mode=='whole':bad|=group not in [1,2,4,8] or vr%group!=0 or vr+group>32 or write and ew!=0;evl=group*16//(1<<ew)
 else:bad|=nf!=0 or ew!=0 or typ>>63!=0 or typ>>3&7>3;evl=(vl+7)//8
 width=1<<ew if mode=='whole' else 1;rf=[rng.getrandbits(64) for _ in range(64)];initial=rf.copy();mem=bytearray((j*13+7)&255 for j in range(N));initialMem=mem.copy();transfers=[];failure=None
 errorAddress=M if errorElement is None else (base+errorElement*width)&M
 if not bad:
  for e in range(start,evl):
   addr=(base+e*width)&M
   if addr&(width-1):failure=(e,6 if write else 4,addr);break
   if addr&~((1<<28)-1)!=BASE:failure=(e,7 if write else 5,addr);break
   chunk=2*vr+e*width//8;shift=e*width%8*8;mask=((1<<(8*width))-1)<<shift;data=rf[chunk]>>shift&((1<<(8*width))-1);transfers.append((addr,ew if mode=='whole' else 0,int(write),data))
   if kind and addr==errorAddress:failure=(e,7 if write else 5,addr);break
   pos=(addr-BASE)%N
   if write:mem[pos:pos+width]=data.to_bytes(width,'little')
   else:rf[chunk]=(rf[chunk]&~mask)|(int.from_bytes(mem[pos:pos+width],'little')<<shift)
 for j,x in enumerate(initial):lines.append(f"rf[{j}]=64'h{x:x};")
 lines.append(f"for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={ident};kind={kind};latency={delay};errorAddress=64'h{errorAddress:x};effectiveLength={evl};")
 f,c,tval=failure if failure else (0,0,0);nstart=start if bad else f if failure else 0
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'hdeadbeef,64'h{typ:x},{vl},{start},{int(bad)},{int(bool(failure))},{c},{f},{nstart},{len(transfers)},64'h{tval:x},{-1 if stop is None else stop});")
 if stop is None:
  expected[ident]=transfers
  for j,x in enumerate(rf):lines.append(f"if(rf[{j}]!==64'h{x:x})$fatal(1,\"context RF {ident}/{j}\");")
  if write:
   for j in {((addr-BASE)%N)+b for addr,_,_,_ in transfers for b in range(width)}:lines.append(f"if(mem[{j}]!==8'h{mem[j]:x})$fatal(1,\"context store {ident}/{j}\");")
 else:
  stopModels[ident]=dict(rf=initial,memory=initialMem,base=base,vr=vr,width=width,write=write,evl=evl,kind=kind)
  for j in range(64):lines.append(f'$display("RF {ident} {j} %016h",rf[{j}]);')
  for j in range(1024,1280):lines.append(f'$display("BYTE {ident} {j} %02h",mem[{j}]);')
 spec=dict(id=ident,mode=mode,eew=8*width,nregs=nregs,write=write,vl=vl,vtype=typ,vstart=start,vr=vr,base=base,evl=evl,illegal=bool(bad),stop=stop);cases.append(spec)
 if not bad:encodings.add((mode,ew,nregs,write))
 for key,yes in [('whole',mode=='whole'),('mask',mode=='mask'),('load',not write),('store',write),('vill_ignored',mode=='whole' and typ>>63 and not bad),('vill_reject',mode=='mask' and typ>>63 and bad),('vl_ignored',mode=='whole' and vl!=evl and not bad),('v0',vr==0 and not bad),('restart',start>0),('empty',start>=evl),('partial_byte',mode=='mask' and vl%8!=0 and not bad),('fault',failure is not None),('illegal',bad),('stop',stop is not None),('error_beats_stop',stop is not None and bool(kind)),('wrap64',base+start*width>M),(f'whole{8*width}',mode=='whole')]:coverage[key]+=int(bool(yes))
forms=[(e,n,w) for n in [1,2,4,8] for w in [False,True] for e in ([0] if w else range(4))]
for ew,n,write in forms:
 evl=n*16//(1<<ew)
 for typ in ([0,(1<<63)] if a.compact else [0,3,24,27,5,1<<63,(1<<64)-1]):
  for vl in ([0] if a.compact else [0,128]):
   for start in sorted(x for x in ({0,1,evl,127} if not a.compact else {0,evl}) if x<=127):issue('whole',ew,n,write,typ,vl,start,vr=24)
 # Legal v0 and odd single-register groups, full restart near the final element.
 issue('whole',ew,n,write,typ=1<<63,vl=0,vr=0,start=evl-1)
 if n==1:issue('whole',ew,n,write,vr=31)
types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for typ in ([0,27,5] if a.compact else types):
 lm=(typ&7) if typ&7<4 else (typ&7)-8;maximum=(16>>(typ>>3&7))*(1<<lm) if lm>=0 else (16>>(typ>>3&7))//(1<<-lm)
 for vl in sorted({0,1,min(7,maximum),min(8,maximum),min(9,maximum),maximum}):
  for write in [False,True]:
   for start in sorted({0,1,(vl+7)//8,127} if not a.compact else {0,(vl+7)//8}):issue('mask',write=write,typ=typ,vl=vl,start=start,vr=0)
for mode,ew,n,write in [('mask',0,1,w) for w in [False,True]]+[('whole',e,n,w) for e,n,w in forms]:
 evl=9 if mode=='mask' else n*16//(1<<ew);vl=65 if mode=='mask' else 0
 for kind in range(1,6):issue(mode,ew,n,write,vl=vl,kind=kind,errorElement=min(1,evl-1),delay=3)
 issue(mode,ew,n,write,vl=vl,base=BASE-1)
 issue(mode,ew,n,write,vl=vl,base=M-(1<<ew)+1,start=1)
 issue(mode,ew,n,write,vl=vl,vm=False)
 issue(mode,ew,n,write,vl=vl,bits=1<<28)
 if mode=='whole' and n>1:issue(mode,ew,n,write,vl=vl,vr=9)
for n in [3,5,6,7]:issue('whole',nregs=n,write=False,vl=0)
for ew in [1,2,3]:issue('whole',ew,write=True);issue('mask',ew,vl=0)
issue('mask',typ=1<<63,vl=0);issue('mask',bits=1<<29,vl=0)
for mode,ew,n in [('mask',0,1),('whole',0,8),('whole',3,8)]:
 evl=16 if mode=='mask' else n*16//(1<<ew);vl=128 if mode=='mask' else 0
 for write in [False,True]:
  if write and ew:continue
  for delay in ([0,40,160] if a.compact else range(0,201,8)):
   issue(mode,ew,n,write,vl=vl,stop=delay,delay=4)
  issue(mode,ew,n,write,vl=vl,kind=1,errorElement=0,stop=30,delay=80)
lines.append('$display("PASS context-memory-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"leaked context response");$finish;end endmodule')
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
 spec=stopModels[i];rf=spec['rf'].copy();mem=spec['memory'].copy();width=spec['width'];addresses=[]
 for e in range(end):
  addr=(spec['base']+e*width)&M;addresses.append(addr);chunk=spec['vr']*2+e*width//8;shift=e*width%8*8;pos=(addr-BASE)%N
  if spec['write']:mem[pos:pos+width]=((rf[chunk]>>shift)&((1<<(8*width))-1)).to_bytes(width,'little')
  else:rf[chunk]=(rf[chunk]&~(((1<<(8*width))-1)<<shift))|(int.from_bytes(mem[pos:pos+width],'little')<<shift)
 assert actualRF[i]==dict(enumerate(rf)),(i,end)
 assert actualByte[i]=={j:mem[j] for j in range(1024,1280)},(i,end)
 got=[x[0] for x in bus.get(i,[])];assert got[:len(addresses)]==addresses,(i,end,got,addresses)
 assert len(got)==1 and got[0]==spec['base'] if spec['kind'] else len(got)==len(addresses) if spec['write'] else len(addresses)<=len(got)<=len(addresses)+1,(i,end,got)
assert all(coverage.values()),coverage;assert len(encodings)==22,encodings
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VectorMemoryEngine.scala']
result=dict(status='PASS',cases=len(cases),encodings=sorted(encodings),coverage=coverage,case_specs=cases,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS context-memory-engine')),scope='WHOLE_AND_MASK; ALL_RF_CHUNKS; INDEPENDENT_FULL_64BIT_ADDRESS_BYTE_ORACLE; REGISTERED_8KIB_MODULO_MEMORY; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
