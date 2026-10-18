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
// Prefix masks: preserve tail/inactive bits, write v0, then consume it.
ctx(6,1,10,0);ctx(7,1,0,0);
ctx(14,1,64'h123456789abcdeff,0);ctx(15,1,64'hfedcba9876543210,0);
cancel(32'h5230a3d7,10,1'b0);
ctx(14,0,0,64'h123456789abcdeff);
command(32'h5230a3d7,0,0,0,80'heb0001,0,0,0,3,8'd4,64'h10);
ctx(14,0,0,64'h123456789abcdef1);ctx(15,0,0,64'hfedcba9876543210);
command(32'h5031a3d7,0,0,0,80'heb0002,0,0,0,3,8'd4,64'h10);
ctx(14,0,0,64'h123456789abcdef3);
command(32'h52312057,0,0,0,80'heb0003,0,0,0,3,8'd4,64'h10);
ctx(0,0,0,2);ctx(1,0,0,0);
command(32'h420821d7,0,0,0,80'heb0004,0,1,1,3,8'd4,64'h10);
command(32'h5000a3d7,0,0,0,80'heb0005,0,0,0,3,8'd4,64'h10);
ctx(14,0,0,64'h123456789abcdef1);
command(32'h5230a1d7,0,0,0,80'heb0006,1,0,0,3,8'd4,64'h10);
command(32'h50312057,0,0,0,80'heb0007,1,0,0,3,8'd4,64'h10);
ctx(0,0,0,2);ctx(6,0,0,10);
// Return from prefix execution to the ordinary masked integer stream.
command(32'h00880457,0,0,0,80'heb0008,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000400000001);ctx(17,0,0,64'h0000000400000004);
// Index generation reaches the public wrapper, consumes mask RAM and feeds
// scalar extraction with exact tail-preserving 32-bit element values.
command(32'h0100f1d7,0,0,4,80'hec0001,0,4,1,3,8'd4,64'h10);
ctx(62,1,64'hb,0);ctx(63,1,0,0);
command(32'h53f82457,0,0,0,80'hec0002,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000100000000);ctx(17,0,0,64'h0000000200000002);
command(32'h428021d7,0,0,0,80'hec0003,0,0,1,3,8'd4,64'h10);
command(32'h5208a457,0,0,0,80'hec0004,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000100000000);ctx(17,0,0,64'h0000000300000002);
// Slides pass through the public command path;
// slide down aliases the source, whereas slide up must reject that alias.
ctx(32,1,64'haaaaaaaa55555555,0);ctx(33,1,64'hbbbbbbbbcccccccc,0);
command(32'h3a80b857,0,0,0,80'hed0001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000000055555555);ctx(33,0,0,64'h0000000200000001);
command(32'h3f00b857,0,0,0,80'hed0002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000000100000000);ctx(33,0,0,64'h0000000000000002);
command(32'h3b02ec57,64'hffffffffffffffff,0,0,80'hed0003,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h00000000ffffffff);ctx(49,0,0,64'h0000000200000001);
command(32'h3f82ec57,5,0,0,80'hed0004,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h0000000100000000);ctx(49,0,0,64'h0000000500000002);
cancel(32'h3b02ec57,18,1'b0);
ctx(48,0,0,64'h0000000100000000);ctx(49,0,0,64'h0000000500000002);
command(32'h3a80b457,0,0,0,80'hed0005,1,0,0,3,8'd4,64'h10);
// Gather reads committed data with vector, scalar and unsigned immediate
// indices. EEW16 indices occupy a fractional group independently of data SEW.
ctx(16,1,64'h0000000200000003,0);ctx(17,1,64'h0000000000000001,0);
command(32'h33840857,0,0,0,80'hee0001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000000200000005);ctx(33,0,0,64'h0000000000000001);
command(32'h3382c457,3,0,0,80'hee0002,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000500000005);ctx(17,0,0,64'h0000000500000005);
command(32'h3380b857,0,0,0,80'hee0003,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000000100000001);ctx(33,0,0,64'h0000000100000001);
ctx(62,1,64'h0004000000020003,0);ctx(63,1,0,0);
command(32'h3b8f8857,0,0,0,80'hee0004,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000000200000005);ctx(33,0,0,0);
cancel(32'h3b8f8857,18,1'b0);
ctx(32,0,0,64'h0000000200000005);ctx(33,0,0,0);
command(32'h33840c57,0,0,0,80'hee0005,1,0,0,3,8'd4,64'h10);
command(32'h33880857,0,0,0,80'hee0006,1,0,0,3,8'd4,64'h10);
command(32'h3382c857,64'hffffffffffffffff,0,0,80'hee0007,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,0);ctx(33,0,0,0);
// Stable RAM compaction through the public interface, preserving packed tail.
ctx(16,1,64'h0000002200000011,0);ctx(17,1,64'h0000004400000033,0);
ctx(6,1,64'ha,0);ctx(7,1,0,0);
ctx(32,1,64'hdeadbeefcafebabe,0);ctx(33,1,64'habcdef0123456789,0);
cancel(32'h5e81a857,18,1'b0);
ctx(32,0,0,64'hdeadbeefcafebabe);ctx(33,0,0,64'habcdef0123456789);
command(32'h5e81a857,0,0,0,80'hef0001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000004400000022);ctx(33,0,0,64'habcdef0123456789);
command(32'h5e81a457,0,0,0,80'hef0002,1,0,0,3,8'd4,64'h10);
command(32'h5e882857,0,0,0,80'hef0003,1,0,0,3,8'd4,64'h10);
command(32'h5e842857,0,0,0,80'hef0004,1,0,0,3,8'd4,64'h10);
command(32'h5c81a857,0,0,0,80'hef0005,1,0,0,3,8'd4,64'h10);
// Resume ordinary integer execution after dense-target addressing.
command(32'h02804457,1,0,0,80'hef0006,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000002300000012);ctx(17,0,0,64'h0000004500000034);
// FP reductions traverse the public issue boundary and monitor alongside TL.
ctx(16,1,64'h400000003f800000,0);ctx(17,1,64'h4080000040400000,0);
ctx(62,1,64'h3f000000,0);ctx(63,1,0,0);
cancel(32'h0e8f9857,30,1'b0);
ctx(32,0,0,64'h0000004400000022);ctx(33,0,0,64'habcdef0123456789);
command(32'h0e8f9857,0,0,0,80'hf00001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000004441280000);ctx(33,0,0,64'habcdef0123456789);
command(32'h068f9857,0,0,0,80'hf00002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000004441280000);
command(32'h168f9857,0,0,0,80'hf00003,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h000000443f000000);
command(32'h1e8f9857,0,0,0,80'hf00004,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h0000004440800000);ctx(33,0,0,64'habcdef0123456789);
// Widened scalar is 64-bit although vtype stays e32/m1.
ctx(16,1,64'h00000002ffffffff,0);ctx(17,1,64'h7fffffff80000000,0);
ctx(62,1,64'h1234567800000010,0);ctx(63,1,0,0);
cancel(32'hc28f8857,18,1'b0);
ctx(32,0,0,64'h0000004440800000);ctx(33,0,0,64'habcdef0123456789);
command(32'hc28f8857,0,0,0,80'hf10001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h1234567a00000010);ctx(33,0,0,64'habcdef0123456789);
command(32'hc68f8857,0,0,0,80'hf10002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h1234567800000010);ctx(33,0,0,64'habcdef0123456789);
command(32'hc2840857,0,0,0,80'hf10003,1,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h1234567800000010);
command(32'h02804457,1,0,0,80'hf10004,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h0000000300000000);ctx(17,0,0,64'h8000000080000001);
// Exact FP32 promotion with FP64 seed and scalar writeback.
ctx(16,1,64'h400000003f800000,0);ctx(17,1,64'h4080000040400000,0);
ctx(62,1,64'h3fe0000000000000,0);ctx(63,1,0,0);
cancel(32'hce8f9857,70,1'b0);
ctx(32,0,0,64'h1234567800000010);ctx(33,0,0,64'habcdef0123456789);
command(32'hce8f9857,0,0,0,80'hf20001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h4025000000000000);ctx(33,0,0,64'habcdef0123456789);
command(32'hc68f9857,0,0,0,80'hf20002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h4025000000000000);ctx(33,0,0,64'habcdef0123456789);
command(32'hc6841857,0,0,0,80'hf20003,1,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h4025000000000000);
command(32'h02804457,1,0,0,80'hf20004,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h400000013f800001);ctx(17,0,0,64'h4080000140400001);
// Packed e8/e16 sources are extended using their own source address geometry.
ctx(16,1,64'h0001ffff7fff8000,0);ctx(17,1,0,0);
cancel(32'h4a83a857,18,1'b0);
ctx(32,0,0,64'h4025000000000000);ctx(33,0,0,64'habcdef0123456789);
command(32'h4a832857,0,0,0,80'hf30001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h00007fff00008000);ctx(33,0,0,64'h000000010000ffff);
command(32'h4a83a857,0,0,0,80'hf30002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h00007fffffff8000);ctx(33,0,0,64'h00000001ffffffff);
// Fractional source may not overlap the destination, including with VL=0.
command(32'h4b03a857,0,0,0,80'hf30003,1,0,0,3,8'd4,64'h10);
command(32'h03004457,1,0,0,80'hf30004,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h00008000ffff8001);ctx(17,0,0,64'h0000000200000000);
// Narrow 64-bit sources into e32 destinations without disturbing masked data.
ctx(16,1,64'h8000000000000000,0);ctx(17,1,64'h7fffffffffffffff,0);
ctx(18,1,64'hffffffff00000001,0);ctx(19,1,64'h0000000180000000,0);
ctx(32,1,64'hdeadbeefcafebabe,0);ctx(33,1,64'habcdef0123456789,0);
cancel(32'hb282c857,18,1'b0);
ctx(32,0,0,64'hdeadbeefcafebabe);ctx(33,0,0,64'habcdef0123456789);
command(32'hb282c857,32,0,0,80'hf40001,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'h7fffffff80000000);ctx(33,0,0,64'h00000001ffffffff);
command(32'hb68fb857,0,0,0,80'hf40002,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'hffffffff00000000);ctx(33,0,0,64'h00000003fffffffe);
ctx(0,1,5,0);ctx(1,1,0,0);
ctx(48,1,64'h0000000000000020,0);ctx(49,1,64'h000000400000003f,0);
command(32'hb08c0857,0,0,0,80'hf40003,0,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'hffffffff80000000);ctx(33,0,0,64'h0000000300000001);
command(32'hb2840857,0,0,0,80'hf40004,1,0,0,3,8'd4,64'h10);
ctx(32,0,0,64'hffffffff80000000);ctx(33,0,0,64'h0000000300000001);
// Double-width integer vector destinations; masked .w operation keeps inactive elements.
ctx(16,1,64'h00000002ffffffff,0);ctx(17,1,64'h7fffffff80000000,0);
ctx(32,1,64'hffffffff00000001,0);ctx(33,1,64'h8000000000000002,0);
ctx(48,1,64'hdeadbeefcafebabe,0);ctx(49,1,64'habcdef0123456789,0);
ctx(50,1,64'h0123456789abcdef,0);ctx(51,1,64'h9876543210abcdef,0);
cancel(32'hc2882c57,35,1'b0);
ctx(48,0,0,64'hdeadbeefcafebabe);ctx(49,0,0,64'habcdef0123456789);
command(32'hc2882c57,0,0,0,80'hf50001,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h100000000);ctx(49,0,0,64'h100000001);
ctx(50,0,0,64'h80000002);ctx(51,0,0,64'hffffffff);
command(32'hd782ec57,64'hffffffffffffffff,0,0,80'hf50002,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hffffffff);ctx(49,0,0,64'h100000000);
ctx(50,0,0,64'h80000001);ctx(51,0,0,64'hfffffffe);
command(32'hdd882c57,0,0,0,80'hf50003,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hfffffffe);ctx(49,0,0,64'h100000000);
ctx(50,0,0,64'h7fffffff);ctx(51,0,0,64'hfffffffe);
command(32'hc282e457,0,0,0,80'hf50004,1,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h00000002ffffffff);ctx(17,0,0,64'h7fffffff80000000);
// Full 64-bit products from e32 sources; candidate flush and mixed signedness.
ctx(16,1,64'h00000002ffffffff,0);ctx(17,1,64'h7fffffff80000000,0);
ctx(32,1,64'hffffffff00000001,0);ctx(33,1,64'h8000000000000002,0);
cancel(32'he2882c57,85,1'b0);
ctx(48,0,0,64'hfffffffe);ctx(49,0,0,64'h100000000);ctx(50,0,0,64'h7fffffff);ctx(51,0,0,64'hfffffffe);
command(32'he2882c57,64'hffffffffffffffff,0,0,80'hf60001,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hffffffff);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'h100000000);
ctx(51,0,0,64'h3fffffff80000000);
command(32'hea882c57,64'hffffffffffffffff,0,0,80'hf60002,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hffffffffffffffff);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'hffffffff00000000);
ctx(51,0,0,64'h3fffffff80000000);
command(32'hee882c57,64'hffffffffffffffff,0,0,80'hf60003,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hffffffffffffffff);
ctx(49,0,0,64'hfffffffffffffffe);
ctx(50,0,0,64'hffffffff00000000);
ctx(51,0,0,64'hc000000080000000);
command(32'he282ec57,64'hffffffffffffffff,0,0,80'hf60004,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hfffffffe00000001);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'h7fffffff80000000);
ctx(51,0,0,64'h7ffffffe80000001);
command(32'hea82ec57,64'hffffffffffffffff,0,0,80'hf60005,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hffffffff00000001);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'h8000000080000000);
ctx(51,0,0,64'h7ffffffe80000001);
command(32'hec82ec57,64'hffffffffffffffff,0,0,80'hf60006,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h1);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'h80000000);
ctx(51,0,0,64'h7ffffffe80000001);
command(32'he6882c57,0,0,0,80'hf60007,1,0,0,3,8'd4,64'h10);
command(32'he2886457,0,0,0,80'hf60008,1,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h1);
ctx(49,0,0,64'h1fffffffe);
ctx(50,0,0,64'h80000000);
ctx(51,0,0,64'h7ffffffe80000001);
// M36: signed-scalar/narrow-vector MAC, whole copies, reverse subtract and mask compare.
ctx(16,1,64'h00000002ffffffff,0);ctx(17,1,64'h0000000380000000,0);
ctx(32,1,64'hffffffff00000001,0);ctx(33,1,64'h8000000000000002,0);
ctx(48,1,1,0);ctx(49,1,2,0);ctx(50,1,3,0);ctx(51,1,4,0);
command(32'hfe882c57,0,0,0,80'hf70001,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h100000000);ctx(49,0,0,0);ctx(50,0,0,64'h100000003);ctx(51,0,0,64'hfffffffe80000004);
command(32'h9f80be57,0,0,0,80'hf70002,0,0,0,3,8'd4,64'h10);
ctx(56,0,0,64'h100000000);ctx(57,0,0,0);ctx(58,0,0,64'h100000003);ctx(59,0,0,64'hfffffffe80000004);
command(32'h0e80c457,1,0,0,80'hf70003,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'hffffffff00000002);ctx(17,0,0,64'hfffffffe80000001);
ctx(0,1,0,0);ctx(1,1,0,0);
command(32'h7e803057,0,0,0,80'hf70004,0,0,0,3,8'd4,64'h10);
ctx(0,0,0,1);ctx(1,0,0,0);
// M37: fixed-point sticky retirement and v0 carry input across unit switches.
command(32'h00f091f3,0,0,0,80'hf80000,0,7,1,3,8'd4,64'h10);
command(32'h0000f1d7,0,0,4,80'hf80001,0,4,1,3,8'd4,0);
ctx(16,1,64'h8877665501807fff,0);ctx(17,1,64'h0123456789abcdef,0);
ctx(32,1,64'h44332211ff800101,0);ctx(33,1,0,0);
ctx(48,1,64'h0a0b0c0ddeadbeef,0);ctx(49,1,64'h0102030405060708,0);
ctx(0,1,10,0);ctx(1,1,0,0);
command(32'h86880c57,0,0,0,80'hf80002,0,0,0,3,8'd4,0);
ctx(48,0,0,64'ha0b0c0d00807f00);ctx(49,0,0,64'h0102030405060708);
command(32'h40880c57,0,0,0,80'hf80003,0,0,0,3,8'd4,0);
ctx(48,0,0,64'ha0b0c0d01008100);ctx(49,0,0,64'h0102030405060708);
command(32'h22882c57,0,0,0,80'hf80004,0,0,0,3,8'd4,0);
ctx(48,0,0,64'ha0b0c0d80804080);ctx(49,0,0,64'h0102030405060708);
command(32'hae80bc57,0,0,0,80'hf80005,0,0,0,3,8'd4,0);
ctx(48,0,0,64'ha0b0c0d01c04000);ctx(49,0,0,64'h0102030405060708);
command(32'h009021f3,0,0,0,80'hf80006,0,1,1,3,8'd4,0);
// Return to the ordinary streaming ALU and FP after the new serialized unit.
command(32'h2880c57,0,0,0,80'hf80007,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h0a0b0c0d00008000);ctx(49,0,0,64'h0102030405060708);
command(32'h0100f1d7,0,0,2,80'hf80008,0,2,1,3,8'd2,64'h10);
ctx(16,1,64'hc00000003f800000,0);ctx(17,1,0,0);
ctx(32,1,64'h3f00000040000000,0);ctx(33,1,0,0);
command(32'h2881c57,0,0,0,80'hf80009,0,0,0,3,8'd2,64'h10);
ctx(48,0,0,64'hbfc0000040400000);ctx(49,0,0,64'h0102030405060708);
command(32'h009021f3,0,0,0,80'hf8000a,0,1,1,3,8'd2,64'h10);
// M38: fractional MIN*MIN, post-round clip overflow and the shared whole-move opcode.
command(32'h00f091f3,0,0,0,80'hf90000,0,1,1,3,8'd2,64'h10);
command(32'h0000f1d7,0,0,4,80'hf90001,0,4,1,3,8'd4,0);
ctx(16,1,64'h8877665501ff7f80,0);ctx(17,1,64'h0123456789abcdef,0);
ctx(32,1,64'h44332211ff807f80,0);ctx(33,1,0,0);
ctx(48,1,64'h0a0b0c0ddeadbeef,0);ctx(49,1,64'h0102030405060708,0);
command(32'h9e880c57,0,0,0,80'hf90002,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h0a0b0c0d00017e7f);ctx(49,0,0,64'h0102030405060708);
command(32'h009091f3,0,0,0,80'hf90003,0,1,1,3,8'd4,0);
ctx(32,1,64'h0000ffff00ff01ff,0);ctx(33,1,0,0);
command(32'hbb00cc57,1,0,0,80'hf90004,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h0a0b0c0d00ff80ff);ctx(49,0,0,64'h0102030405060708);
command(32'h009091f3,0,0,0,80'hf90005,0,1,1,3,8'd4,0);
ctx(32,1,64'hff000100feff00ff,0);ctx(33,1,0,0);
command(32'hbf00bc57,0,0,0,80'hf90006,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h0a0b0c0d807f807f);ctx(49,0,0,64'h0102030405060708);
command(32'h9e80cc57,128,0,0,80'hf90007,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h0a0b0c0dff01817f);ctx(49,0,0,64'h0102030405060708);
command(32'h9e803c57,0,0,0,80'hf90008,0,0,0,3,8'd4,0);
ctx(48,0,0,64'h8877665501ff7f80);ctx(49,0,0,64'h0123456789abcdef);
command(32'h009021f3,0,0,0,80'hf90009,0,1,1,3,8'd4,0);
// M39 raw FP transfers: f0 is writable; unboxed scalar becomes canonical NaN.
command(32'h0100f1d7,0,0,4,80'hfa0001,0,4,1,3,8'd4,64'h10);
ctx(32,1,64'h800000007f800001,0);ctx(33,1,64'h7fc123453f800000,0);
ctx(48,1,64'habcd1234deadbeef,0);ctx(49,1,64'h0123456789abcdef,0);
command(32'h43001057,0,0,0,80'hfa0002,0,64'hffffffff7f800001,1,3,8'd4,64'h10);
command(32'h4200dc57,64'h7f800001,0,0,80'hfa0003,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'habcd12347fc00000);ctx(49,0,0,64'h0123456789abcdef);
command(32'h3b00dc57,64'hffffffff80000000,0,0,80'hfa0004,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h7f80000180000000);ctx(49,0,0,64'h3f80000080000000);
command(32'h3f80dc57,64'hffffffff7fc01234,0,0,80'hfa0005,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h800000007f800001);ctx(49,0,0,64'h7fc012343f800000);
// M40: narrow+narrow wide add, wide accumulator FMA, wide-source scalar/vector.
ctx(32,1,64'h400000003f800000,0);ctx(33,1,64'h4080000040400000,0);
ctx(48,1,64'h40c0000040a00000,0);ctx(49,1,64'h4100000040e00000,0);
command(32'hc30c1457,64'h0,0,0,80'hfb0000,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h4018000000000000);
ctx(17,0,0,64'h4020000000000000);
ctx(18,0,0,64'h4024000000000000);
ctx(19,0,0,64'h4028000000000000);
command(32'hf300d457,64'hffffffff40000000,0,0,80'hfb0001,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h4020000000000000);
ctx(17,0,0,64'h4028000000000000);
ctx(18,0,0,64'h4030000000000000);
ctx(19,0,0,64'h4034000000000000);
command(32'hda80d457,64'hffffffff3f800000,0,0,80'hfb0002,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h401c000000000000);
ctx(17,0,0,64'h4026000000000000);
ctx(18,0,0,64'h402e000000000000);
ctx(19,0,0,64'h4033000000000000);
command(32'hd28c1457,64'h0,0,0,80'hfb0003,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h4028000000000000);
ctx(17,0,0,64'h4031000000000000);
ctx(18,0,0,64'h4036000000000000);
ctx(19,0,0,64'h403b000000000000);
// M41 cross-width conversions: literal known answers through public command/context.
command(32'h4b061457,0,0,0,80'hfc000c,0,0,0,3,8'd4,64'h10);
ctx(16,0,0,64'h3ff0000000000000);
ctx(17,0,0,64'h4000000000000000);
ctx(18,0,0,64'h4008000000000000);
ctx(19,0,0,64'h4010000000000000);
command(32'h4a8a1c57,0,0,0,80'hfc0014,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'h400000003f800000);ctx(49,0,0,64'h4080000040400000);
ctx(16,1,64'h3ff0000010000000,0);
ctx(17,1,64'hbff0000010000000,0);
ctx(18,1,64'h3690000000000000,0);
ctx(19,1,64'h7ff0000000000000,0);
command(32'h4a8a9c57,0,0,0,80'hfc0015,0,0,0,3,8'd4,64'h10);
ctx(48,0,0,64'hbf8000013f800001);ctx(49,0,0,64'h7f80000000000001);
command(32'h0080f1d7,0,0,4,80'hfc0010,0,4,1,3,8'd4,64'h8);
ctx(32,1,64'h80007fff0000ffff,0);
command(32'h4b059457,0,0,0,80'hfc000b,0,0,0,3,8'd4,64'h8);
ctx(16,0,0,64'h00000000bf800000);ctx(17,0,0,64'hc700000046fffe00);
command(32'h4a889c57,0,0,0,80'hfc0011,0,0,0,3,8'd4,64'h8);
ctx(48,0,0,64'h80007fff0000ffff);
// M42 estimates: normative FP32 examples and FP64 1/4 literal answers.
command(32'h0100f1d7,0,0,2,80'hfe0010,0,2,1,3,8'd2,64'h10);
ctx(32,1,64'h7f76543200718abc,0);
command(32'h4f029457,0,0,0,80'hfe0005,0,0,0,3,8'd2,64'h10);
ctx(16,0,0,64'h002140007e900000);
command(32'h4f021457,0,0,0,80'hfe0004,0,0,0,3,8'd2,64'h10);
ctx(16,0,0,64'h1f8200005f080000);
command(32'h0180f1d7,0,0,2,80'hfe0018,0,2,1,3,8'd2,64'h18);
ctx(32,1,64'h3ff0000000000000,0);ctx(33,1,64'h4010000000000000,0);
command(32'h4f029457,0,0,0,80'hfe0065,0,0,0,3,8'd2,64'h18);
ctx(16,0,0,64'h3fefe00000000000);ctx(17,0,0,64'h3fcfe00000000000);
command(32'h4f021457,0,0,0,80'hfe0064,0,0,0,3,8'd2,64'h18);
ctx(16,0,0,64'h3fefe00000000000);ctx(17,0,0,64'h3fdfe00000000000);
monPolling=0;repeat(4)tick();
monAccess(64'h10,4,0,64'h4201);monAccess(64'h18,4,0,64'hffffffff);
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
