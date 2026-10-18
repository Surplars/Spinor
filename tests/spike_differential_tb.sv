// PIN_DECLARATIONS
`TOP dut(.*);
integer cycles=0,commands=0,reads=0;
reg [31:0] originalVersions;
reg [63:0] originalType;
reg [7:0] originalVl;
reg [6:0] originalStart;
reg [1:0] originalVxrm;
reg originalSat;
reg [2:0] originalFrm;
reg [4:0] originalFlags;

task tick;
begin
 #5;clock=1;#5;clock=0;cycles=cycles+1;
 if(cycles>20000000)$fatal(1,"differential timeout");
 if(io_tl_a_valid)$fatal(1,"non-memory differential emitted TL traffic");
end endtask

task ctx_access(input integer address,input bit write,input [63:0] data);
begin
 io_core_context_valid=1;io_core_context_bits_address=address;
 io_core_context_bits_write=write;io_core_context_bits_data=data;
 #1;if(io_core_context_ready!==1)$fatal(1,"context blocked");
 tick();io_core_context_valid=0;
 if(io_core_contextResult_valid!==1)$fatal(1,"missing context response");
 if(!write)begin
  reads=reads+1;
  if(io_core_contextResult_bits!==data)$fatal(1,"Spike RF mismatch command=%0d chunk=%0d got=%h expected=%h",commands-1,address,io_core_contextResult_bits,data);
 end
 tick();
end endtask

task unchanged;
begin
 if(io_core_versions!==originalVersions || io_core_vtype!==originalType || io_core_vl!==originalVl ||
  io_core_vstart!==originalStart || io_core_vxrm!==originalVxrm || io_core_vxsat!==originalSat ||
  `FRM!==originalFrm || `FLAGS!==originalFlags)$fatal(1,"early architecture publication command=%0d",commands);
end endtask

task command(input integer id,input [31:0] instruction,input [63:0] scalar,input [63:0] scalar2,input [63:0] avl,
 input bit illegal,input bit writes,input [63:0] result,
 input [7:0] vl,input [63:0] vtype,input [6:0] vstart,input [1:0] vxrm,input bit vxsat,input [2:0] frm,input [4:0] flags);
reg [79:0] token;
reg [63:0] heldScalar;
integer started;
begin
 started=cycles;token={16'h50de,32'hfedcab09,id[31:0]};
 originalVersions=io_core_versions;originalType=io_core_vtype;originalVl=io_core_vl;
 originalStart=io_core_vstart;originalVxrm=io_core_vxrm;originalSat=io_core_vxsat;
 originalFrm=`FRM;originalFlags=`FLAGS;
 io_core_command_bits_instruction=instruction;io_core_command_bits_scalar=scalar;
 io_core_command_bits_scalar2=scalar2;io_core_command_bits_avl=avl;io_core_command_bits_token=token;
 io_core_command_valid=1;#1;if(io_core_command_ready!==1)$fatal(1,"command unavailable");
 tick();io_core_command_valid=0;
 while(!io_core_completion_valid)begin unchanged();tick();end
 heldScalar=io_core_completion_bits_scalar;
 repeat(id%4+1)begin
  unchanged();
  if(io_core_completion_valid!==1 || io_core_completion_bits_token!==token || io_core_completion_bits_instruction!==instruction ||
   io_core_completion_bits_illegal!==illegal || io_core_completion_bits_writesScalar!==writes ||
   io_core_completion_bits_scalar!==heldScalar || (writes && io_core_completion_bits_scalar!==result))$fatal(1,"Spike completion mismatch id=%0d instruction=%h illegal=%b/%b writes=%b/%b scalar=%h/%h",id,instruction,io_core_completion_bits_illegal,illegal,io_core_completion_bits_writesScalar,writes,io_core_completion_bits_scalar,result);
  tick();
 end
 io_core_completion_ready=1;tick();io_core_completion_ready=0;
 if(io_core_vl!==vl || io_core_vtype!==vtype || io_core_vstart!==vstart || io_core_vxrm!==vxrm || io_core_vxsat!==vxsat ||
  `FRM!==frm || `FLAGS!==flags)$fatal(1,"Spike CSR mismatch id=%0d instruction=%h VL=%h/%h vtype=%h/%h vstart=%h/%h vxrm=%h/%h vxsat=%h/%h frm=%h/%h flags=%h/%h",id,instruction,io_core_vl,vl,io_core_vtype,vtype,io_core_vstart,vstart,io_core_vxrm,vxrm,io_core_vxsat,vxsat,`FRM,frm,`FLAGS,flags);
 commands=commands+1;
 $display("CMD %0d %0d",id,cycles-started);
end endtask

initial begin
 reset=1;tick();tick();reset=0;tick();
 // EVENTS
 $display("PASS Spike differential commands=%0d reads=%0d cycles=%0d",commands,reads,cycles);
 $finish;
end
endmodule
