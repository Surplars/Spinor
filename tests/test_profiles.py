#!/usr/bin/env python3
"""Production-preset public top: integer/FP, context, memory TL and monitor MMIO."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/profiles';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--top',choices=['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'],required=True);p.add_argument('--mapped',action='store_true');a=p.parse_args()
manifest=ROOT/f'build/rtl/{a.top}.json';cfg=json.loads(manifest.read_text());fp=cfg['fp32_fp64'];assert cfg['has_fp_csr_ports']==fp
h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;'+('wire [2:0] io_frm;wire [4:0] io_fflags;' if fp else '')).replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('io_','io_core_')
def bus(prefix,master):
 text=''
 fieldsA={'opcode':3,'param':3,'size':3,'source':4,'address':64,'mask':8,'data':64,'corrupt':1};fieldsD={'opcode':3,'param':3,'size':3,'source':4,'sink':1,'denied':1,'data':64,'corrupt':1}
 for channel,fields,output in [('a',fieldsA,master),('d',fieldsD,not master)]:
  for key,n in {'valid':1,'ready':1,**{'bits_'+k:v for k,v in fields.items()}}.items():
   out=output if key!='ready' else not output;size='' if n==1 else f'[{n-1}:0] ';text+=f'{"wire" if out else "reg"} {size}{prefix}_{channel}_{key}'+(';' if out else '=0;')+'\n'
 return text
extra=bus('io_tl',True)+bus('io_monitor',False)+'''wire io_memoryStatus_valid,io_memoryStatus_bits_fault,io_memoryStatus_bits_interrupted;
wire [5:0] io_memoryStatus_bits_cause;wire [63:0] io_memoryStatus_bits_address;wire [7:0] io_memoryStatus_bits_element;
reg [63:0] memword=64'h1234567887654321;integer transfers=0,byteIndex;
always @(posedge clock)begin
 if(reset)io_tl_d_valid<=0;
 else begin
  if(io_tl_d_valid && io_tl_d_ready)io_tl_d_valid<=0;
  if(io_tl_a_valid && io_tl_a_ready)begin
   if(io_tl_d_valid)$fatal(1,"multiple TL requests");
   if(io_tl_a_bits_address[63:3]!==61'h10000000 && io_tl_a_bits_address[63:3]!==61'h11ffffff)$fatal(1,"memory address");
   transfers<=transfers+1;io_tl_d_valid<=1;io_tl_d_bits_opcode<=io_tl_a_bits_opcode==4?1:0;
   io_tl_d_bits_size<=io_tl_a_bits_size;io_tl_d_bits_source<=io_tl_a_bits_source;io_tl_d_bits_data<=memword;
   if(io_tl_a_bits_opcode!=4)begin
    if(io_tl_a_bits_mask!==((io_tl_a_bits_size==3?8'hff:io_tl_a_bits_size==2?8'h0f:io_tl_a_bits_size==1?8'h03:8'h01)<<io_tl_a_bits_address[2:0]))$fatal(1,"store mask");
    for(byteIndex=0;byteIndex<8;byteIndex=byteIndex+1)if(io_tl_a_bits_mask[byteIndex])memword[8*byteIndex+:8]<=io_tl_a_bits_data[8*byteIndex+:8];
   end
  end
 end
end
task mon(input [63:0] addr,input [63:0] value);begin
 io_monitor_a_valid=1;io_monitor_a_bits_opcode=4;io_monitor_a_bits_size=3;io_monitor_a_bits_address=addr;io_monitor_a_bits_mask=255;
 #1;while(!io_monitor_a_ready)tick();tick();io_monitor_a_valid=0;
 while(!io_monitor_d_valid)tick();
 repeat(3)begin if(!io_monitor_d_valid || io_monitor_d_bits_denied || io_monitor_d_bits_data!==value)$fatal(1,"monitor addr=%h data=%h expected=%h",addr,io_monitor_d_bits_data,value);tick();end
 io_monitor_d_ready=1;tick();io_monitor_d_ready=0;
end endtask
'''
h=h.replace('`TOP dut(.*);',extra+'`TOP dut(.*);')
body=[h,'io_tl_a_ready=1;']
count=0
def command(inst,scalar=0,scalar2=0,avl=0,result=0,writes=0,bad=0,vl=4,typ=16):
 global count
 body.append(f"command(32'h{inst:x},64'h{scalar:x},64'h{scalar2:x},{avl},80'h{0x390000+count:x},{bad},64'h{result:x},{writes},3,{vl},64'h{typ:x});");count+=1
def ctx(addr,value,write=False):body.append(f"ctx({addr},{int(write)},64'h{value:x},64'h{value:x});")
for addr in range(64):ctx(addr,0,True)
body += [f"mon(16,64'h5001);mon(24,64'h{cfg['monitor_caps'][2:]});mon(32,64'h1002000400080);mon(40,64'h800000200);"]
command(0x0100f1d7,avl=4,result=4,writes=1)
ctx(16,0x0000000200000001,True);ctx(17,0x0000000400000003,True);ctx(32,0x0000000600000005,True);ctx(33,0x0000000800000007,True)
command(0x02880c57);ctx(48,0x0000000800000006);ctx(49,0x0000000c0000000a)
command(0x96882c57);ctx(48,0x0000000c00000005);ctx(49,0x0000002000000015)
# FP f0 return must be marked as a real scalar destination; integer variants reject it.
command(0x43801057,result=0xffffffff00000005 if fp else 0,writes=int(fp),bad=int(not fp))
command(0x4200dc57,scalar=0xffffffff7f800001,bad=int(not fp));ctx(48,0x0000000c7f800001 if fp else 0x0000000c00000005)
# Iterate integer unit after the optional FP path; held reply and cancellation.
body.append("cancel(32'h02880c57,12,0);")
ctx(48,0x0000000c7f800001 if fp else 0x0000000c00000005)
command(0x001021f3,result=0,writes=int(fp),bad=int(not fp))
# Reconfigure e64 VL1 and load/store the real physical memory path.
command(0x0180f1d7,avl=1,result=1,writes=1,vl=1,typ=24)
command(0x02007407,scalar=0x80000000,vl=1,typ=24);ctx(16,0x1234567887654321)
ctx(16,0xfedcba9876543210,True);command(0x02007427,scalar=0x80000000,vl=1,typ=24)
body.append("if(memword!==64'hfedcba9876543210 || transfers!=2)$fatal(1,\"store/transfer count\");")
# Outside the configured physical window faults without emitting a bus request.
command(0x02007407,scalar=0x90000000,vl=1,typ=24)
body.append('if(transfers!=2 || io_core_vstart!=0)$fatal(1,"region check");')
# Real zero-stride transfers in all four production presets (including no FP).
command(0x0180f1d7,avl=2,result=2,writes=1,vl=2,typ=24)
command(0x0a00f407,scalar=0x80000000,scalar2=0xdeadbeef,vl=2,typ=24)
ctx(16,0xfedcba9876543210);ctx(17,0xfedcba9876543210)
command(0x0a20f427,scalar=0x80000000,scalar2=0,vl=2,typ=24)
body.append('if(transfers!=6 || memword!==64\'hfedcba9876543210)$fatal(1,"zero stride transfer count");')
# M44: indexed gather/scatter in FP and integer-only presets.
command(0x0100f1d7,avl=4,result=4,writes=1)
ctx(48,0,True);ctx(49,0,True)
command(0x0780d407,scalar=0x80000000)
ctx(16,0x7654321076543210);ctx(17,0x7654321076543210)
command(0x0f80d427,scalar=0x80000000)
body.append('if(transfers!=14 || memword!==64\'hfedcba9876543210)$fatal(1,"indexed preset transfers");')
# M45: whole transfers ignore vill/VL; mask vstart counts bytes.
command(0x0200f1d7,avl=0,result=0,writes=1,vl=0,typ=1<<63)
command(0x00809073,scalar=1,result=0,writes=0,vl=0,typ=1<<63)
command(0x0280f407,scalar=0x7ffffff8,vl=0,typ=1<<63)
ctx(17,0xfedcba9876543210)
command(0x00809073,scalar=15,result=0,writes=0,vl=0,typ=1<<63)
command(0x02808427,scalar=0x7ffffff1,vl=0,typ=1<<63)
command(0x02b08007,scalar=0x80000000,bad=1,vl=0,typ=1<<63)
command(0x0030f1d7,avl=9,result=9,writes=1,vl=9,typ=3)
ctx(0,0xaaaabbbbccccdddd,True)
command(0x00809073,scalar=1,result=0,writes=0,vl=9,typ=3)
command(0x02b08007,scalar=0x7fffffff,vl=9,typ=3)
ctx(0,0xaaaabbbbccccfedd)
command(0x00809073,scalar=1,result=0,writes=0,vl=9,typ=3)
command(0x02b08027,scalar=0x7fffffff,vl=9,typ=3)
body.append('if(transfers!=18 || memword!==64\'hfedcba98765432fe)$fatal(1,"context preset transfers");')
# M46: deinterleave a two-field structure and pack it back through real TL.
command(0x0100f1d7,avl=1,result=1,writes=1,vl=1,typ=16)
ctx(16,0,True);ctx(18,0,True)
command(0x2200e407,scalar=0x80000000,vl=1,typ=16)
ctx(16,0x765432fe);ctx(18,0xfedcba98)
command(0x2200e427,scalar=0x80000000,vl=1,typ=16)
body.append('if(transfers!=22 || memword!==64\'hfedcba98765432fe)$fatal(1,"segment preset transfers");')
# M47: zero-stride x0 / register-zero repeats every segment; indexed forms reuse two offsets.
command(0x0100f1d7,avl=2,result=2,writes=1,vl=2,typ=16)
command(0x2a00e407,scalar=0x80000000,scalar2=0xdeadbeef,vl=2,typ=16)
ctx(16,0x765432fe765432fe);ctx(18,0xfedcba98fedcba98)
command(0x2a20e427,scalar=0x80000000,scalar2=0,vl=2,typ=16)
ctx(48,0,True)
command(0x2f80e407,scalar=0x80000000,vl=2,typ=16)
ctx(16,0x765432fe765432fe);ctx(18,0xfedcba98fedcba98)
command(0x2780e427,scalar=0x80000000,vl=2,typ=16)
command(0x2e90e407,scalar=0x80000000,bad=1,vl=2,typ=16)
body.append('if(transfers!=38 || memword!==64\'hfedcba98765432fe)$fatal(1,"addressed segment preset transfers");')
# M48: real architectural VL trim, CSR read, and a two-field load at the RAM edge.
command(0x0180f1d7,avl=2,result=2,writes=1,vl=2,typ=24)
ctx(16,0xaaaabbbbccccdddd,True);ctx(17,0xeeeeffff12345678,True)
command(0x0300f407,scalar=0x8ffffff8,vl=1,typ=24)
ctx(16,0xfedcba98765432fe);ctx(17,0xeeeeffff12345678)
command(0xc20021f3,result=1,writes=1,vl=1,typ=24)
command(0x0100f1d7,avl=2,result=2,writes=1,vl=2,typ=16)
ctx(16,0xaabbccdd00000000,True);ctx(18,0x1122334400000000,True)
command(0x2300e407,scalar=0x8ffffff8,vl=1,typ=16)
ctx(16,0xaabbccdd765432fe);ctx(18,0x11223344fedcba98)
body.append('if(transfers!=41)$fatal(1,"FOF preset transfers");')
body.append(f'$display("PASS profile {a.top} commands=%0d cycles=%0d",cmds,cycles);$finish;end endmodule')
label=a.top+('-mapped' if a.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(body));rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl];extra=[]
if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*extra,'-o',str(OUT/label),*map(str,files)],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
result=dict(status='PASS',config=cfg,commands=count,scope='DIRECTED_PUBLIC_INTEGRATION_NOT_FULL_ISA_MATRIX',summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS profile')),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,manifest,Path(__file__).resolve(),ROOT/'tests/test_vector.py']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
