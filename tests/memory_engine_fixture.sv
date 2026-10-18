
VectorMemoryEngine dut(.*);
reg [63:0] rf[0:63];reg [7:0] mem[0:8191];
integer cycles=0,caseid=0,requests=0,responses=0,ctxreads=0,commits=0,j,k,waits=0,latency=0,kind=0;
reg pending=0,pwrite;reg [63:0] pa,pdata;reg [2:0] psz;reg [79:0] ptoken;integer perror;
reg heldRequest=0,heldCommit=0;reg [220:0] previousRequest;reg [6:0] previousCommit;
always @(posedge clock)if(!reset)begin
 if(heldRequest && (!io_memoryRequest_valid || {io_memoryRequest_bits_address,io_memoryRequest_bits_size,io_memoryRequest_bits_write,io_memoryRequest_bits_data,io_memoryRequest_bits_mask,io_memoryRequest_bits_token,io_memoryRequest_bits_irrevocable}!==previousRequest))$fatal(1,"unstable request");
 if(heldCommit && (!io_commit_valid || io_commit_bits!==previousCommit))$fatal(1,"unstable progress");
 heldRequest<=io_memoryRequest_valid && !io_memoryRequest_ready;heldCommit<=io_commit_valid && !io_commit_ready;
 previousRequest<={io_memoryRequest_bits_address,io_memoryRequest_bits_size,io_memoryRequest_bits_write,io_memoryRequest_bits_data,io_memoryRequest_bits_mask,io_memoryRequest_bits_token,io_memoryRequest_bits_irrevocable};previousCommit<=io_commit_bits;
end
reg [63:0] errorAddress=64'hffffffffffffffff;
assign io_context_ready=cycles%4!=1;
assign io_commit_ready=cycles%3!=1;
assign io_memoryRequest_ready=!pending && !io_memoryResponse_valid && cycles%3!=1;
always @(posedge clock)begin
 if(reset)begin io_contextResult_valid<=0;io_memoryResponse_valid<=0;pending<=0;end
 else begin
  io_contextResult_valid<=io_context_valid && io_context_ready;
  if(io_context_valid && io_context_ready)begin
   io_contextResult_bits<=rf[io_context_bits_address];
   if(io_context_bits_write)rf[io_context_bits_address]<=io_context_bits_data;else ctxreads=ctxreads+1;
  end
  if(io_commit_valid && io_commit_ready)begin io_vstart<=io_commit_bits;commits=commits+1;end
  if(io_memoryRequest_valid && io_memoryRequest_ready)begin
   if(pending || !io_memoryRequest_bits_irrevocable || io_memoryRequest_bits_size>3 || io_memoryRequest_bits_mask!==((1<<(1<<io_memoryRequest_bits_size))-1))$fatal(1,"request protocol");
   pa<=io_memoryRequest_bits_address;pdata<=io_memoryRequest_bits_data;psz<=io_memoryRequest_bits_size;pwrite<=io_memoryRequest_bits_write;ptoken<=io_memoryRequest_bits_token;
   perror<=io_memoryRequest_bits_address==errorAddress?kind:0;waits<=latency;pending<=1;requests=requests+1;
   $display("BUS %0d %016h %0d %0d %016h",caseid,io_memoryRequest_bits_address,io_memoryRequest_bits_size,io_memoryRequest_bits_write,io_memoryRequest_bits_data);
  end
  if(pending && !io_memoryResponse_valid)begin
   if(waits>0)waits<=waits-1;
   else begin
    io_memoryResponse_valid<=1;io_memoryResponse_bits_token<=ptoken^(perror==3?80'h1:80'h0);
    io_memoryResponse_bits_denied<=perror==1;io_memoryResponse_bits_corrupt<=perror==2;io_memoryResponse_bits_protocolError<=perror==4;io_memoryResponse_bits_localError<=perror==5;
    io_memoryResponse_bits_data<=0;
    for(j=0;j<(1<<psz);j=j+1)io_memoryResponse_bits_data[8*j+:8]<=mem[((pa-64'h80000000)&8191)+j];
   end
  end
  if(io_memoryResponse_valid && io_memoryResponse_ready)begin
   if(pwrite && perror==0)for(j=0;j<(1<<psz);j=j+1)mem[((pa-64'h80000000)&8191)+j]<=pdata[8*j+:8];
   pending<=0;io_memoryResponse_valid<=0;responses=responses+1;
  end
 end
end
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>10000000)$fatal(1,"timeout");end endtask
task run(input [31:0] inst,input [63:0] base,stride,input [63:0] typ,input integer length,start,bad,fault,cause,element,expectedStart,count,input [63:0] tval,input integer stopDelay);
integer begun,breq,bread,stopped;reg [159:0] held;begin
 io_vtype=typ;io_vl=length;io_vstart=start;io_command_bits_instruction=inst;io_command_bits_scalar=base;io_command_bits_scalar2=stride;io_command_bits_token=80'h430000+caseid;
 begun=cycles;breq=requests;bread=ctxreads;io_command_valid=1;#1;if(!io_command_ready)$fatal(1,"blocked issue");tick();io_command_valid=0;
 io_command_bits_scalar=~base;io_command_bits_scalar2=~stride;io_command_bits_instruction=0;
 stopped=0;
 while(!io_completion_valid)begin
  if(stopDelay>=0 && !stopped && cycles-begun>=stopDelay)begin io_stop=1;stopped=1;end else io_stop=0;
  tick();
 end
 io_stop=0;
 if(io_completion_bits_instruction!==inst || io_completion_bits_token!==(80'h430000+caseid) || io_completion_bits_writesScalar || io_completion_bits_scalar!==0 || io_completion_bits_illegal!==bad)$fatal(1,"completion case %0d",caseid);
 if(stopDelay<0)begin
  if(io_status_fault!==fault || io_status_interrupted || io_status_cause!==cause || io_status_element!==element || io_status_address!==tval || io_vstart!==expectedStart || requests-breq!=count)$fatal(1,"status case=%0d fault=%b cause=%d index=%d start=%d requests=%d/%d",caseid,io_status_fault,io_status_cause,io_status_element,io_vstart,requests-breq,count);
 end else begin
  if((fault && (!io_status_fault || io_status_interrupted || io_status_element!==element || io_status_cause!==cause || io_status_address!==tval || io_vstart!==expectedStart || requests-breq!=count)) || (!fault && io_status_fault) || (io_status_interrupted && io_vstart!==io_status_element) || (!io_status_interrupted && io_vstart!==0))$fatal(1,"stop progress");
  $display("STOP %0d %0d %0d %0d",caseid,(io_status_fault || io_status_interrupted)?io_status_element:length,requests-breq,io_vstart);
 end
 held={io_status_fault,io_status_interrupted,io_status_cause,io_status_address,io_status_element,io_completion_bits_token};
 repeat(4)begin tick();if(!io_completion_valid || {io_status_fault,io_status_interrupted,io_status_cause,io_status_address,io_status_element,io_completion_bits_token}!==held)$fatal(1,"unstable completion");end
 io_completion_ready=1;tick();io_completion_ready=0;
 if(pending || io_memoryResponse_valid || io_busy)$fatal(1,"undrained completion");
 $display("PERF %0d %0d %0d",caseid,cycles-begun,ctxreads-bread);
end endtask
initial begin
reset=1;tick();tick();reset=0;tick();
