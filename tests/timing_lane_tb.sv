`timescale 1ns/1fs
module tb;
import timing_reference::*;
localparam real PERIOD=`PERIOD_NS;
reg clock=0,reset=1,io_flush=0,io_in_valid=0,io_out_ready=0;
reg [63:0] io_in_bits_a=0,io_in_bits_b=0;
reg [1:0] io_in_bits_sew=0;
reg [4:0] io_in_bits_op=0;
reg io_in_bits_select=0;
reg [7:0] io_in_bits_tag=0;
wire io_in_ready,io_out_valid;
wire [63:0] io_out_bits_data;
wire [7:0] io_out_bits_tag;
`TOP dut(.*);
always #(PERIOD/2.0)clock=~clock;
integer fd,n,status;
initial begin
 repeat(4)@(posedge clock);
 #0.25;reset=0;
 repeat(3)@(posedge clock);
 enabled=1;
 fd=$fopen("build/test/timing-reference.stim","r");
 for(n=0;n<`STIM_COUNT;n=n+1)begin
   @(posedge clock);
   if(n>0)$display("T %0d %0d %0d %016h %0d",n-1,io_in_ready,io_out_valid,io_out_bits_data,io_out_bits_tag);
   // Source-flop launch after the edge; each DUT input gets a full cycle,
   // less this fixed 0.25 ns clock-to-output budget. No half-cycle stimulus.
   #0.25;
   status=$fscanf(fd,"%d %d %d %h %h %d %d %d %d\n",io_in_valid,io_out_ready,io_flush,
     io_in_bits_a,io_in_bits_b,io_in_bits_sew,io_in_bits_op,io_in_bits_select,io_in_bits_tag);
   if(status!=9)$fatal(1,"bad stimulus");
 end
 @(posedge clock);
 $display("T %0d %0d %0d %016h %0d",n-1,io_in_ready,io_out_valid,io_out_bits_data,io_out_bits_tag);
 #(PERIOD/2.0);
 $display("REFERENCE_COUNTS %0d %0d %0d",timing_reference::setup_violations,
   timing_reference::hold_violations,timing_reference::ram_violations);
 $finish;
end
endmodule
