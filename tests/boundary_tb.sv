module tb;
reg clock=0,reset=1,io_flush=0,io_headValid=1,io_olderMemoryDrained=0,io_olderFpDrained=0;
reg [4:0] io_headIndex=0,io_offer_bits_index=0;
reg [63:0] io_headTag=0,io_offer_bits_tag=0;
reg io_offer_valid=0,io_reply_ready=0,io_command_ready=0,io_completion_valid=0;
reg [31:0] io_offer_bits_instruction=0,io_completion_bits_instruction=0;
reg [63:0] io_offer_bits_scalar=0,io_offer_bits_scalar2=0,io_offer_bits_avl=0,io_completion_bits_scalar=0;
reg [79:0] io_completion_bits_token=0;
reg io_completion_bits_writesScalar=0,io_completion_bits_illegal=0;
wire io_offer_ready,io_reply_valid,io_command_valid,io_completion_ready,io_active,io_discarded;
wire [4:0] io_reply_bits_index;
wire [63:0] io_reply_bits_tag,io_reply_bits_data,io_reply_bits_cause,io_reply_bits_tval;
wire io_reply_bits_writesScalar,io_reply_bits_exception;
wire [31:0] io_command_bits_instruction;
wire [63:0] io_command_bits_scalar,io_command_bits_scalar2,io_command_bits_avl;
wire [79:0] io_command_bits_token;
ValenceBoundary dut(.*);
task tick;begin #5;clock=1;#5;clock=0;end endtask
integer i,j;
reg [79:0] token;
initial begin
 tick();tick();reset=0;tick();
 for(i=0;i<128;i=i+1)begin
   io_offer_bits_index=i%32;
   io_offer_bits_tag=64'hdeadbeef01234567+i*64'h102030405;
   io_offer_bits_instruction=32'h002081d7;
   io_offer_bits_scalar=64'h87654321abcdef01+i;
   io_offer_bits_scalar2=64'h12345678fedcba00+i;
   io_offer_bits_avl=i%16;
   token={11'b0,io_offer_bits_tag,io_offer_bits_index};
   io_offer_valid=1;io_command_ready=1;
   io_headIndex=io_offer_bits_index;io_headTag=io_offer_bits_tag^1;
   io_olderMemoryDrained=1;io_olderFpDrained=1;
   #1;if(io_offer_ready || io_command_valid)$fatal(1,"nonhead command launched");tick();
   io_headTag=io_offer_bits_tag;io_olderMemoryDrained=0;
   #1;if(io_offer_ready || io_command_valid)$fatal(1,"undrained memory command launched");tick();
   io_olderMemoryDrained=1;io_olderFpDrained=0;
   #1;if(io_offer_ready || io_command_valid)$fatal(1,"undrained FP command launched");tick();
   io_olderFpDrained=1;io_command_ready=0;
   #1;if(io_offer_ready || !io_command_valid)$fatal(1,"bad command backpressure");
   if(io_command_bits_token !== token || io_command_bits_instruction !== io_offer_bits_instruction ||
      io_command_bits_scalar !== io_offer_bits_scalar || io_command_bits_scalar2 !== io_offer_bits_scalar2 ||
      io_command_bits_avl !== io_offer_bits_avl)$fatal(1,"lost request payload");
   tick();io_command_ready=1;tick();io_offer_valid=0;
   if(!io_active)$fatal(1,"lost owner");
   io_completion_valid=1;io_reply_ready=1;io_completion_bits_token=token^1;
   #1;if(!io_discarded || io_reply_valid)$fatal(1,"stale reply routed");tick();
   if(!io_active)$fatal(1,"stale reply released owner");
   io_completion_bits_token=token;io_completion_bits_instruction=io_offer_bits_instruction;
   io_completion_bits_scalar=i+64'h8000000000000000;
   io_completion_bits_illegal=i%2;io_completion_bits_writesScalar=1;io_reply_ready=0;
   for(j=0;j<5;j=j+1)begin
     #1;if(!io_reply_valid || io_completion_ready || io_discarded)$fatal(1,"bad completion backpressure");
     if(io_reply_bits_index !== io_offer_bits_index || io_reply_bits_tag !== io_offer_bits_tag ||
        io_reply_bits_data !== io_completion_bits_scalar || io_reply_bits_exception !== io_completion_bits_illegal ||
        io_reply_bits_writesScalar !== !io_completion_bits_illegal ||
        io_reply_bits_cause !== (io_completion_bits_illegal?64'd2:64'd0) ||
        io_reply_bits_tval !== (io_completion_bits_illegal?{32'd0,io_offer_bits_instruction}:64'd0))
       $fatal(1,"bad reply payload/ownership");tick();
   end
   if(i%3==0)begin
     io_flush=1;#1;if(io_reply_valid || io_completion_ready || io_offer_ready)$fatal(1,"flush did not gate handshake");
     tick();io_flush=0;
     #1;if(io_active || io_reply_valid || !io_discarded)$fatal(1,"flush stale reply not discarded");tick();
   end else begin io_reply_ready=1;tick();if(io_active)$fatal(1,"owner not released");end
   io_completion_valid=0;io_reply_ready=0;tick();
 end
 $display("PASS boundary transactions=128 stale_rejections=171 blocked_reply_cycles=640");$finish;
end
endmodule
