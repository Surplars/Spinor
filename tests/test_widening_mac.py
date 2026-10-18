#!/usr/bin/env python3
"""RVV widening MAC oracle: immutable three-source snapshots and exact Python sums/products."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/widening-mac';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--smoke',action='store_true');p.add_argument('--mapped',action='store_true')
p.add_argument('--top',choices=['RamVectorFp','RamVector','RamVector16'],default='RamVectorFp');args=p.parse_args()
assert not args.mapped or args.smoke
fp=args.top=='RamVectorFp';rng=random.Random(0x364d4143);M64=(1<<64)-1;M128=(1<<128)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else ''))
h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"widening-mac premature commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1)
h=h.replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_writesScalar!==wr || io_completion_bits_illegal!==illegal)$fatal(1,"widening-mac stalled reply changed");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[rng.getrandbits(128) for _ in range(32)];versions=0;vl=0;typ=1<<63;start=0;case=0;maximum=0
seen_types=set();bench=[]
coverage={k:0 for k in ['signed','unsigned','signed_unsigned','unsigned_signed','vv','vx','illegal','bad_width','bad_emul','bad_form','bad_opcode','misaligned','bad_overlap','old_destination','same_source','fraction_source','masked_source_v0','masked_vd0','zero_vl','restart','restart_active','nop_start','masked','all_masked','source_v0','dest_v0','source_cross_register','second_cross_register','destination_cross_register','negative_product','mixed_negative_unsigned','full_product_high_half','scalar_truncation','flush']}
def state():
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_vxrm!==2'd2 || io_vxsat!==1'b1)$fatal(1,\"widening-mac state {case}\");")
 if fp:lines.append('if(io_frm!==3\'d3 || io_fflags!==5\'d21)$fatal(1,"widening-mac FP state");')
def cmd(inst,result=0,writes=0,scalar=0,avl=0,bad=False,record=False,check=True):
 global case
 lines.append(f"command(32'h{inst:08x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x2555<<64)|case:x},1'b{int(bad)},64'h{result&M64:x},1'b{writes},{0 if record else rng.randrange(6)},8'd{vl},64'h{typ:x});")
 case+=1
 if check:state()
def ctx(r,wr=False):
 for k in range(2):
  x=(regs[r]>>(64*k))&M64;lines.append(f"ctx({2*r+k},1'b{int(wr)},64'h{x:x},64'h{x:x});")
def checkregs():
 for r in range(32):ctx(r)
def config(s,m,length):
 global vl,typ,start,maximum
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,maximum);typ=(s<<3)|m|(rng.randrange(4)<<6);start=0
 cmd((typ<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,result=vl,writes=1,avl=length)
def setstart(value):
 global start
 old=start;start=value&127;cmd((8<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=value,result=old,writes=1)
def geometry():
 bits=8<<(typ>>3&3);wide=2*bits
 source_bytes=maximum*bits//8;dest_bytes=maximum*wide//8
 return bits,wide,max(1,(source_bytes+15)//16),max(1,(dest_bytes+15)//16),source_bytes,dest_bytes

def overlap(a,na,b,nb):return a<b+nb and b<a+na
def packed(snapshot,base,count):return sum(snapshot[base+j]<<(128*j) for j in range(count))
def execute(code,form,vd=8,src=16,other=24,vm=1,scalar=0,record=False):
 global start,versions
 bits,wide,ncount,dcount,sbytes,dbytes=geometry()
 ov2=overlap(vd,dcount,src,ncount);ov1=form==2 and overlap(vd,dcount,other,ncount)
 high2=ov2 and sbytes>=16 and src+ncount==vd+dcount
 high1=ov1 and sbytes>=16 and other+ncount==vd+dcount
 bad_overlap=ov2 or ov1 # old vd is a wide source; all narrow-source overlap reads two EEWs
 misaligned=vd%dcount!=0 or src%ncount!=0 or form==2 and other%ncount!=0
 bad=bool(typ>>63 or code not in [0x3c,0x3d,0x3e,0x3f] or (code==0x3e and form==2) or form not in [2,6] or wide>64 or dbytes>128 or misaligned or bad_overlap or not vm and (vd==0 or src==0 or form==2 and other==0))
 inst=(code<<26)|(vm<<25)|(src<<20)|(other<<15)|(form<<12)|(vd<<7)|0x57
 if bad:
  coverage['illegal']+=1;coverage['bad_width']+=int(wide>64);coverage['bad_emul']+=int(dbytes>128)
  coverage['bad_form']+=int(form not in [2,6] or (code==0x3e and form==2));coverage['bad_opcode']+=int(code not in [0x3c,0x3d,0x3e,0x3f])
  coverage['misaligned']+=int(misaligned);coverage['bad_overlap']+=int(bad_overlap)
  coverage['masked_source_v0']+=int(not vm and (src==0 or form==2 and other==0));coverage['masked_vd0']+=int(not vm and vd==0)
 else:
  snapshot=list(regs);data=packed(snapshot,src,ncount);second=packed(snapshot,other,ncount) if form==2 else scalar
  active=[i for i in range(start,vl) if vm or snapshot[0]>>i&1]
  for i in active:
   raw_a=data>>(i*bits)&((1<<bits)-1)
   raw_b=(second>>(i*bits) if form==2 else scalar)&((1<<bits)-1)
   a=raw_a-(1<<bits) if code in [0x3d,0x3e] and raw_a>>(bits-1) else raw_a
   b=raw_b-(1<<bits) if code in [0x3d,0x3f] and raw_b>>(bits-1) else raw_b
   old_d=packed(snapshot,vd,dcount)>>(i*wide)&((1<<wide)-1)
   mathematical=a*b+old_d;value=mathematical&((1<<wide)-1)
   coverage['old_destination']+=int(old_d!=0)
   row=vd+i*wide//128;offset=i*wide%128;mask=((1<<wide)-1)<<offset
   regs[row]=(regs[row]&~mask)|(value<<offset)
   coverage['source_cross_register']+=int(i*bits>=128);coverage['second_cross_register']+=int(form==2 and i*bits>=128)
   coverage['destination_cross_register']+=int(i*wide>=128);coverage['negative_product']+=int(a*b<0)
   coverage['mixed_negative_unsigned']+=int((code==0x3e and a<0 and raw_b>=(1<<(bits-1))) or (code==0x3f and b<0 and raw_a>=(1<<(bits-1))))
   coverage['full_product_high_half']+=int(value>>bits!=0)
  if start<vl:versions^=((1<<dcount)-1)<<vd
  coverage[{0x3c:'unsigned',0x3d:'signed',0x3e:'unsigned_signed',0x3f:'signed_unsigned'}[code]]+=1;coverage['vv' if form==2 else 'vx']+=1
  coverage['same_source']+=int(form==2 and src==other)
  coverage['fraction_source']+=int(sbytes<16);coverage['scalar_truncation']+=int(form==6 and scalar>=(1<<bits))
  coverage['zero_vl']+=int(vl==0);coverage['restart']+=int(start!=0);coverage['restart_active']+=int(0<start<vl)
  coverage['nop_start']+=int(start>=vl and vl!=0);coverage['masked']+=int(not vm);coverage['all_masked']+=int(not active and vl>start)
  coverage['source_v0']+=int(src==0);coverage['dest_v0']+=int(vd==0);seen_types.add(typ&63);start=0
 if record:lines.append('begin integer begun;begun=cycles;')
 cmd(inst,scalar=scalar,bad=bad,record=record)
 if record:
  ident=len(bench);bench.append(dict(id=ident,code=code,form=form,vl=vl,vm=vm,vtype=typ&63))
  lines.append(f'$display("WMACPERF {ident} %0d",cycles-begun);end')
 checkregs()

def seed(src=16,other=24,pattern=0):
 bits,wide,ncount,dcount,sbytes,dbytes=geometry()
 for r in range(32):regs[r]=rng.getrandbits(128)
 if wide<=64 and dbytes<=128:
  for base in [src,other]:
   values=[0,1,(1<<(bits-1))-1,1<<(bits-1),(1<<bits)-1,2,0x55,0xaa]
   for i in range(maximum):
    row=base+i*bits//128;offset=i*bits%128;mask=((1<<bits)-1)<<offset
    value=values[(i+(1 if base==other else 0))%8] if pattern%2==0 else rng.getrandbits(bits)
    regs[row]=(regs[row]&~mask)|((value&((1<<bits)-1))<<offset)
 if src!=0 and other!=0:regs[0]=0 if pattern==3 else rng.getrandbits(128)
 for r in range(32):ctx(r,True)

cmd((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=1,writes=1,check=False)
cmd((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=2,writes=1,check=False)
if fp:
 cmd((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=21,writes=1,check=False)
 cmd((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,scalar=3,writes=1,check=False)
for r in range(32):ctx(r,True)
execute(0x3c,6) # vill and VL0 must still reject
all_types=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
types=[(0,0),(2,0),(0,5),(3,0),(0,3)] if args.smoke else all_types
for s,m in types:
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m))
 for code in [0x3c,0x3d,0x3e,0x3f]:
  for form in [2,6]:
   for scenario in ([0,2] if args.smoke else range(7)):
    config(s,m,[mx,0,max(1,mx-1),mx,1,mx,mx][scenario]);seed(pattern=scenario)
    if scenario==4:setstart(127)
    if scenario==5:setstart(max(1,mx//2))
    execute(code,form,vm=int(scenario not in [2,3]),scalar=M64,record=scenario==0)
   for length in ([0] if args.smoke else [0,mx]):
    config(s,m,length);bits,wide,ncount,dcount,sbytes,dbytes=geometry()
    execute(code,form,vd=16) # low narrow-source overlap is reserved
    execute(code,form,vd=0,vm=0);execute(code,form,src=0,vm=0)
    if form==2:execute(code,form,other=16);execute(code,form,other=0,vm=0)
    if dcount>1:execute(code,form,vd=9)
    if not args.smoke:
     if ncount>1:execute(code,form,other=25 if form==2 else 24);execute(code,form,src=17)
   if not args.smoke:
    config(s,m,mx);seed();execute(code,form,src=8+dcount-ncount)
    seed();execute(code,form,other=8+dcount-ncount)
# Upper group v24..v31 and odd restarted elements expose source/destination
# byte-offset confusion in serialized multiply return paths.
for s,m in ([(0,2),(2,0)] if args.smoke else [(0,2),(1,2),(2,2),(0,5)]):
 config(s,m,128);bits,wide,ncount,dcount,sbytes,dbytes=geometry()
 for code in [0x3c,0x3d,0x3e,0x3f]:
  seed()
  for scalar in ([0,M64] if args.smoke else [0,1,(1<<bits)-1,1<<(bits-1),1<<32,1<<63,M64]):execute(code,6,scalar=scalar)
  seed(src=24+dcount-ncount,other=8);setstart(1);execute(code,2,vd=24,src=24+dcount-ncount,other=8,record=True)
  seed();execute(code,2,other=8+dcount-ncount)
  seed();execute(code,2,vd=24,src=8,other=16)
config(0,0,16);seed(pattern=3);execute(0x3c,2,vm=0)
seed(src=0);execute(0x3e,6,src=0,scalar=M64)
seed();execute(0x3d,6,vd=0,scalar=M64)
seed();execute(0x3d,2,other=16)
config(0,5,2);seed();execute(0x3c,6);execute(0x3e,6,vd=16)
config(2,0,4);seed();setstart(127);execute(0x3d,6,scalar=M64)
# M40 implements OPFVV/OPFVF at this funct6. Keep negative probes reserved;
# their positive FP semantics are covered by test_fp_widen_arithmetic.py.
for form in [0,1,3,4,5]:execute(0x39 if fp and form in [1,5] else 0x3c,form)
for form in [2,6]:execute(0x39,form)
# Sampling the reused multiplier's partial-product/align/accumulate phases,
# owner flush and indefinitely held completion; no result is published early.
for code in [0x3c,0x3d,0x3e,0x3f]:
 for form in [2,6]:
  if code==0x3e and form==2:continue
  config(2,0,4);seed();inst=(code<<26)|(1<<25)|(16<<20)|(24<<15)|(form<<12)|(8<<7)|0x57
  for delay in ([0,17,85] if args.smoke else [0,2,*range(5,35),40,50,70,90,110,130,180,260]):
   lines.append(f"cancel(32'h{inst:x},{delay},0);");state();checkregs();coverage['flush']+=1
  lines.append(f"cancel(32'h{inst:x},0,1);");state();checkregs();coverage['flush']+=1
  execute(code,form,scalar=M64,record=True)
lines+=['$display("PASS widening-mac commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=args.top+('-smoke' if args.smoke else '-full')+('-mapped' if args.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{args.top}/mapped.v' if args.mapped else f'build/rtl/{args.top}.sv');files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{args.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(args.top+'.','tb.dut.'));files.append(f);extra=['-s',args.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={args.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(s.split()[1]):int(s.split()[2]) for s in run.stdout.splitlines() if s.startswith('WMACPERF ')};assert len(observed)==len(bench)
for row in bench:row['cycles']=observed[row['id']]
assert all(coverage.values()),coverage
result=dict(status='PASS',top=args.top,mapped=args.mapped,commands=case,coverage=coverage,types=sorted(seen_types),performance=bench,summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS widening-mac')),
 sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['sha256','performance']},indent=2))
