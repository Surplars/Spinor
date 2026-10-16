#!/usr/bin/env python3
"""Reuse the established memory oracle with concurrent monitor MMIO traffic."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spinor='--spinor' in sys.argv
if spinor:sys.argv.remove('--spinor')
sys.path.insert(0,str(ROOT/'tests'))
pins=r'''
reg monPolling=1,monValid=0;reg [63:0] monAddr=0,monData=0;reg [2:0] monOp=4;
wire io_monitor_a_valid=monPolling || monValid;wire io_monitor_a_ready;
wire [2:0] io_monitor_a_bits_opcode=monPolling?4:monOp;
wire [2:0] io_monitor_a_bits_param=0,io_monitor_a_bits_size=3;
wire [3:0] io_monitor_a_bits_source=0;
wire [63:0] io_monitor_a_bits_address=monPolling?0:monAddr,io_monitor_a_bits_data=monData;
wire [7:0] io_monitor_a_bits_mask=255;wire io_monitor_a_bits_corrupt=0;
wire io_monitor_d_valid;wire io_monitor_d_ready=!monPolling || cycles%5!=0;
wire [2:0] io_monitor_d_bits_opcode,io_monitor_d_bits_param,io_monitor_d_bits_size;
wire [3:0] io_monitor_d_bits_source;wire io_monitor_d_bits_sink,io_monitor_d_bits_denied,io_monitor_d_bits_corrupt;
wire [63:0] io_monitor_d_bits_data;
reg refOwned=0,refMemory=0;reg [31:0] refCount[0:12],expectedSnap[0:12];integer mi,monitorReads=0;
wire refAccept=io_core_command_valid && io_core_command_ready;
wire refComplete=io_core_completion_valid && io_core_completion_ready;
wire refCancel=refOwned && !refMemory && io_core_flush;
wire refMemoryDone=refComplete && io_memoryStatus_valid;
wire [12:0] refEvents={io_core_completion_valid && !io_core_completion_ready,
 io_core_command_valid && !io_core_command_ready,io_tl_d_valid && io_tl_d_ready,
 io_tl_a_valid && io_tl_a_ready,refMemoryDone && io_memoryStatus_bits_interrupted,
 refMemoryDone && io_memoryStatus_bits_fault,refComplete && io_core_completion_bits_illegal,
 refCancel,refComplete,refAccept,refOwned && refMemory,io_core_busy,1'b1};
always @(posedge clock)begin
 if(reset)begin for(mi=0;mi<13;mi=mi+1)refCount[mi]<=0;refOwned<=0;refMemory<=0;end
 else begin
  for(mi=0;mi<13;mi=mi+1)if(refEvents[mi])refCount[mi]<=refCount[mi]+1;
  if(refComplete || refCancel)begin refOwned<=0;refMemory<=0;end
  if(refAccept)begin refOwned<=1;refMemory<=io_core_command_bits_instruction[6:0]==7'h07 || io_core_command_bits_instruction[6:0]==7'h27;end
  if(monPolling && io_monitor_d_valid && io_monitor_d_ready)begin
   if(io_monitor_d_bits_denied || io_monitor_d_bits_corrupt || io_monitor_d_bits_data!==64'h4c495348)$fatal(1,"concurrent monitor read");
   monitorReads=monitorReads+1;
  end
 end
end
task monAccess(input [63:0] addr,input [2:0] op,input [63:0] data,input [63:0] expected);
begin
 monAddr=addr;monOp=op;monData=data;monValid=1;#1;
 while(!io_monitor_a_ready)tick();tick();monValid=0;
 while(!io_monitor_d_valid)tick();
 if(io_monitor_d_bits_denied || io_monitor_d_bits_corrupt || io_monitor_d_bits_data !== expected)$fatal(1,"integrated monitor snapshot addr=%h got=%h expected=%h",addr,io_monitor_d_bits_data,expected);
 tick();
end endtask
'''
end=r'''
// Execute a real integer reduction through the public SoC command port.
command(32'h0100f1d7,0,0,4,80'he80001,0,4,1,3,8'd4,64'h10);
ctx(16,1,64'h0000000200000001,0);ctx(17,1,64'h0000000400000003,0);
ctx(32,1,64'h000000000000000a,0);ctx(33,1,0,0);
ctx(48,1,64'h12345678deadbeef,0);ctx(49,1,64'hfedcba9876543210,0);
command(32'h02882c57,0,0,0,80'he80002,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h1234567800000014);ctx(49,0,0,64'hfedcba9876543210);
cancel(32'h02880457,20,1'b0);
ctx(16,0,0,64'h0000000200000001);ctx(17,0,0,64'h0000000400000003);
// Scalar extraction/insertion, including sign extension and preserved tail.
command(32'h438021d7,0,0,0,80'he90001,0,20,1,3,8'd4,64'h10);
ctx(62,1,64'habcdef0112345678,0);ctx(63,1,64'hfedcba9876543210,0);
command(32'h4200efd7,64'hfffffffffffffffd,0,0,80'he90002,0,0,0,3,8'd4,64'h10);
ctx(62,0,0,64'habcdef01fffffffd);ctx(63,0,0,64'hfedcba9876543210);
command(32'h43f021d7,0,0,0,80'he90003,0,64'hfffffffffffffffd,1,3,8'd4,64'h10);
// Build v0 via mask XOR, then consume it in an ordinary masked vadd.
ctx(0,1,0,0);ctx(1,1,0,0);
ctx(2,1,10,0);ctx(3,1,0,0);ctx(4,1,12,0);ctx(5,1,0,0);
command(32'h6e112057,0,0,0,80'he90004,0,0,0,3,8'd4,64'h10);
ctx(0,0,0,6);ctx(1,0,0,0);
ctx(32,1,64'h0000000100000001,0);ctx(33,1,64'h0000000100000001,0);
command(32'h00880457,0,0,0,80'he90005,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000300000001);ctx(17,0,0,64'h0000000400000004);
// Return from the new instruction kinds to the reduction path, then extract it.
command(32'h02882c57,0,0,0,80'he90006,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h123456780000000d);ctx(49,0,0,64'hfedcba9876543210);
command(32'h438021d7,0,0,0,80'he90007,0,13,1,3,8'd4,64'h10);
command(32'h420821d7,0,0,0,80'hea0001,0,2,1,3,8'd4,64'h10);
command(32'h4208a1d7,0,0,0,80'hea0002,0,1,1,3,8'd4,64'h10);
command(32'h401821d7,0,0,0,80'hea0003,0,1,1,3,8'd4,64'h10);
monPolling=0;repeat(4)tick();
monAccess(64'h10,4,0,64'h2101);monAccess(64'h18,4,0,64'h3ff);
for(mi=0;mi<13;mi=mi+1)expectedSnap[mi]=refCount[mi];
monAccess(64'h40,0,1,0);
for(mi=0;mi<13;mi=mi+1)monAccess(64'h100+8*mi,4,0,{32'h0,expectedSnap[mi]});
if(monitorReads<100 || expectedSnap[5]==0 || expectedSnap[7]==0 || expectedSnap[8]==0 || expectedSnap[9]!==expectedSnap[10])$fatal(1,"monitor coverage");
$display("PASS monitored-mmio reads=%0d accepted=%0d completed=%0d faults=%0d stops=%0d",monitorReads,expectedSnap[3],expectedSnap[4],expectedSnap[7],expectedSnap[8]);
'''
original=ROOT/'tests/test_vector_memory.py';source=original.read_text()
replacements={
 "choices=['LishiVpuMemory','LishiVpuMemory16']":"choices=['LishiVpuMemory','LishiVpuMemory16','LishiVpuMonitored','SpinorVpu']",
 "'tb.dut.'+instance+'.'":"'tb.dut.vpu.'+instance+'.'",
}
for before,after in replacements.items():
 assert source.count(before)==1,before
 source=source.replace(before,after)
source=source.replace("lines.append('$display(\"PASS vector-memory", "lines.append(MONITOR_END)\n lines.append('$display(\"PASS vector-memory")
ns={'__file__':str(original),'__name__':'monitored_memory_oracle','MONITOR_END':end}
exec(compile(source,str(original),'exec'),ns)
ns['OUT']=ROOT/('build/monitor/integration-spinor' if spinor else 'build/monitor/integration')
ns['MODEL']=ns['MODEL'].replace('dut.engine.','dut.vpu.engine.')+pins
sys.argv += ['--top','SpinorVpu' if spinor else 'LishiVpuMonitored']
ns['main']()
