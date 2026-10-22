#!/usr/bin/env python3
"""CPU-side protocol tests; synthetic CPU/VPU peers, no Valence execution."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/host-boundary';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
tb=r'''module tb;
reg clock=0,reset=1,io_headValid=0,io_olderMemoryDrained=0,io_olderFpDrained=0,io_stop=0;
reg [79:0] io_headToken=0;
reg io_offer_valid=0;wire io_offer_ready;
reg [31:0] io_offer_bits_instruction=0;reg [63:0] io_offer_bits_scalar=0,io_offer_bits_scalar2=0,io_offer_bits_avl=0;reg [79:0] io_offer_bits_token=0;
wire io_command_valid;reg io_command_ready=0;
wire [31:0] io_command_bits_instruction;wire [63:0] io_command_bits_scalar,io_command_bits_scalar2,io_command_bits_avl;wire [79:0] io_command_bits_token;
reg io_completion_valid=0;wire io_completion_ready;
reg [79:0] io_completion_bits_token=0;reg [31:0] io_completion_bits_instruction=0;
reg [63:0] io_completion_bits_scalar=0;reg io_completion_bits_writesScalar=0,io_completion_bits_illegal=0;
reg io_memoryStatus_valid=0,io_memoryStatus_bits_fault=0,io_memoryStatus_bits_interrupted=0;
reg [5:0] io_memoryStatus_bits_cause=0;reg [63:0] io_memoryStatus_bits_address=0;reg [7:0] io_memoryStatus_bits_element=0;
wire io_reply_valid;reg io_reply_ready=0;
wire [79:0] io_reply_bits_completion_token;wire [31:0] io_reply_bits_completion_instruction;
wire [63:0] io_reply_bits_completion_scalar;wire io_reply_bits_completion_writesScalar,io_reply_bits_completion_illegal;
wire io_reply_bits_memory,io_reply_bits_stopped,io_reply_bits_exception;wire [5:0] io_reply_bits_cause,io_reply_bits_rawMemoryCause;
wire [63:0] io_reply_bits_tval;wire [7:0] io_reply_bits_element;
wire io_vpuFlush,io_active,io_protocolError,io_canceled_valid;wire [79:0] io_canceled_bits;
VpuHostBoundary dut(.*);
integer cycles=0,replies=0,cancels=0,poisons=0,n,j,kind,raw,expectedCause;
reg mem,store,stopped,bad,fault;reg [31:0] inst;reg [79:0] token;reg [63:0] expectedTval;
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>10000)$fatal(1,"timeout");end endtask
task restart;begin
 reset=1;io_stop=0;io_offer_valid=0;io_completion_valid=0;io_memoryStatus_valid=0;io_reply_ready=0;io_command_ready=0;
 tick();tick();reset=0;#1;if(io_active || io_protocolError)$fatal(1,"reset");
end endtask
task launch(input [31:0] ins,input [79:0] tag);
begin
 io_offer_bits_instruction=ins;io_offer_bits_token=tag;io_offer_bits_scalar=64'hfedcba9876543210;
 io_offer_bits_scalar2=64'h123456789abcdef0;io_offer_bits_avl=64'h100000001;
 io_offer_valid=1;io_command_ready=0;io_headValid=0;io_olderMemoryDrained=0;io_olderFpDrained=0;
 #1;if(io_command_valid || io_offer_ready)$fatal(1,"not head");tick();
 io_headValid=1;io_headToken=tag^80'h80000000000000000000;
 #1;if(io_command_valid)$fatal(1,"truncated head identity");tick();
 io_headToken=tag;io_olderMemoryDrained=1;
 #1;if(io_command_valid)$fatal(1,"FP not drained");tick();
 io_olderFpDrained=1;io_olderMemoryDrained=0;
 #1;if(io_command_valid)$fatal(1,"memory not drained");tick();
 io_olderMemoryDrained=1;
 repeat(3)begin
  #1;if(!io_command_valid || io_offer_ready || io_command_bits_instruction!==ins || io_command_bits_token!==tag ||
   io_command_bits_scalar!==64'hfedcba9876543210 || io_command_bits_scalar2!==64'h123456789abcdef0 || io_command_bits_avl!==64'h100000001)$fatal(1,"offer stability");tick();
 end
 io_command_ready=1;#1;if(!io_offer_ready)$fatal(1,"not accepted");tick();io_offer_valid=0;
 if(!io_active)$fatal(1,"owner missing");
 io_headValid=0;io_headToken=~tag;
 #1;if(io_offer_ready)$fatal(1,"second owner");
end endtask
initial begin restart();
for(n=0;n<128;n=n+1)begin
 kind=n%4;mem=kind==1 || kind==2;store=kind==2;
 inst=kind==0?32'h02880457:kind==1?32'h00040407:kind==2?32'h02040427:32'hc20021f3;
 token=80'hf8aadeadbeef00000000+n;launch(inst,token);
 repeat(n%5)tick();
 if(!mem && n%8==0)begin
  io_stop=1;io_completion_valid=1;io_completion_bits_token=token;io_completion_bits_instruction=inst;
  io_memoryStatus_valid=0;io_reply_ready=1;
  #1;if(io_reply_valid || io_completion_ready || !io_vpuFlush || !io_canceled_valid || io_canceled_bits!==token)$fatal(1,"arithmetic cancel");
  tick();io_completion_valid=0;io_stop=0;io_reply_ready=0;
  #1;if(io_active || io_canceled_valid || io_protocolError)$fatal(1,"cancel owner");cancels=cancels+1;
 end else begin
  stopped=mem && n%3==0;bad=n%11==0;fault=mem && n%5==0;raw=((n/4)%2)==0?(store?6:4):(store?7:5);
  if(stopped)begin
   io_stop=1;
   repeat(4)begin #1;if(!io_active || !io_vpuFlush || io_canceled_valid || io_offer_ready)$fatal(1,"memory owner lost on stop");tick();end
   if(n%2)io_stop=0;
  end
  io_completion_valid=1;io_completion_bits_instruction=inst;io_completion_bits_token=token;
  io_completion_bits_scalar=64'h123456789abcdef0+n;io_completion_bits_writesScalar=1;io_completion_bits_illegal=bad;
  io_memoryStatus_valid=mem;io_memoryStatus_bits_fault=fault;io_memoryStatus_bits_interrupted=stopped;
  io_memoryStatus_bits_cause=raw;io_memoryStatus_bits_address=64'h8000000034567800+n;io_memoryStatus_bits_element=n;
  expectedCause=bad?2:!fault?0:raw==(store?6:4)?(store?6:4):(store?7:5);
  expectedTval=bad?{32'h0,inst}:fault?(64'h8000000034567800+n):0;
  repeat(5)begin
   #1;if(!io_reply_valid || io_completion_ready || io_protocolError || io_canceled_valid || !io_active ||
    io_reply_bits_completion_token!==token || io_reply_bits_completion_instruction!==inst || io_reply_bits_completion_scalar!==(64'h123456789abcdef0+n) ||
    io_reply_bits_completion_writesScalar!==( !(bad||fault||stopped)) || io_reply_bits_completion_illegal!==bad ||
    io_reply_bits_memory!==mem || io_reply_bits_stopped!==stopped || io_reply_bits_exception!==(bad||fault) ||
    io_reply_bits_cause!==expectedCause || io_reply_bits_tval!==expectedTval ||
    io_reply_bits_rawMemoryCause!==(mem?raw:0) || io_reply_bits_element!==(mem?n:0))$fatal(1,"reply n=%0d",n);
   tick();
  end
  io_reply_ready=1;#1;if(!io_completion_ready)$fatal(1,"retirement permission missing");
  tick();io_completion_valid=0;io_memoryStatus_valid=0;io_reply_ready=0;io_stop=0;
  #1;if(io_active || io_protocolError)$fatal(1,"retirement owner");replies=replies+1;
 end
end
// Exhaust all raw six-bit causes with held replies for both load/store owners.
for(j=0;j<2;j=j+1)for(raw=0;raw<64;raw=raw+1)begin
 store=j!=0;inst=store?32'h02808427:32'h0280f407;token=80'hc1000000000000000000+128*j+raw;launch(inst,token);
 io_completion_valid=1;io_completion_bits_token=token;io_completion_bits_instruction=inst;io_completion_bits_illegal=0;
 io_completion_bits_scalar=0;io_completion_bits_writesScalar=1;io_memoryStatus_valid=1;
 io_memoryStatus_bits_fault=1;io_memoryStatus_bits_interrupted=0;io_memoryStatus_bits_cause=raw;
 io_memoryStatus_bits_address=64'h80000001+raw;io_memoryStatus_bits_element=raw;
 expectedCause=store?(raw==6?6:7):(raw==4?4:5);
 repeat(3)begin
  #1;if(!io_reply_valid || io_reply_bits_cause!==expectedCause || io_reply_bits_rawMemoryCause!==raw ||
   io_reply_bits_tval!==(64'h80000001+raw) || !io_reply_bits_exception || io_reply_bits_completion_writesScalar ||
   io_reply_bits_completion_token!==token || io_completion_ready)$fatal(1,"raw fault map %0d/%0d",j,raw);tick();
 end
 io_reply_ready=1;tick();io_reply_ready=0;io_completion_valid=0;io_memoryStatus_valid=0;replies=replies+1;
 #1;if(io_active || io_protocolError)$fatal(1,"raw fault owner");
end
// High bits, wrong instruction and missing/extra memory metadata fail closed.
for(j=0;j<5;j=j+1)begin
 restart();inst=j==3?32'h00040407:32'h02880457;token=80'hb0000000000000000042;launch(inst,token);
 io_completion_valid=1;io_completion_bits_token=token;io_completion_bits_instruction=inst;
 io_completion_bits_illegal=0;io_memoryStatus_valid=0;io_reply_ready=1;
 if(j==0)io_completion_bits_token=token^80'h80000000000000000000;
 if(j==1)io_completion_bits_instruction=inst^32'h80000000;
 if(j==2)io_memoryStatus_valid=1;
 if(j==4)begin io_completion_valid=0;io_memoryStatus_valid=1;end
 #1;if(!io_protocolError || io_reply_valid || io_completion_ready)$fatal(1,"bad completion consumed");tick();
 io_completion_valid=0;io_memoryStatus_valid=0;
 #1;if(!io_protocolError || io_offer_ready)$fatal(1,"poison not sticky");poisons=poisons+1;
end
restart();io_completion_valid=1;io_completion_bits_token=0;io_reply_ready=1;
#1;if(!io_protocolError || io_completion_ready || io_reply_valid)$fatal(1,"stray completion");tick();poisons=poisons+1;
restart();if(replies!=240 || cancels!=16 || poisons!=6)$fatal(1,"coverage");
$display("PASS host-boundary replies=%0d cancels=%0d poisons=%0d cycles=%0d",replies,cancels,poisons,cycles);$finish;end endmodule
'''
label='mapped' if args.mapped else 'rtl';path=OUT/'tb.sv';path.write_text(tb)
rtl=ROOT/('build/synth/VpuHostBoundary/mapped.v' if args.mapped else 'build/rtl/VpuHostBoundary.sv')
files=[path,rtl];extra=[]
if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'tests/fp_mapped_global.sv'];extra=['-s','glbl']
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',*extra,'-o',str(OUT/label),*map(str,files)],check=True,stdout=log,stderr=log)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
d=dict(status='PASS',scope='SYNTHETIC_PEERS_NO_ACTUAL_CPU_INTEGRATION',mapped=args.mapped,raw_cause_combinations=128,summary=next(x for x in run.stdout.splitlines() if x.startswith('PASS host-boundary')),
 sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,path,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/interface/VpuHostBoundary.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
