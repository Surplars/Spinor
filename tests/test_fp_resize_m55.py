#!/usr/bin/env python3
"""RVV width conversions: independent whole-register oracle plus SoftFloat."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from reference_fp_resize_m54 import ResizeReference
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m55/fp-resize';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVectorFp16','RamVector','RamVector16'],default='RamVectorFp');a=p.parse_args();assert not a.mapped or a.compact
fp='Fp' in a.top;ref=ResizeReference();rng=random.Random(0x4150494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','10000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;'+('reg [4:0] oldFlags;' if fp else ''))
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;'+('oldFlags=io_fflags;' if fp else '')+'io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart)$fatal(1,"premature resize publish");'+('if(io_fflags!==oldFlags)$fatal(1,"premature resize flags");' if fp else '')
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall)begin '+guard+' if(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable resize reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;frm=0;flags=0;commands=0;performance=[];types=set();encodings=set()
ops={8:21,9:22,10:23,11:24,12:28,14:25,15:26,16:21,17:22,18:23,19:24,20:28,21:29,22:25,23:26}
coverage={k:0 for k in ['wide','narrow','int16_fp32','fp32_int16','round_odd','rtz','reserved_frm_fixed','illegal','masked','all_masked','restart','no_work','zero_vl','overlap_high','overlap_low','overlap_bad','cross_register','fflags','flush','reserved_selector']}
def ctx(r,write=False):
 for k in range(2):
  v=regs[r]>>(64*k)&M64;lines.append(f"ctx({2*r+k},{int(write)},64'h{v:x},64'h{v:x});")
def checkregs():
 for r in range(32):ctx(r)
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!=={start} || io_vxrm!==2 || io_vxsat!==1)$fatal(1,\"resize state {commands}\");")
 if fp:lines.append(f'if(io_frm!=={frm} || io_fflags!=={flags})$fatal(1,"resize FP state {commands}");')
def cmd(inst,scalar=0,result=0,write=False,bad=False,avl=0,record=None):
 global commands
 if record:lines.append('begin integer begun;begun=cycles;')
 lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x41ab<<64)|commands:x},{int(bad)},64'h{result&M64:x},{int(write)},{0 if record else rng.randrange(5)},8'd{vl},64'h{typ:x});");commands+=1
 if record:
  i=len(performance);performance.append(dict(id=i,**record));lines.append(f'$display("PERF {i} %0d",cycles-begun);end')
 checkregs()
def csr(address,value):
 global start,frm,flags
 if address==8:old=start;start=value
 elif address==2:old=frm;frm=value
 elif address==1:old=flags;flags=value
 else:raise AssertionError(address)
 cmd(address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,result=old,write=True)
def config(s,m,length):
 global vl,typ,start
 maximum=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(maximum,length);typ=s<<3|m;start=0
 cmd(typ<<20|1<<15|7<<12|3<<7|0x57,result=vl,write=True,avl=length)
def seed(bits):
 values={8:[0,1,127,128,255],16:[0,1,0x7fff,0x8000,0xffff],32:[0,1,0x80000000,0x3f800000,0xbf800000,0x4f800000,0x47000000,0xc7000000,0x7f800001,0x7fc12345,0x7f800000,0xffffffff],64:[0,1,0x8000000000000000,0x3ff0000000000000,0x3ff0000010000000,0x3690000000000000,0x7ff0000000000001,0x7fefffffffffffff,0x7ff0000000000000,0xffffffffffffffff]}
 for r in range(32):
  regs[r]=sum(rng.choice(values[min(bits,64)])<<(min(bits,64)*k) for k in range(128//min(bits,64)));ctx(r,True)
 regs[0]=int('a596'*8,16);ctx(0,True)
def elem(snapshot,r,i,bits):return snapshot[r+i*bits//128]>>(i*bits%128)&((1<<bits)-1)
def execute(sub,vd=8,src=16,vm=1,record=False):
 global start,versions,flags
 s=typ>>3&3;m=typ&7;wide=sub<16;op=ops.get(sub,31);n=1<<m if m<4 else 1;double=2*n if m<4 else 1;dstCount=double if wide else n;srcCount=n if wide else double
 outbits=(8<<s)*(2 if wide else 1);inbits=(8<<s)*(1 if wide else 2)
 overlap=vd<src+srcCount and src<vd+dstCount;allowed=(src==vd+dstCount-srcCount and m<4) if wide else vd==src
 small=s==1 and (wide and op in [23,24,28] or not wide and op in [21,22,25,26,28]);badType=s!=2 and not small
 bad=bool(not fp or typ>>63 or sub not in ops or badType or m==3 or vd%dstCount or src%srcCount or overlap and not allowed or not vm and (vd==0 or src==0) or frm>4 and op not in [25,26,29])
 initial=start;old=tuple(regs)
 if bad:
  coverage['illegal']+=1;coverage['overlap_bad']+=int(overlap and not allowed);coverage['reserved_selector']+=int(sub not in ops)
 else:
  active=[i for i in range(start,vl) if vm or old[0]>>i&1]
  for i in active:
   v,f=ref(op,(1 if wide else 2)+(4 if s==1 else 0),wide and s==2,frm,elem(old,src,i,inbits))
   row=vd+i*outbits//128;offset=i*outbits%128;mask=((1<<outbits)-1)<<offset;regs[row]=(regs[row]&~mask)|(v<<offset);flags|=f
   coverage['fflags']+=int(f!=0);coverage['cross_register']+=int(i*outbits>=128 or i*inbits>=128)
  if start<vl:versions^=((1<<dstCount)-1)<<vd
  types.add(typ);encodings.add(sub);coverage['wide' if wide else 'narrow']+=1;coverage['int16_fp32']+=int(s==1 and wide);coverage['fp32_int16']+=int(s==1 and not wide);coverage['round_odd']+=int(op==29);coverage['rtz']+=int(op in [25,26]);coverage['reserved_frm_fixed']+=int(frm>4)
  coverage['masked']+=int(not vm);coverage['all_masked']+=int(start<vl and not active);coverage['restart']+=int(start!=0);coverage['no_work']+=int(start>=vl);coverage['zero_vl']+=int(vl==0);coverage['overlap_high']+=int(overlap and wide);coverage['overlap_low']+=int(overlap and not wide);start=0
 inst=0x12<<26|vm<<25|src<<20|sub<<15|1<<12|vd<<7|0x57
 cmd(inst,bad=bad,record=dict(selector=sub,vtype=typ,vl=vl,vstart=initial,frm=frm,sew=8<<s) if record and not bad else None)
lines.append("command(32'h00a091f3,2,0,0,0,0,0,1,0,0,64'h8000000000000000);command(32'h009091f3,1,0,0,0,0,0,1,0,0,64'h8000000000000000);");commands+=2
for r in range(32):ctx(r,True)
execute(8)
alltypes=[(s,m) for m in [0,1,2,3,5,6,7] for s in range(4) if m<4 or s<=m-5]
for s,m in ([(1,0),(2,0),(3,0)] if a.compact else alltypes):
 config(s,m,4 if a.compact else 128)
 for sub in ops:
  seed((8<<s)*(1 if sub<16 else 2))
  for rm in ([0] if a.compact else range(8)):
   if fp:
    if not a.compact:csr(2,rm)
    csr(1,0)
   execute(sub,record=True)
  if not a.compact:
   if fp:csr(2,0)
   csr(8,1);execute(sub,vm=0)
   execute(sub,vd=16);execute(sub,vd=16,src=16+((1<<m) if m<3 else 1))
   execute(sub,vd=9);execute(sub,src=17);execute(sub,vm=0,src=0)
 if not a.compact:
  regs[0]=0;ctx(0,True)
  for sub in ops:execute(sub,vm=0)
  config(s,m,0)
  for sub in ops:execute(sub)
config(2,0,3);seed(64)
for sub in ([8,11,20,21,23] if a.compact else ops):
 if fp:csr(2,7)
 execute(sub)
 if fp:csr(2,0)
 execute(sub);csr(8,127);execute(sub)
 if fp:
  for delay in ([0,12] if a.compact else [0,1,3,8,12,20,40,70,100]):
   lines.append(f"cancel(32'h{0x12<<26|1<<25|16<<20|sub<<15|1<<12|8<<7|0x57:x},{delay},0);");coverage['flush']+=1;checkregs()
  lines.append(f"cancel(32'h{0x12<<26|1<<25|16<<20|sub<<15|1<<12|8<<7|0x57:x},0,1);");coverage['flush']+=1;checkregs()
config(1,0,4);seed(32)
for sub in [12,20]:
 if fp:csr(2,0);csr(1,0)
 csr(8,1);execute(sub,vm=0)
 if fp:
  for delay in [0,1,3,8,12,20,40,70,100]:
   lines.append(f"cancel(32'h{0x12<<26|1<<25|16<<20|sub<<15|1<<12|8<<7|0x57:x},{delay},0);");coverage['flush']+=1;checkregs()
for sub in [4,5,13,24,31]:execute(sub)
lines.append('$display("PASS fp-resize commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule')
label=a.top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/(f'build/m55/synth/{a.top}/mapped.v' if a.mapped else f'build/m55/rtl/{a.top}.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/m55/rtl/verification/assert/{a.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(a.top+'.','tb.dut.'));files.append(f);extra=['-s',a.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
r=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
# The unrolled full-test executable is ~310MiB and is reproducible from the
# bound RTL/TB. Keep these inputs/logs rather than retaining an unbound cache.
if not a.compact and not a.mapped:(OUT/label).unlink()
observed={int(x.split()[1]):int(x.split()[2]) for x in r.stdout.splitlines() if x.startswith('PERF ')};assert len(observed)==len(performance)
for row in performance:row['cycles']=observed[row['id']]
files=[rtl,tb,Path(__file__).resolve(),ROOT/'tests/reference_fp_resize_m54.py',ROOT/'tests/fp_resize_reference_m54.c',ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/core/RamVector.scala',ROOT/'src/main/scala/vpu/execute/fp/FloatingPointLane.scala']
d=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),encodings=sorted(encodings),performance=performance,reference_anchors=ref.anchors,summary=next(x for x in r.stdout.splitlines() if x.startswith('PASS fp-resize')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files});(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(d['summary'])
