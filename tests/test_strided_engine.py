#!/usr/bin/env python3
"""64-bit independent address/RF oracle for the physical LSU, with stalls and stops."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/strided-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x43a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
# Derive only the port declarations; the oracle does not read implementation logic.
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
ports=[];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ports.append((direction,width,name))
ready={'io_context_ready','io_commit_ready','io_memoryRequest_ready'}
lines=['module tb;']
for d,w,n in ports:lines.append(f'{"wire" if d=="output" or n in ready else "reg"} {w} {n}'+(';' if d=='output' or n in ready else '=0;'))
lines.append((ROOT/'tests/memory_engine_fixture.sv').read_text())
rf=[(i*0x32100123456789ab+0xabcdee)&M for i in range(64)];mem=bytearray((i*13+7)&255 for i in range(N));expected={};cases=[];coverage={k:0 for k in ['positive','negative','zero','rs2_x0','masked','restart','empty','fault','illegal','wrap64','high_stride','eew8','eew16','eew32','eew64','stop']}
for i,x in enumerate(rf):lines.append(f"rf[{i}]=64'h{x:x};")
lines.append('for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;')
def issue(ew,write,step,vl=4,start=0,mask=None,typ=None,vr=8,rs2=2,base=BASE+2048,kind=0,error=None,bits=0,stop=None,service=None):
 global rf,mem
 typ=((ew<<3)|int(vl>(16>>ew))) if typ is None else typ;lm=(typ&7) if typ&7<4 else (typ&7)-8;emul=lm+ew-((typ>>3)&7);n=1<<max(0,emul)
 inst=(2<<26)|(int(mask is None)<<25)|(rs2<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 bad=bool(typ>>63 or not -3<=emul<=3 or vr%n or vr+n>32 or mask is not None and vr==0 or inst>>28 or (inst>>26&3)!=2 or (inst>>12&7) not in [0,5,6,7])
 stride=step if rs2 else 0;old=list(rf);memory=bytearray(mem);width=1<<ew;transfers=[];failure=None
 pred=(1<<128)-1 if mask is None else mask;rf[0]=pred&M;rf[1]=pred>>64
 old=list(rf)
 if not bad:
  for e in range(start,vl):
   if not pred>>e&1:continue
   addr=(base+e*stride)&M
   if addr&(width-1):failure=(e,6 if write else 4,addr);break
   if addr&~((1<<28)-1)!=BASE:failure=(e,7 if write else 5,addr);break
   chunk=2*vr+(e*width)//8;shift=(e*width%8)*8;data=(rf[chunk]>>shift)&((1<<(8*width))-1)
   transfers.append((addr,ew,int(write),data))
   if error==addr and kind:failure=(e,7 if write else 5,addr);break
   ix=(addr-BASE)%N
   if write:memory[ix:ix+width]=data.to_bytes(width,'little')
   else:
    data=int.from_bytes(memory[ix:ix+width],'little');rf[chunk]=(rf[chunk]&~(((1<<(8*width))-1)<<shift))|(data<<shift)
 ident=len(cases);spec=dict(id=ident,eew=8<<ew,write=write,stride=step,rs2=rs2,vl=vl,start=start,masked=mask is not None,vtype=typ,base=base,illegal=bad,stop=stop,fault_stop=bool(stop is not None and kind))
 cases.append(spec);expected[ident]=transfers
 for key,yes in [('positive',stride>0),('negative',stride<0),('zero',stride==0),('rs2_x0',rs2==0),('masked',mask is not None),('restart',start!=0),('empty',start>=vl),('fault',failure is not None),('illegal',bad),('wrap64',base+start*stride!=((base+start*stride)&M)),('high_stride',abs(stride)>2**32),(f'eew{8<<ew}',True),('stop',stop is not None)]:coverage[key]+=int(yes)
 lines.append(f"caseid={ident};rf[0]=64'h{pred&M:x};rf[1]=64'h{pred>>64:x};latency={ident%3*3 if service is None else service};kind={kind};errorAddress=64'h{(M if error is None else error):x};")
 f,c,t=(failure if failure else (0,0,0));nstart=start if bad else f if failure else 0
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'h{step&M:x},64'h{typ:x},{vl},{start},{int(bad)},{int(bool(failure))},{c},{f},{nstart},{len(transfers)},64'h{t:x},{-1 if stop is None else stop});")
 if stop is None:
  mem=memory
  for i,x in enumerate(rf):lines.append(f"if(rf[{i}]!==64'h{x:x})$fatal(1,\"RF case {ident} chunk {i}\");")
  if write:
   touched={((addr-BASE)%N)+j for addr,_,_,_ in transfers for j in range(width)}
   for ix in touched:lines.append(f"if(mem[{ix}]!==8'h{mem[ix]:x})$fatal(1,\"memory case {ident}\");")
 else:
  # Stop cases are last; restore a deterministic fixture before each command.
  rf=list(old);expected.pop(ident)
  for i in range(64):lines.append(f'$display("RF {ident} {i} %016h",rf[{i}]);')
  for ix in range(1024,1152):lines.append(f'$display("BYTE {ident} {ix} %02h",mem[{ix}]);')
  spec.update(old_rf=list(old),old_memory=list(mem[1024:1152]))
  for i,x in enumerate(old):lines.append(f"rf[{i}]=64'h{x:x};")
  for ix in range(1024,1152):lines.append(f"mem[{ix}]=8'h{mem[ix]:x};")
types=[(s<<3)|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
comb=[(t,e) for t in types for e in range(4) if -3<=((t&7) if t&7<4 else (t&7)-8)+e-((t>>3)&7)<=3]
if a.compact:comb=[(0,0),(8,1),(16,2),(24,3),(0,3),(24,0),(3,0),(27,3)]
for typ,ew in comb:
 lm=(typ&7) if typ&7<4 else (typ&7)-8;maximum=(16>>((typ>>3)&7))*(1<<lm) if lm>=0 else (16>>((typ>>3)&7))//(1<<-lm);vl=min(maximum,8 if a.compact else 128)
 for write in [False,True]:
  for step in [0,3*(1<<ew),-2*(1<<ew)]:
   for pred in ([None] if a.compact else [None,int('a596'*8,16)]):issue(ew,write,step,vl=vl,typ=typ,mask=pred,start=int(not a.compact and vl>2))
for ew in range(4):
 w=1<<ew
 for write in [False,True]:
  for start in [0,1,7,15,63,127]:
   vl=128 if ew==0 else 128//w
   for step in [w,-w,0]:issue(ew,write,step,vl=vl,typ=(ew<<3)|3,start=start,base=BASE+2048)
  issue(ew,write,0xdeadbeef,rs2=0,vl=2)
  for step in [1<<32,-(1<<32),(1<<63),-(1<<63),M-7,-M+7]:
   issue(ew,write,step,vl=3,start=1,base=(BASE-step)&M)
  for kind in range(1,6):issue(ew,write,w*3,vl=2,kind=kind,error=BASE+2048+w*3)
  issue(ew,write,w+1,vl=2);issue(ew,write,-w,vl=2,base=BASE)
  issue(ew,write,w,vl=0);issue(ew,write,w,start=7,vl=2);issue(ew,write,w,mask=0,base=BASE+1)
  issue(ew,write,w,mask=1,vr=0);issue(ew,write,w,bits=1<<28);issue(ew,write,w,bits=(1<<29)|(1<<28))
for typ,ew in [(3,3),(0,0x0)]:issue(ew,False,8,typ=typ,vr=9 if ew==0 else 8)
# Unknown stop boundaries use observed progress, independently replayed after simulation.
for write in [False,True]:
 for step in [2,-2,0]:
  for delay in ([0,15,80] if a.compact else range(0,120,5)):
   issue(0,write,step,vl=16,base=BASE+1056,stop=delay,mask=0xa596)
for write in [False,True]:issue(0,write,2,vl=16,base=BASE+1056,stop=30,kind=1,error=BASE+1056,service=80)
lines.append('$display("PASS strided-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"response leak");$finish;end endmodule')
label=('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));files=[tb,rtl]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
bus={};stops={};rfactual={};byteactual={};performance={}
for line in r.stdout.splitlines():
 f=line.split()
 if f[0]=='BUS':bus.setdefault(int(f[1]),[]).append((int(f[2],16),int(f[3]),int(f[4]),int(f[5],16)))
 elif f[0]=='STOP':stops[int(f[1])]=tuple(map(int,f[2:]))
 elif f[0]=='RF':rfactual.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif f[0]=='BYTE':byteactual.setdefault(int(f[1]),{})[int(f[2])]=int(f[3],16)
 elif f[0]=='PERF':performance[int(f[1])]=dict(cycles=int(f[2]),context_reads=int(f[3]))
for i,want in expected.items():
 got=bus.get(i,[]);assert len(got)==len(want),(i,len(got),len(want))
 for x,y in zip(got,want,strict=True):assert x[:3]==y[:3] and (not x[2] or x[3]&((1<<(8*(1<<x[1])))-1)==y[3]),(i,x,y)
for i,(stop,count,start) in stops.items():
 spec=cases[i];regs=list(spec['old_rf']);data=bytearray(spec['old_memory']);pred=0xa596;addresses=[]
 for e in range(stop):
  if not pred>>e&1:continue
  addr=(spec['base']+e*spec['stride'])&M;addresses.append(addr);chunk=16+e//8;shift=8*(e%8);pos=addr-BASE-1024
  if spec['write']:data[pos]=(regs[chunk]>>shift)&255
  else:regs[chunk]=(regs[chunk]&~(255<<shift))|(data[pos]<<shift)
 assert rfactual[i]==dict(enumerate(regs)),(i,spec,stops[i],[(k,hex(v),hex(rfactual[i][k])) for k,v in enumerate(regs) if rfactual[i][k]!=v])
 assert byteactual[i]=={1024+k:v for k,v in enumerate(data)},i
 got=[x[0] for x in bus.get(i,[])];assert got[:len(addresses)]==addresses,(i,got,addresses)
 assert len(got)==1 and got[0]==spec['base'] if spec['fault_stop'] else len(got)==len(addresses) if spec['write'] else len(addresses)<=len(got)<=len(addresses)+1,(i,got,addresses)
assert all(coverage.values()),coverage
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/memory/VectorMemoryEngine.scala']
result=dict(status='PASS',cases=len(cases),coverage=coverage,case_specs=cases,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS strided-engine')),scope='REGISTERED_8KIB_MODULO_BACKING_WITH_FULL_64BIT_ADDRESS_ORACLE; PHYSICAL_NORMAL_RAM_ONLY',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
