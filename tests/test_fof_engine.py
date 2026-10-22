#!/usr/bin/env python3
"""Independent FOF unit/segment oracle: all RF bytes, addresses, partial fields and restart units."""
import argparse,hashlib,json,random,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fof-engine';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');a=p.parse_args()
M=(1<<64)-1;BASE=0x80000000;N=8192;rng=random.Random(0x48a55)
rtl=ROOT/('build/synth/VectorMemoryEngine/mapped.v' if a.mapped else 'build/rtl/VectorMemoryEngine.sv')
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
fixture=(ROOT/'tests/memory_engine_fixture.sv').read_text().replace('if(io_context_bits_write)rf[io_context_bits_address]<=io_context_bits_data;', 'if(io_context_bits_write)begin rf[io_context_bits_address]<=io_context_bits_data;$display("WRITE %0d %0d %016h",caseid,io_context_bits_address,io_context_bits_data);end ')
fixture=fixture.replace('if(io_commit_valid && io_commit_ready)begin io_vstart<=io_commit_bits;',
 'if(io_commit_valid && io_commit_ready)begin if(io_trim_valid)begin io_vl<=io_trim_bits;$display("TRIM %0d %0d",caseid,io_trim_bits);end io_vstart<=io_commit_bits;')
fixture=fixture.replace('reg [159:0] held;begin','reg [159:0] held;reg [7:0] heldVl;begin').replace('repeat(4)begin tick();if(!io_completion_valid','heldVl=io_vl;repeat(4)begin tick();if(io_vl!==heldVl)$fatal(1,"VL changed with held completion");if(!io_completion_valid')
fixture=fixture.replace('stopDelay>=0 && !stopped && cycles-begun>=stopDelay','(stopAtError ? (io_memoryResponse_valid && perror!=0) : stopDelay>=0 && cycles-begun>=stopDelay) && !stopped')
fixture=fixture.replace('io_status_element:length,requests-breq','io_status_element:io_vl,requests-breq')
extra='reg stopAtError=0;reg priorTrim=0;reg [7:0] priorLength;always @(posedge clock)if(!reset)begin if(heldCommit && (io_trim_valid!==priorTrim || (priorTrim && io_trim_bits!==priorLength)))$fatal(1,"unstable VL metadata");priorTrim<=io_trim_valid;priorLength<=io_trim_bits;end'
fixture=fixture.replace('task tick;',extra+'\n task tick;')
lines.append(fixture);specs=[];models={};encodings=set();coverage={k:0 for k in ['unit','segment','trim','trap_zero','masked_zero','nonzero_start','empty','fractional','grouped','last_register','v0','partial_field','local_fault','response_fault','illegal','stop','error_beats_stop','cold']}
def issue(ew,n,typ=None,vl=2,start=0,vr=8,pred=None,base=BASE+1024,kind=0,error=None,stop=None,bits=0,write=False,fof=True,cold=False,race=False,mop=0):
 typ=ew<<3 if typ is None else typ;sew=typ>>3&7;lm=(typ&7) if typ&7<4 else (typ&7)-8;emul=lm+ew-sew;group=1<<max(0,emul);w=1<<ew
 bad=typ>>63!=0 or sew>3 or typ&7==4 or lm<0 and sew>3+lm or emul not in range(-3,4) or group*n>8 or vr%group!=0 or vr+group*n>32 or pred is not None and vr==0 or bool(bits) or write and fof and mop==0
 ident=len(specs);inst=((n-1)<<29)|(mop<<26)|(int(pred is None)<<25)|((16 if fof or mop else 0)<<20)|(1<<15)|([0,5,6,7][ew]<<12)|(vr<<7)|(0x27 if write else 7)|bits
 rf=[rng.getrandbits(64) for _ in range(64)];mem=bytearray((j*13+7)&255 for j in range(N))
 if pred is not None:rf[0]=pred&M;rf[1]=pred>>64
 if mop in [1,3]:
  rf[32]=0;rf[33]=0
  if ew==3:rf[33]=n*w
  else:rf[32]=(n*w)<<(8*w)
 initial=rf.copy();seq=[];failure=None;errorAddress=M if error is None else (base+(error[0]*n+error[1])*w)&M
 if not bad:
  for e in range(start,vl):
   if pred is not None and not(pred>>e&1):continue
   for f in range(n):
    addr=(base+(e*n+f)*w)&M;chunk=2*(vr+f*group)+e*w//8;shift=e*w%8*8
    if addr&(w-1):failure=(e,4,addr);break
    if addr>>28!=BASE>>28:failure=(e,5,addr);break
    seq.append((e,f,addr,chunk,shift))
    if kind and addr==errorAddress:failure=(e,5,addr);break
   if failure:break
 if cold:lines.append('reset=1;tick();tick();reset=0;tick();')
 for j,x in enumerate(initial):lines.append(f"rf[{j}]=64'h{x:x};")
 lines.append(f"for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={ident};kind={kind};latency={3 if kind else 1};errorAddress=64'h{errorAddress:x};stopAtError={int(race)};")
 trim=bool(fof and mop==0 and failure and failure[0]>0);trap=bool(failure and not trim);e,c,tval=failure if trap else (0,0,0);ns=start if bad else e if trap else 0;newvl=failure[0] if trim else vl
 lines.append(f"run(32'h{inst:x},64'h{base&M:x},64'h{n*w:x},64'h{typ:x},{vl},{start},{int(bad)},{int(trap)},{c},{e},{ns},{len(seq)},64'h{tval:x},{-1 if stop is None else stop});")
 if stop is None or race:lines.append(f'if(io_vl!==8\'d{newvl})$fatal(1,"FOF VL case {ident}");')
 else:lines.append(f'if(io_vl!==8\'d{vl})$fatal(1,"interrupt reduced VL");')
 for j in range(64):lines.append(f'$display("RF {ident} {j} %016h",rf[{j}]);')
 specs.append(dict(id=ident,eew=w*8,nfields=n,vtype=typ,vl=vl,vstart=start,vr=vr,masked=pred is not None,illegal=bool(bad),fof=fof and mop==0,mop=mop,write=write,error=error,kind=kind,stop=stop,race=race,cold=cold,trim=trim,final_vl=newvl))
 models[ident]=dict(rf=initial,sequence=seq,width=w,write=write,failure=failure,stop=stop,vl=vl,trim=trim,race=race)
 if not bad and fof and mop==0:encodings.add((ew,n))
 for k,v in [('unit',n==1),('segment',n>1),('trim',trim),('trap_zero',trap and failure[0]==0),('masked_zero',pred is not None and not(pred&1)),('nonzero_start',start>0),('empty',start>=vl),('fractional',emul<0 and not bad),('grouped',group>1 and not bad),('last_register',vr+group*n==32 and not bad),('v0',vr==0 and not bad),('partial_field',failure is not None and error is not None and error[1]>0),('local_fault',failure is not None and not kind),('response_fault',failure is not None and kind),('illegal',bad),('stop',stop is not None),('error_beats_stop',race),('cold',cold)]:coverage[k]+=int(bool(v))
# Every encoding is exercised cold with a zero-index trap and a later-index trim.
for n in range(1,9):
 for ew in range(4):
  for e in [0,1]:issue(ew,n,kind=1,error=(e,n-1),cold=True)
  for start,pred in [(0,None),(1,None),(0,2),(0,0),(2,None),(127,None)]:issue(ew,n,start=start,pred=pred)
  issue(ew,n,kind=1,error=(1,0),pred=2)
  issue(ew,n,kind=1,error=(1,n-1),start=1)
  issue(ew,n,vr=32-n);issue(ew,n,vr=0)
  issue(ew,n,vl=0);issue(ew,n,write=True,vl=0)
  for kind in range(1,6):
   for e in [0,1]:
    for f in (sorted({0,n-1}) if a.compact else range(n)):issue(ew,n,kind=kind,error=(e,f))
  # Fault at a later segment caused by crossing the physical RAM window.
  issue(ew,n,base=BASE+(1<<28)-n*(1<<ew))
  if ew:
   issue(ew,n,base=BASE+1)
   issue(ew,n,base=BASE+1,start=1)
  issue(ew,n,base=BASE+1,pred=0)
# All legal EMUL/SEW combinations use an independent geometry calculation.
types=[s<<3|m for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for n in range(1,9):
 for ew in range(4):
  for typ in ([ew<<3] if a.compact else types):
   lm=(typ&7) if typ&7<4 else (typ&7)-8;sew=typ>>3&7;emul=lm+ew-sew;group=1<<max(0,emul)
   if emul not in range(-3,4) or group*n>8:continue
   maximum=int(16/(1<<sew)*2**lm)
   issue(ew,n,typ,maximum)
   issue(ew,n,typ,maximum,min(maximum,127))
   if maximum>1:issue(ew,n,typ,maximum,kind=2,error=(1,n-1))
for t,ew,n,vr in [(1,0,4,10),(2,0,2,4),(8,0,8,8),(5,0,8,8),(14,0,8,8),(23,0,8,8)]:
 issue(ew,n,t,vl=1,vr=vr)
for typ,ew,n,vr,pred,bits in [(2,0,3,8,None,0),(1,0,8,8,None,0),(1,0,4,9,None,0),(0,0,8,25,None,0),(1<<63,0,2,8,None,0),(4,0,2,8,None,0),(29,0,2,8,None,0),(3,3,2,8,None,0),(0,0,2,0,1,0),(0,0,2,8,None,1<<28),(0,0,2,8,None,1<<12)]:
 issue(ew,n,typ,vl=0,start=127,vr=vr,pred=pred,bits=bits)
for t,ew in [(4,3),(29,0),(32,0)]:
 for vl in [0,2]:issue(ew,1,t,vl=vl)
for mop in [1,2,3]:
 for ew,n in [(0,1),(1,3),(3,2)]:issue(ew,n,mop=mop,kind=1,error=(1,n-1))
for ew,n in [(0,3),(3,2),(0,1)]:
 for delay in ([0,35,80,160] if a.compact else range(0,201,5)):issue(ew,n,vl=2 if ew==3 else 4,stop=delay)
 issue(ew,n,kind=1,error=(1,n-1),stop=0,race=True)
 # An ordinary load after a FOF trim must retain ordinary fault semantics.
 issue(ew,n,kind=1,error=(1,n-1),fof=False)
lines.append('$display("PASS fof-engine cases=%0d requests=%0d responses=%0d cycles=%0d",caseid+1,requests,responses,cycles);if(requests!=responses)$fatal(1,"leaked response");$finish;end endmodule')
label=('compact' if a.compact else 'full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));files=[tb,rtl]
if a.mapped:files.append(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
bus={};writes={};stops={};actualRF={};actualMem={};performance={};trims={}
for line in r.stdout.splitlines():
 f=line.split()
 if not f:continue
 i=int(f[1]) if f[0] in ['BUS','WRITE','STOP','RF','BYTE','PERF','TRIM'] else 0
 if f[0]=='BUS':bus.setdefault(i,[]).append((int(f[2],16),int(f[3]),int(f[4]),int(f[5],16)))
 elif f[0]=='WRITE':writes.setdefault(i,[]).append((int(f[2]),int(f[3],16)))
 elif f[0]=='STOP':stops[i]=tuple(map(int,f[2:]))
 elif f[0]=='RF':actualRF.setdefault(i,{})[int(f[2])]=int(f[3],16)
 elif f[0]=='BYTE':actualMem.setdefault(i,{})[int(f[2])]=int(f[3],16)
 elif f[0]=='TRIM':trims.setdefault(i,[]).append(int(f[2]))
 elif f[0]=='PERF':performance[i]=dict(cycles=int(f[2]),context_reads=int(f[3]))
for i,model in models.items():
 rf=model['rf'].copy();mem=bytearray((j*13+7)&255 for j in range(N));seq=model['sequence'];got=bus.get(i,[]);wr=writes.get(i,[]);w=model['width'];failure=model['failure']
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
  if end==model['vl'] and not model['trim']:assert successful==len(seq) and start==0,(i,successful,len(seq))
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
 assert trims.get(i,[])==([failure[0]] if model['trim'] else []),(i,'trim handshake',trims.get(i,[]))
assert all(coverage.values()),coverage;assert len(encodings)==32,encodings
inputs=[rtl,tb,ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve(),ROOT/'src/main/scala/vpu/memory/VectorMemoryEngine.scala']
d=dict(status='PASS',cases=len(specs),encodings=sorted(encodings),coverage=coverage,case_specs=specs,performance=performance,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS fof-engine')),scope='FOF_UNIT_AND_SEGMENTS_1_TO_8; ATOMIC_VL_TRIM; ALL_64_RF_CHUNKS; INDEPENDENT_FIELD_PREFIX_ORACLE; FULL_64BIT_ADDRESSES; 8KIB_MODULO_MEMORY; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
