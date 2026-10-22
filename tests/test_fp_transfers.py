#!/usr/bin/env python3
"""Bit-level full-register oracle for FP scalar moves and slide1, not FP arithmetic."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/fp-transfers';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVectorFp16','RamVector','RamVector16'],default='RamVectorFp');a=p.parse_args();assert not a.mapped or a.compact
fp='Fp' in a.top;rng=random.Random(0x3950494e);M64=(1<<64)-1
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','6000000')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,oldVersions;reg [6:0] oldStart;')
h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','oldVersions=io_versions;oldStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==oldVersions || io_vstart!==oldStart)$fatal(1,"premature FP transfer commit");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall)begin '+guard+' if(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"unstable FP reply");',1)
h=h.replace('io_flush=1;#1;if(io_completion_valid','io_completion_ready=1;io_flush=1;#1;if(io_completion_valid',1).replace('tick();io_flush=0;\nrepeat(12)','tick();io_flush=0;io_completion_ready=0;\nrepeat(12)',1)
lines=[h];regs=[0]*32;versions=0;vl=0;typ=1<<63;start=0;frm=0;commands=0;performance=[];types=set();forms=set()
coverage={x:0 for x in ['read','write','up','down','illegal','zero_vl','restart','no_work','f0_write','boxed','unboxed','snan_bits','masked','alias_down','cross_register','flush','reserved_frm','single_register_unaligned']}
def ctx(r,write=False):
 for k in range(2):
  v=regs[r]>>(64*k)&M64;lines.append(f"ctx({2*r+k},{int(write)},64'h{v:x},64'h{v:x});")
def state():
 for r in range(32):ctx(r)
 lines.append(f'if(io_versions!==32\'h{versions:x} || io_vstart!=={start} || io_vxrm!==0 || io_vxsat!==0)$fatal(1,"state {commands}");')
 if fp:lines.append(f'if(io_frm!=={frm} || io_fflags!==21)$fatal(1,"FP flags changed");')
def cmd(inst,scalar=0,result=0,write=False,bad=False,avl=0,record=None):
 global commands
 if record:lines.append('begin integer begun;begun=cycles;')
 lines.append(f"command(32'h{inst:x},64'h{scalar&M64:x},0,64'h{avl:x},80'h{(0x39ab<<64)|commands:x},{int(bad)},64'h{result&M64:x},{int(write)},{0 if record else rng.randrange(5)},8'd{vl},64'h{typ:x});")
 commands+=1
 if record:
  ident=len(performance);performance.append(dict(id=ident,**record));lines.append(f'$display("PERF {ident} %0d",cycles-begun);end')
 state()
def csr(address,value):
 global start,frm
 if address==8:old=start;start=value
 elif address==2:old=frm;frm=value
 else:raise AssertionError(address)
 cmd(address<<20|1<<15|1<<12|3<<7|0x73,scalar=value,result=old,write=True)
def config(s,m,length):
 global vl,typ,start
 mx=(16>>s)*(1<<m) if m<4 else (16>>s)//(1<<(8-m));vl=min(length,mx);typ=s<<3|m;start=0
 cmd(typ<<20|1<<15|7<<12|3<<7|0x57,result=vl,write=True,avl=length)
def seed():
 for r in range(32):regs[r]=rng.getrandbits(128);ctx(r,True)
 regs[0]=int('a596'*8,16);ctx(0,True)
def inst(kind,vd,src,vm=1):return (0x10 if kind in ['read','write'] else 0xe if kind=='up' else 0xf)<<26|vm<<25|(0 if kind=='write' else src)<<20|(0 if kind=='read' else 1)<<15|(1 if kind=='read' else 5)<<12|vd<<7|0x57
def execute(kind,vd=8,src=16,scalar=0xffffffff7f800001,vm=1,force_bad=False,record=False):
 global versions,start
 s=typ>>3&3;bits=8<<s;mask=(1<<bits)-1;group=(1<<(typ&7)) if typ&7<4 else 1;old=tuple(regs);move=kind in ['read','write'];initial=start
 bad=bool(force_bad or not fp or typ>>63 or s<2 or (move and not vm) or (not move and (vd%group or src%group or (kind=='up' and vd==src) or (not vm and (vd==0 or src==0)))))
 result=0;writes=False
 if bad:coverage['illegal']+=1
 else:
  scalarBits=scalar&mask if s==3 or scalar>>32==0xffffffff else 0x7fc00000
  coverage[kind]+=1;forms.add(kind);types.add(typ);coverage['zero_vl']+=int(vl==0);coverage['restart']+=int(start!=0);coverage['no_work']+=int(start>=vl);coverage['reserved_frm']+=int(frm>4)
  coverage['single_register_unaligned']+=int(move and (vd%group!=0 or src%group!=0))
  if kind=='read':
   value=old[src]&mask;result=value|(M64^mask);writes=True;coverage['f0_write']+=int(vd==0)
  elif kind=='write':
   if start<vl:
    regs[vd]=(old[vd]&~mask)|scalarBits;versions^=1<<vd
  else:
   for i in range(start,vl):
    if not vm and not old[0]>>i&1:continue
    insert=i==(0 if kind=='up' else vl-1);j=i-1 if kind=='up' else i+1
    value=scalarBits if insert else old[src+j*bits//128]>>(j*bits%128)&mask
    r=vd+i*bits//128;shift=i*bits%128;regs[r]=(regs[r]&~(mask<<shift))|(value<<shift)
    coverage['cross_register']+=int(not insert and j*bits//128!=i*bits//128)
   if start<vl:versions^=((1<<group)-1)<<vd
   coverage['alias_down']+=int(kind=='down' and vd==src);coverage['masked']+=int(not vm)
  coverage['boxed' if scalar>>32==0xffffffff else 'unboxed']+=int(kind!='read' and s==2)
  coverage['snan_bits']+=int((scalar&0x7fffffff)==0x7f800001);start=0
 cmd(inst(kind,vd,src,vm),scalar,result,writes,bad,record=dict(kind=kind,sew=bits,vtype=typ,vl=vl,vstart=initial,frm=frm) if record and not bad else None)
for r in range(32):ctx(r,True)
if fp:
 lines.append("command(32'h001091f3,21,0,0,0,0,0,1,0,0,64'h8000000000000000);");commands+=1
execute('read')
alltypes=[(s,m) for m in [0,1,2,3,5,6,7] for s in [2,3] if m<4 or s<=m-5]
for s,m in ([(2,0),(3,0),(2,3)] if a.compact else alltypes):
 config(s,m,128 if not a.compact else 3);seed()
 if fp:csr(2,7) # all transfers ignore frm, including reserved encodings
 for kind in ['read','write','up','down']:
  execute(kind,record=True);execute(kind,scalar=0x000000007f800001)
  execute(kind,vd=0 if kind=='read' else 8)
  csr(8,1);execute(kind,vm=1 if kind in ['read','write'] else 0)
  execute(kind,vd=16,src=16)
  if not a.compact:
   if kind in ['read','write']:execute(kind,vd=9,src=17)
   execute(kind,vm=0);csr(8,127);execute(kind)
 config(s,m,0)
 for kind in ['read','write','up','down']:execute(kind)
for s in [0,1]:
 config(s,0,0)
 for kind in ['read','write','up','down']:execute(kind)
config(2,0,3);seed()
for kind in ['read','write','up','down']:
 if fp:
  for delay in ([0,12] if a.compact else [0,1,3,8,12,20,32,60]):lines.append(f"cancel(32'h{inst(kind,8,16):x},{delay},0);");coverage['flush']+=1;state()
  lines.append(f"cancel(32'h{inst(kind,8,16):x},0,1);");coverage['flush']+=1;state()
 execute(kind)
lines+=['$display("PASS fp-transfers commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule']
label=a.top+('-compact' if a.compact else '-full')+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines));rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
else:
 source=ROOT/f'build/rtl/verification/assert/{a.top}_Verification_Assert.sv'
 if source.exists():
  f=OUT/(label+'-assert.sv');f.write_text(source.read_text().replace(a.top+'.','tb.dut.'));files.append(f);extra=['-s',a.top+'_Verification_Assert']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
observed={int(x.split()[1]):int(x.split()[2]) for x in run.stdout.splitlines() if x.startswith('PERF ')};assert len(observed)==len(performance)
for row in performance:row['cycles']=observed[row['id']]
result=dict(status='PASS',commands=commands,coverage=coverage,types=sorted(types),forms=sorted(forms),performance=performance,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS fp-transfers')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'tests/test_vector.py',ROOT/'src/main/scala/vpu/core/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
