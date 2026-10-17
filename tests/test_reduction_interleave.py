#!/usr/bin/env python3
"""Live command sequence alternating compress, gather, slides, reductions, ALU, MUL and FP."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/reduction-interleave';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;').replace('input [4:0] expectedVl','input [7:0] expectedVl')
h=h.replace('reg [31:0] saved;','reg [31:0] saved,originalVersions;reg [6:0] originalStart;').replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;','originalVersions=io_versions;originalStart=io_vstart;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;',1)
guard='if(io_versions!==originalVersions || io_vstart!==originalStart)$fatal(1,"interleave premature publication");'
h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();'+guard+'end',1).replace('repeat(stall) begin','repeat(stall) begin\n'+guard+'\nif(io_completion_bits_scalar!==result || io_completion_bits_illegal!==illegal || io_completion_bits_writesScalar!==wr)$fatal(1,"interleave unstable reply");',1)
lines=[h];regs=[0]*32;versions=0;count=vector_count=start=0;flags=rounding=vxsat=vxrm=0
def ctx(r,write=False):
 for chunk in range(2):
  x=(regs[r]>>(64*chunk))&((1<<64)-1)
  lines.append(f"ctx({2*r+chunk},1'b{int(write)},64'h{x:x},64'h{x:x});")
def setwords(r,words):regs[r]=sum(x<<(32*i) for i,x in enumerate(words));ctx(r,True)
def command(inst,result=0,writes=0,scalar=0):
 global count,vector_count
 lines.append(f"command(32'h{inst:x},64'h{scalar:x},0,4,80'h{0xcccc0000000000000000+count:x},0,64'h{result:x},1'b{writes},3,8'd4,64'h10);")
 lines.append(f"if(io_versions!==32'h{versions:x} || io_vstart!==7'd{start} || io_fflags!==5'd{flags} || io_frm!==3'd{rounding} || io_vxsat!==1'd{vxsat} || io_vxrm!==2'd{vxrm})$fatal(1,\"interleave state\");")
 count+=1
 vector_count+=int(inst&127==0x57 and (inst>>12&7)!=7)
def execute(code,form,vd,source,seed,words,scalar=0):
 global versions
 regs[vd]=sum(x<<(32*i) for i,x in enumerate(words));versions^=1<<vd
 command((code<<26)|(1<<25)|(source<<20)|(seed<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar);ctx(vd)
for r in range(32):ctx(r,True)
command(0x0100f1d7,result=4,writes=1)
flags=21;command((1<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=flags)
rounding=3;command((2<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=rounding)
vxsat=1;command((9<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=vxsat)
vxrm=2;command((10<<20)|(1<<15)|(1<<12)|(3<<7)|0x73,writes=1,scalar=vxrm)
setwords(8,[1,2,3,4]);setwords(16,[10,0,0,0])
execute(0,2,24,8,16,[20,0,0,0])
execute(0,0,8,8,16,[11,2,3,4])
execute(6,2,31,8,16,[11,0,0,0])
execute(0x25,2,24,8,16,[110,0,0,0])
execute(3,2,24,24,31,[101,0,0,0])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
# Slide on FP bit patterns, then return to FP arithmetic: the slide mode,
# private VLMAX scratch and source offset must not leak into old operations.
execute(0x0e,3,24,8,1,[101,0x3f800000,0x3f800000,0x3f800000])
execute(0x0f,3,24,24,1,[0x3f800000,0x3f800000,0x3f800000,0])
execute(0,1,24,8,16,[0x40400000]*4)
execute(0x0f,6,24,24,5,[0x40400000,0x40400000,0x40400000,0x40000000],scalar=0x40000000)
execute(0,1,24,24,16,[0x40a00000,0x40a00000,0x40a00000,0x40800000])
execute(3,2,24,24,31,[0x0020000b,0x40a00000,0x40a00000,0x40800000])
execute(0x0e,6,8,24,5,[7,0x0020000b,0x40a00000,0x40a00000],scalar=7)
execute(0,0,8,8,16,[0x40000007,0x4020000b,0x80a00000,0x80a00000])
# Indexed and splat gathers return to both integer and FP paths.
setwords(16,[3,2,1,0])
execute(0x0c,0,24,8,16,[0x80a00000,0x80a00000,0x4020000b,0x40000007])
execute(0x0c,4,8,24,5,[0x4020000b]*4,scalar=2)
execute(0,0,8,8,16,[0x4020000e,0x4020000d,0x4020000c,0x4020000b])
execute(0x0c,3,24,8,31,[0,0,0,0])
regs[16]=0x0002000000010003;ctx(16,True)
execute(0x0e,0,24,8,16,[0x4020000b,0x4020000d,0x4020000e,0x4020000c])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(0,1,24,8,16,[0x40400000]*4)
# Explicit mask must not overwrite the implicit execution mask between modes.
regs[3]=0xa;ctx(3,True)
execute(0x17,2,24,8,3,[0x3f800000,0x3f800000,0x40400000,0x40400000])
execute(0,1,24,24,16,[0x40400000,0x40400000,0x40a00000,0x40a00000])
execute(0x14,2,8,3,16,[0,0,1,1])
execute(0x17,2,24,8,3,[0,1,0x40a00000,0x40a00000])
execute(0x0c,3,8,24,0,[0,0,0,0])
# FP feedback reduction shares seed/candidate RAM with integer modes.
setwords(8,[0x3f800000,0x40000000,0x40400000,0x40800000])
setwords(16,[0x3f000000]*4)
execute(3,1,24,8,16,[0x41280000,1,0x40a00000,0x40a00000])
execute(1,1,24,8,16,[0x41280000,1,0x40a00000,0x40a00000])
execute(5,1,24,8,16,[0x3f000000,1,0x40a00000,0x40a00000])
execute(7,1,24,8,16,[0x40800000,1,0x40a00000,0x40a00000])
execute(0,1,8,8,16,[0x3fc00000,0x40200000,0x40600000,0x40900000])
execute(0x17,2,24,8,3,[0x40200000,0x40900000,0x40a00000,0x40a00000])
# Widen e32 sources into a full 64-bit seed/result; then return to same-width
# FP/INT operations to catch leaked arithmetic width or sign control.
setwords(8,[0xffffffff,2,0x80000000,0x7fffffff])
setwords(16,[0x10,0x12345678,0x55,0x66])
execute(0x30,0,24,8,16,[0x10,0x1234567a,0x40a00000,0x40a00000])
execute(0x31,0,24,8,16,[0x10,0x12345678,0x40a00000,0x40a00000])
execute(0,0,8,8,16,[0xf,0x1234567a,0x80000055,0x80000065])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(3,1,24,8,16,[0x40c00000,0x12345678,0x40a00000,0x40a00000])
execute(0,1,8,8,16,[0x40400000]*4)
# Mixed FP32 data / FP64 seed reuses the same RF and FP lane.
setwords(8,[0x3f800000,0x40000000,0x40400000,0x40800000])
setwords(31,[0,0x3fe00000,0,0])
execute(0x33,1,24,8,31,[0,0x40250000,0x40a00000,0x40a00000])
execute(0x31,1,8,8,31,[0,0x40250000,0x40400000,0x40800000])
setwords(8,[0x3f800000]*4)
execute(0,1,8,8,16,[0x40400000]*4)
execute(0x17,2,24,8,3,[0x40400000,0x40400000,0x40a00000,0x40a00000])
# Smaller packed sources must not use destination SEW for RAM offsets.
setwords(16,[0x7fff8000,0x0001ffff,0,0])
execute(0x12,2,8,16,6,[0x8000,0x7fff,0xffff,1])
execute(0x12,2,8,16,7,[0xffff8000,0x7fff,0xffffffff,1])
execute(0,0,24,8,8,[0xffff0000,0xfffe,0xfffffffe,2])
setwords(16,[0xff7f8001,0,0,0])
execute(0x12,2,8,16,4,[1,0x80,0x7f,0xff])
execute(0x12,2,8,16,5,[1,0xffffff80,0x7f,0xffffffff])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(0,1,24,8,16,[0x40400000]*4)
execute(0x17,2,24,8,3,[0x3f800000,0x3f800000,0x40400000,0x40400000])
# Narrow wide sources with a separate SEW-sized shift vector, then legally
# overlap the destination with the low source group. FP FMA shares funct6=2c.
setwords(16,[0x89abcdef,0x01234567,0x76543210,0xfedcba98])
setwords(17,[0,0x80000000,0xffffffff,0xffffffff])
setwords(24,[0,32,63,64])
execute(0x2c,0,8,16,24,[0x89abcdef,0xfedcba98,1,0xffffffff])
execute(0x2d,0,8,16,24,[0x89abcdef,0xfedcba98,0xffffffff,0xffffffff])
execute(0x2c,4,16,16,5,[0x01234567,0xfedcba98,0x80000000,0xffffffff],scalar=32)
setwords(16,[0x7fff8000,0x0001ffff,0,0])
execute(0x12,2,8,16,7,[0xffff8000,0x7fff,0xffffffff,1])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4);setwords(24,[0x3f800000]*4)
execute(0x2c,1,24,8,16,[0x40400000]*4)
execute(0x17,2,24,8,3,[0x3f800000,0x3f800000,0x40400000,0x40400000])
# Widened vector destinations occupy two registers; keep vtype e32/m1.
def widen(code,form,vd,src,other,values,scalar=0):
 global versions
 for j in range(2):regs[vd+j]=sum((values[2*j+k]&((1<<64)-1))<<(64*k) for k in range(2))
 versions^=3<<vd
 command((code<<26)|(1<<25)|(src<<20)|(other<<15)|(form<<12)|(vd<<7)|0x57,scalar=scalar)
 ctx(vd);ctx(vd+1)
setwords(8,[0xffffffff,2,0x80000000,0x7fffffff]);setwords(16,[1,0xffffffff,2,0x80000000])
widen(0x30,2,24,8,16,[0x100000000,0x100000001,0x80000002,0xffffffff])
widen(0x35,6,24,24,5,[0xffffffff,0x100000000,0x80000001,0xfffffffe],scalar=0xffffffffffffffff)
widen(0x37,2,24,24,16,[0xfffffffe,0x100000001,0x7fffffff,0x17ffffffe])
setwords(25,[0xffffffff,2,0x80000000,0x7fffffff])
widen(0x31,2,24,25,16,[0,1,-2147483646,-1]) # legal highest narrow-source overlap
execute(0,0,8,8,16,[0,1,0x80000002,0xffffffff])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(0,1,24,8,16,[0x40400000]*4)
# Full-width product, including signed(vs2)*unsigned(vs1), then mode changes.
setwords(8,[0xffffffff,2,0x80000000,0x7fffffff]);setwords(16,[1,0xffffffff,2,0x80000000])
aw=[0xffffffff,2,0x80000000,0x7fffffff];bw=[1,0xffffffff,2,0x80000000]
signed32=lambda x:x-(1<<32) if x>>31 else x
for code in [0x38,0x3a,0x3b]:
 left=[signed32(x) for x in aw] if code!=0x38 else aw
 right=[signed32(x) for x in bw] if code==0x3b else bw
 widen(code,2,24,8,16,[a*b for a,b in zip(left,right)])
 scalar=-1 if code==0x3b else 0xffffffff
 widen(code,6,24,8,5,[a*scalar for a in left],scalar=0xffffffffffffffff)
setwords(25,aw)
widen(0x3a,2,24,25,16,[-1,0x1fffffffe,-0x100000000,0x3fffffff80000000])
widen(0x30,2,24,8,16,[0x100000000,0x100000001,0x80000002,0xffffffff])
execute(0x2c,4,8,24,5,[0,1,0x80000002,0xffffffff],scalar=0)
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(0,1,24,8,16,[0x40400000]*4)
setwords(8,[1,2,3,4]);setwords(16,[5,6,7,8])
execute(0x25,2,24,8,16,[5,12,21,32])
# Integer destructive multiply-add shares the third RAM read with FP FMA.
# Exercise both overwrite forms and return immediately to FP and ordinary MUL.
setwords(8,[1,2,3,4]);setwords(16,[5,6,7,8]);setwords(24,[10,20,30,40])
execute(0x2d,2,24,8,16,[15,32,51,72])
execute(0x2f,6,24,8,5,[12,26,42,60],scalar=3)
execute(0x29,2,24,8,16,[61,158,297,484])
execute(0x2b,6,24,8,5,[(x-2*d)&0xffffffff for x,d in zip([1,2,3,4],[61,158,297,484])],scalar=2)
execute(0x2d,2,8,8,8,[2,6,12,20])
execute(0x25,2,24,8,16,[10,36,84,160])
# MAC and reductions share only scalar scratch: seed reload and product
# handoff must overwrite it at their own boundaries.
execute(0,2,24,8,16,[45,36,84,160])
execute(0x2d,2,24,8,16,[55,72,168,320])
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4);setwords(24,[0x3f800000]*4)
execute(0x2c,1,24,8,16,[0x40400000]*4)
execute(0,1,24,24,16,[0x40a00000]*4)
# Preserve the complete M35 sequence above, then cross the M36 whole-move
# fast path with the modes whose metadata and scalar scratch it bypasses.
assert vector_count==79
def whole(n,vd,src):
 global versions,start
 snapshot=tuple(regs);first=start*32
 for j in range(n):
  for bit in range(0,128,8):
   if 128*j+bit>=first:
    mask=255<<bit
    regs[vd+j]=(regs[vd+j]&~mask)|(snapshot[src+j]&mask)
 if first<n*128 and vd!=src:versions^=((1<<n)-1)<<vd
 start=0
 command((0x27<<26)|(1<<25)|(src<<20)|((n-1)<<15)|(3<<12)|(vd<<7)|0x57)
 for j in range(n):ctx(vd+j)
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4);setwords(24,[0x3f800000]*4)
execute(0x2c,1,24,8,16,[0x40400000]*4) # exact FP32 1*2+1 = 3
whole(1,20,24)
setwords(16,[10,0,0,0])
execute(0,2,28,20,16,[0x0100000a,0,0,0]) # modular integer sum of the four FP bit patterns
setwords(8,[0xffffffff,2,0x80000000,3]);setwords(16,[1,0xffffffff,2,0x80000000])
setwords(24,[1,0,2,0]);setwords(25,[3,0,4,0])
widen(0x3f,2,24,8,16,[0x100000000,0,0x100000003,0xfffffffe80000004])
execute(0,2,28,8,16,[0x80000005,0,0,0])
regs[3]=0xa;ctx(3,True)
execute(0x17,2,24,8,3,[2,3,0,0])
whole(2,20,24)
setwords(8,[0x3f800000]*4);setwords(16,[0x40000000]*4)
execute(0,1,24,8,16,[0x40400000]*4)
# A held whole move must leave both its destination versions and a nonzero
# vstart untouched. Assert flush and completion.ready together, then retry
# from the same element using an immutable source/destination byte oracle.
setwords(28,[0xdeadbeef,0x12345678,0x89abcdef,0xfedcba98]);setwords(29,[0x76543210,0x0badcafe,0x55555555,0xaaaaaaaa])
start=1;command(0x008091f3,writes=1,scalar=1)
cancel_inst=(0x27<<26)|(1<<25)|(20<<20)|(1<<15)|(3<<12)|(28<<7)|0x57
cancel_guard=f'if(io_versions!==32\'h{versions:x} || io_vstart!==1 || io_vl!==4 || io_vtype!==64\'h10 || io_fflags!==5\'d{flags} || io_frm!==3\'d{rounding} || io_vxsat!==1\'d{vxsat} || io_vxrm!==2\'d{vxrm})$fatal(1,"whole move cancelled state");'
lines.append(f'''io_command_bits_instruction=32'h{cancel_inst:x};io_command_bits_scalar=0;
io_command_bits_token=80'h36ccccbad;io_command_valid=1;
#1;if(!io_command_ready)$fatal(1,"whole cancel command unavailable");tick();io_command_valid=0;
while(!io_completion_valid)begin tick();{cancel_guard}end
repeat(5)begin
 {cancel_guard}
 if(!io_completion_valid || io_completion_bits_instruction!==32'h{cancel_inst:x} || io_completion_bits_token!==80'h36ccccbad || io_completion_bits_illegal || io_completion_bits_writesScalar || io_completion_bits_scalar!==0)$fatal(1,"whole cancel held reply");
 tick();
end
io_completion_ready=1;io_flush=1;
#1;if(io_completion_valid || io_command_ready)$fatal(1,"whole cancel flush handshake");
tick();io_flush=0;io_completion_ready=0;
repeat(12)begin tick();{cancel_guard}if(io_completion_valid)$fatal(1,"whole cancel stale reply");end
if(io_busy)$fatal(1,"whole cancel remains busy");''')
for r in range(32):ctx(r)
whole(2,28,20)
execute(0,0,24,28,28,[0xbd5b7dde,6,0,0]) # preserved prestart word is read by the next ALU operation
for r in range(32):ctx(r)
lines+=[f'$display("PASS reduction-interleave {vector_count} vector instructions, 1 held whole-move flush");$finish;end endmodule']
tb=OUT/'tb.sv';tb.write_text('\n'.join(lines));label='mapped' if args.mapped else 'rtl'
rtl=ROOT/('build/synth/RamVectorFp/mapped.v' if args.mapped else 'build/rtl/RamVectorFp.sv')
files=[tb,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-DTOP=RamVectorFp',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
result=dict(status='PASS',mapped=args.mapped,vector_instructions=vector_count,commands=count,held_whole_move_flushes=1,original_vector_instructions=79,sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/RamVector.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
