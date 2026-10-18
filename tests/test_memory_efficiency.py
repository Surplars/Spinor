#!/usr/bin/env python3
"""Replay identical unit-stride commands on frozen M42/current LSU with phase-free service."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/memory-efficiency';OUT.mkdir(parents=True,exist_ok=True)
M=(1<<64)-1;BASE=0x80000000
header=(ROOT/'build/rtl/VectorMemoryEngine.sv').read_text().split('module VectorMemoryEngine(')[1].split(');')[0]
lines=['module tb;'];direction=None;width=''
for part in header.split(','):
 part=part.strip();m=re.fullmatch(r'(input|output)\s*(\[\d+:\d+\])?\s*(\w+)',part)
 if m:direction,width,name=m.group(1),m.group(2) or '',m.group(3)
 else:name=part
 ready=name in ['io_context_ready','io_commit_ready','io_memoryRequest_ready'];lines.append(f'{"wire" if direction=="output" or ready else "reg"} {width} {name}'+(';' if direction=='output' or ready else '=0;'))
fixture=(ROOT/'tests/memory_engine_fixture.sv').read_text().replace('cycles%4!=1','1\'b1').replace('cycles%3!=1','1\'b1')
lines.append(fixture);cases=[]
for ew in range(4):
 width=1<<ew
 for vl in [0,1,2,128>>ew]:
  for start in sorted({0,1,min(127,vl+1)}):
   for masked in [False,True]:
    for write in [False,True]:
     for delay in [0,4]:
      i=len(cases);active=[e for e in range(start,vl) if not masked or e%3!=1];pred=sum(1<<e for e in range(128) if e%3!=1);rf=[(k*0x32100123456789ab+0xabcdee)&M for k in range(64)];rf[0]=pred&M;rf[1]=pred>>64;memory=bytearray((k*13+7)&255 for k in range(8192))
      for k,x in enumerate(rf):lines.append(f"rf[{k}]=64'h{x:x};")
      lines.append(f'for(k=0;k<8192;k=k+1)mem[k]=(k*13+7)&255;caseid={i};latency={delay};kind=0;')
      inst=(int(not masked)<<25)|(1<<15)|([0,5,6,7][ew]<<12)|(8<<7)|(0x27 if write else 7)
      lines.append(f"run(32'h{inst:x},64'h{BASE+1024:x},64'hdeadbeef,64'h{(ew<<3)|3:x},{vl},{start},0,0,0,0,0,{len(active)},0,-1);")
      for e in active:
       chunk=16+e*width//8;shift=8*(e*width%8);mask=((1<<(8*width))-1)<<shift
       if write:memory[1024+e*width:1024+(e+1)*width]=((rf[chunk]>>shift)&((1<<(8*width))-1)).to_bytes(width,'little')
       else:rf[chunk]=(rf[chunk]&~mask)|(int.from_bytes(memory[1024+e*width:1024+(e+1)*width],'little')<<shift)
      for k,x in enumerate(rf):lines.append(f"if(rf[{k}]!==64'h{x:x})$fatal(1,\"unit efficiency RF {i}\");")
      if write:
       for k in range(128):lines.append(f"if(mem[{1024+k}]!==8'h{memory[1024+k]:x})$fatal(1,\"unit efficiency memory {i}\");")
      cases.append(dict(id=i,eew=8<<ew,vl=vl,vstart=start,masked=masked,write=write,service=delay,active=len(active),saved_reads=(2 if not masked and start<vl else 0)+(len(active) if ew==3 and not write else 0)))
lines.append('$display("PASS memory-efficiency cases=%0d cycles=%0d",caseid+1,cycles);$finish;end endmodule');tb=OUT/'tb.sv';tb.write_text('\n'.join(lines));results={}
for label,path in [('M42','archive/m42/rtl/VectorMemoryEngine.sv'),('M43','build/rtl/VectorMemoryEngine.sv')]:
 with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(OUT/label),str(tb),str(ROOT/path)],stdout=log,stderr=log,check=True)
 p=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
 rows={int(f[1]):dict(cycles=int(f[2]),context_reads=int(f[3])) for line in p.stdout.splitlines() if (f:=line.split()) and f[0]=='PERF'};assert len(rows)==len(cases);results[label]=rows
for spec in cases:
 old,new=results['M42'][spec['id']],results['M43'][spec['id']];saved=spec['saved_reads'];assert old['context_reads']-new['context_reads']==saved,(spec,old,new);assert old['cycles']-new['cycles']==2*saved,(spec,old,new)
inputs=[tb,ROOT/'archive/m42/rtl/VectorMemoryEngine.sv',ROOT/'build/rtl/VectorMemoryEngine.sv',ROOT/'tests/memory_engine_fixture.sv',Path(__file__).resolve()]
r=dict(status='PASS',cases=cases,results=results,scope='IDENTICAL_DIRECT_LSU_INPUTS; CONSTANT_READY; ONE_CYCLE_CONTEXT; REGISTERED_FIXED_MEMORY_SERVICE; NO_DEVICE_TIMING',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs});(OUT/'results.json').write_text(json.dumps(r,indent=2)+'\n');print('PASS',len(cases),'frozen/current unit-stride replays: exact cycle and RF-read savings')
