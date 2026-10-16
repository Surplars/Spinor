#!/usr/bin/env python3
"""Raw instruction encodings and register-state oracle independent of Chisel.

Tests own standalone prototype with Icarus; never builds or simulates Valence.
This is subset verification, not an ISA compliance suite.
"""
import argparse
import json
from pathlib import Path
import random
import subprocess
from test_lane import golden

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test'
BIN=ROOT/'tools/oss-cad-suite/bin'
MASK128=(1<<128)-1

HEADER=r'''
module tb;
reg clock=0, reset=1, io_flush=0;
reg io_command_valid=0,io_completion_ready=0,io_context_valid=0;
reg [31:0] io_command_bits_instruction=0;
reg [63:0] io_command_bits_scalar=0,io_command_bits_scalar2=0,io_command_bits_avl=0;
reg [79:0] io_command_bits_token=0;
reg [5:0] io_context_bits_address=0;
reg io_context_bits_write=0;
reg [63:0] io_context_bits_data=0;
wire io_command_ready,io_completion_valid,io_context_ready,io_contextResult_valid,io_busy;
wire [63:0] io_completion_bits_scalar,io_contextResult_bits,io_vtype;
wire [79:0] io_completion_bits_token;
wire io_completion_bits_writesScalar,io_completion_bits_illegal;
wire [31:0] io_completion_bits_instruction;
wire [4:0] io_vl;
`TOP dut(.*);
integer cycles=0,cmds=0,reads=0;
task tick;
begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>1000000)$fatal(1,"timeout");end
endtask
task ctx(input integer addr,input bit wr,input [63:0] data,input [63:0] expected);
begin
io_context_valid=1;io_context_bits_address=addr;io_context_bits_write=wr;io_context_bits_data=data;
#1;if(!io_context_ready)$fatal(1,"context unavailable");tick();io_context_valid=0;
if(!io_contextResult_valid)$fatal(1,"missing context result");
if(!wr && io_contextResult_bits !== expected)$fatal(1,"reg addr=%0d got=%h expected=%h",addr,io_contextResult_bits,expected);
if(!wr) reads=reads+1;tick();
end
endtask
task command(input [31:0] inst,input [63:0] scalar,input [63:0] scalar2,input [63:0] avl,
 input [79:0] token,input bit illegal,input [63:0] result,input bit wr,input integer stall,
 input [4:0] expectedVl,input [63:0] expectedVtype);
reg [31:0] saved;
begin
io_command_bits_instruction=inst;io_command_bits_scalar=scalar;io_command_bits_scalar2=scalar2;
io_command_bits_avl=avl;io_command_bits_token=token;io_command_valid=1;
#1;if(!io_command_ready)$fatal(1,"command unavailable");tick();io_command_valid=0;
while(!io_completion_valid) tick();
saved=io_completion_bits_instruction;
repeat(stall) begin
 if(io_completion_bits_token !== token || io_completion_bits_instruction !== saved || !io_completion_valid)
   $fatal(1,"unstable completion");tick();
end
if(io_completion_bits_illegal !== illegal || io_completion_bits_token !== token ||
 io_completion_bits_scalar !== result || io_completion_bits_writesScalar !== wr ||
 io_completion_bits_instruction !== inst)
 $fatal(1,"bad completion inst=%h illegal=%b/%b result=%h/%h",inst,io_completion_bits_illegal,illegal,io_completion_bits_scalar,result);
io_completion_ready=1;tick();io_completion_ready=0;
if(io_vl !== expectedVl || io_vtype !== expectedVtype)$fatal(1,"bad configuration");
cmds=cmds+1;
end
endtask
task cancel(input [31:0] inst,input integer delayCycles,input bit atCompletion);
begin
io_command_bits_instruction=inst;io_command_bits_scalar=64'h123;io_command_bits_token=64'hbad;
io_command_valid=1;#1;if(!io_command_ready)$fatal(1,"cancel start blocked");tick();io_command_valid=0;
if(atCompletion) begin while(!io_completion_valid) tick();end
else repeat(delayCycles) tick();
io_flush=1;#1;if(io_completion_valid || io_command_ready)$fatal(1,"flush handshake");tick();io_flush=0;
repeat(12)begin tick();if(io_completion_valid)$fatal(1,"stale completion after flush");end
if(io_busy)$fatal(1,"busy after cancellation");
end
endtask
initial begin
tick();tick();reset=0;tick();
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mapped',action='store_true',help='also exercise mapped LUTRAM netlist with Yosys cell models')
    parser.add_argument('--mapped-only',action='store_true',help='exercise only the mapped model; preserve preceding RTL results')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    rng=random.Random(0xabc1502)
    regs=[rng.getrandbits(128) for _ in range(32)]
    lines=[HEADER]
    def ctx(r,value=None):
        for c in range(2):
            x=((regs[r] if value is None else value)>>(64*c))&((1<<64)-1)
            lines.append(f"ctx({2*r+c},1'b{int(value is not None)},64'h{x:x},64'h{x:x});")
    for r in range(32): ctx(r,regs[r])
    vl=0;vtype=1<<63;sew=0;case=0
    def cmd(inst,scalar=0,scalar2=0,avl=0,illegal=False,result=0,writes=False):
        nonlocal case
        lines.append(f"command(32'h{inst:08x},64'h{scalar:x},64'h{scalar2:x},64'h{avl:x},"
                     f"80'h{((0xabc1<<64)|case):x},1'b{int(illegal)},64'h{result:x},1'b{int(writes)},{rng.randrange(8)},"
                     f"5'd{vl},64'h{vtype:x});")
        case+=1
    # Before vset, arithmetic is illegal and cannot change a destination.
    cmd(0x57|(1<<25)|(1<<7),illegal=True);ctx(1)
    defs=[(0x00,0,True),(0x02,1,False),(0x09,2,True),(0x0a,3,True),(0x0b,4,True),
          (0x25,5,True),(0x28,6,True),(0x29,7,True),(0x05,8,False),(0x04,9,False),
          (0x07,10,False),(0x06,11,False),(0x18,12,True),(0x19,13,True),
          (0x1b,14,False),(0x1a,15,False),(0x1d,16,True),(0x1c,17,True),
          (0x17,18,True),(0x17,19,True)]
    for sew in range(4):
      for iteration in range(100):
        w=8<<sew;maxvl=128//w
        if iteration%10==0:
            vl=rng.randrange(maxvl+1)
            vtype=(sew<<3)|(rng.randrange(4)<<6)
            kind=(iteration//10)%3
            if kind==0: inst=(vtype<<20)|(1<<15)|(7<<12)|(3<<7)|0x57;avl=vl;scalar2=0
            elif kind==1: inst=(3<<30)|(vtype<<20)|(vl<<15)|(7<<12)|(3<<7)|0x57;avl=0;scalar2=0
            else: inst=(0x40<<25)|(2<<20)|(1<<15)|(7<<12)|(3<<7)|0x57;avl=vl;scalar2=vtype
            cmd(inst,scalar2=scalar2,avl=avl,result=vl,writes=True)
        f6,op,immok=defs[iteration%len(defs)]
        form=rng.choice([0,4,3] if immok else [0,4])
        vm=1 if op==18 else 0 if op==19 else rng.randrange(2)
        vd=rng.randrange(32)
        if not vm and op<12 and vd==0:vd=1
        if op==19 and vd==0:vd=1
        vs2=0 if op==18 else rng.randrange(32)
        vs1=rng.randrange(32)
        scalar=rng.getrandbits(64)
        inst=(f6<<26)|(vm<<25)|(vs2<<20)|(vs1<<15)|(form<<12)|(vd<<7)|0x57
        a=regs[vs2];b=regs[vs1];mask=regs[0];dest=regs[vd]
        for e in range(vl):
            select=(mask>>e)&1
            if not vm and not select and op!=19:continue
            av=(a>>(e*w))&((1<<w)-1)
            if form==0:bv=b>>(e*w)
            elif form==4:bv=scalar
            elif op in [5,6,7]:bv=vs1
            else:bv=vs1 if vs1<16 else vs1-32
            res=golden(av,bv,sew,op,select)
            if 12<=op<=17:
                dest=(dest&~(1<<e))|((res&1)<<e)
            else:dest=(dest&~(((1<<w)-1)<<(e*w)))|(res<<(e*w))
        regs[vd]=dest&MASK128
        cmd(inst,scalar=scalar)
        ctx(vd)
        if iteration%19==0:
            # Reserved integer form and unsupported operation both trap.
            cmd((inst&~(7<<12))|(2<<12),illegal=True);ctx(vd)
      # Flush at distinct pipeline stages and with stalled completion.
      vl=maxvl;vtype=sew<<3
      cmd((vtype<<20)|(7<<12)|(3<<7)|0x57,avl=vl,result=vl,writes=True)
      inst=(1<<25)|(2<<20)|(3<<15)|(1<<7)|0x57
      for delay in [0,2,5,10]:
        lines.append(f"cancel(32'h{inst:x},{delay},1'b0);");ctx(1)
      lines.append(f"cancel(32'h{inst:x},0,1'b1);");ctx(1)
    # Unsupported LMUL sets vill/vl=0; following arithmetic must trap.
    vl=0;vtype=1<<63
    cmd((1<<20)|(7<<12)|(3<<7)|0x57,avl=4,result=0,writes=True)
    cmd((1<<25)|(1<<7)|0x57,illegal=True);ctx(1)
    # Flush a pending configuration completion: old vtype/vl must survive.
    lines.append("cancel(32'h000071d7,0,1'b1);")
    lines.append(f"if(io_vl !== 0 || io_vtype !== 64'h{vtype:x}) $fatal(1,\"config flush changed state\");")
    for r in range(32):ctx(r)
    lines.append('$display("PASS commands=%0d reads=%0d cycles=%0d",cmds,reads,cycles);$finish;end endmodule\n')
    tb=OUT/'vector_tb.sv';tb.write_text('\n'.join(lines))
    results=json.loads((OUT/'vector-results.json').read_text()) if args.mapped_only else {}
    for top in ([] if args.mapped_only else ['VectorPrototypeBaseline','VectorPrototype','VectorPrototype16','VectorPrototypeFlops']):
        exe=OUT/top
        with (OUT/f'{top}.compile.log').open('w') as log:
            subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}','-o',str(exe),
                            str(tb),str(ROOT/f'build/rtl/{top}.sv')],stdout=log,stderr=log,check=True)
        run=subprocess.run([str(BIN/'vvp'),str(exe)],cwd=ROOT,capture_output=True,text=True)
        (OUT/f'{top}.log').write_text(run.stdout+run.stderr)
        if run.returncode:raise RuntimeError(run.stdout+run.stderr)
        results[top]=run.stdout.strip()
    if args.mapped or args.mapped_only:
        top='VectorPrototype'
        exe=OUT/'VectorPrototype-mapped'
        with (OUT/'VectorPrototype-mapped.compile.log').open('w') as log:
            subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}','-o',str(exe),
                            str(tb),str(ROOT/f'build/synth/{top}/mapped.v'),
                            str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')],
                           stdout=log,stderr=log,check=True)
        run=subprocess.run([str(BIN/'vvp'),str(exe)],cwd=ROOT,capture_output=True,text=True)
        (OUT/'VectorPrototype-mapped.log').write_text(run.stdout+run.stderr)
        if run.returncode:raise RuntimeError(run.stdout+run.stderr)
        results['VectorPrototype-mapped']=run.stdout.strip()
    (OUT/'vector-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
