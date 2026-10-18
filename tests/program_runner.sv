// Simulation-only RV64 scalar subset. Vector execution is exclusively the DUT.
// No Orbital implementation, privilege, cache, MMU, interrupts, or scalar FP.
// PIN_DECLARATIONS
`TOP dut(.*);
localparam [63:0] BASE=64'h80000000;
reg [7:0] mem[0:65535];
reg [63:0] x[0:31];
reg [63:0] pc,nextpc,a,b,value,addr,imm;
reg [31:0] inst,word;
integer rd,rs1,rs2,f3,f7,op,j,k,caseid,cycles=0,steps,commands,requests,responses;
integer pending=0,latency=0,caseStart,cmdStart,reqStart,scalarSteps,fd;
reg [63:0] heldData;
reg [2:0] heldOp,heldSize;
reg [3:0] heldSource;
reg [79:0] token;
reg [31:0] heldInst;
reg heldWrite,heldIllegal;
reg [7:0] heldVl;
reg [63:0] heldType;
integer family[0:7];
assign io_tl_a_ready=!pending && !io_tl_d_valid && cycles%5!=1;

function automatic integer offset(input [63:0] address);
begin
 if(address>=BASE && address<BASE+65536)offset=address-BASE;
 // A second RAM page at the configured region end exercises real FOF trim.
 else if(address>=64'h8ffff000 && address<64'h90000000)offset=16'hb000+address[11:0];
 else begin $fatal(1,"runner RAM address=%h pc=%h case=%0d",address,pc,caseid);offset=0;end
end endfunction

function automatic [63:0] load(input [63:0] address,input integer bytes);
integer q,t;reg [63:0] result;
begin
 if(address%bytes!=0)$fatal(1,"scalar unaligned load");
 result=0;
 for(q=0;q<bytes;q=q+1)begin t=offset(address+q);result=result|({56'b0,mem[t]}<<(8*q));end
 load=result;
end endfunction

task store(input [63:0] address,input integer bytes,input [63:0] data);
integer q,t;
begin
 if(address%bytes!=0)$fatal(1,"scalar unaligned store");
 for(q=0;q<bytes;q=q+1)begin
  t=offset(address+q);
  if(t<16'h4000 || (t>=16'h6000 && t<16'hd000))$fatal(1,"scalar write outside output/stack");
  mem[t]=data>>(8*q);
 end
end endtask

always @(posedge clock)begin
 if(reset)begin io_tl_d_valid<=0;pending<=0;latency<=0;end
 else begin
  if(io_tl_d_valid && io_tl_d_ready)begin io_tl_d_valid<=0;responses=responses+1;end
  if(pending)begin
   if(latency==0)begin pending<=0;io_tl_d_valid<=1;end
   else latency<=latency-1;
  end
  if(io_tl_a_valid && io_tl_a_ready)begin
   if(pending || io_tl_d_valid)$fatal(1,"multiple outstanding TL");
   if(io_tl_a_bits_size>3 || io_tl_a_bits_param!=0 || io_tl_a_bits_corrupt ||
     io_tl_a_bits_address%(1<<io_tl_a_bits_size)!=0 ||
     io_tl_a_bits_mask!==((8'hff>>(8-(1<<io_tl_a_bits_size)))<<io_tl_a_bits_address[2:0]))$fatal(1,"bad TL shape");
   if(io_tl_a_bits_opcode!=4 && io_tl_a_bits_opcode!=0)$fatal(1,"bad TL opcode");
   requests=requests+1;pending<=1;latency<=1+(requests%4);
   io_tl_d_bits_opcode<=io_tl_a_bits_opcode==4?1:0;
   io_tl_d_bits_size<=io_tl_a_bits_size;io_tl_d_bits_source<=io_tl_a_bits_source;
   io_tl_d_bits_data<=load(io_tl_a_bits_address&~64'd7,8)^($test$plusargs("bad-tl")?64'd1:64'd0);
   if(io_tl_a_bits_opcode==0)begin
    for(k=0;k<8;k=k+1)if(io_tl_a_bits_mask[k])begin
     j=offset((io_tl_a_bits_address&~64'd7)+k);
     if(j<16'h4000 || j>=16'h6000)$fatal(1,"vector write outside output");
     mem[j]=io_tl_a_bits_data>>(8*k);
    end
   end
  end
 end
end

task tick;
begin
 #5;clock=1;#5;clock=0;cycles=cycles+1;
 if(cycles-caseStart>2000000)$fatal(1,"program timeout pc=%h inst=%h case=%0d",pc,inst,caseid);
end endtask

task vector;
integer stall;
begin
 token={16'hf149,pc[31:0],commands[31:0]};
 io_core_command_bits_instruction=inst;
 io_core_command_bits_scalar=a;io_core_command_bits_scalar2=b;io_core_command_bits_avl=a;
 io_core_command_bits_token=token;io_core_command_valid=1;
 #1;while(!io_core_command_ready)tick();tick();io_core_command_valid=0;
 while(!io_core_completion_valid)tick();
 heldData=io_core_completion_bits_scalar;heldInst=io_core_completion_bits_instruction;
 heldWrite=io_core_completion_bits_writesScalar;heldIllegal=io_core_completion_bits_illegal;
 heldVl=io_core_vl;heldType=io_core_vtype;
 for(stall=0;stall<commands%4+1;stall=stall+1)begin
  if(!io_core_completion_valid || io_core_completion_bits_token!==token ||
    io_core_completion_bits_instruction!==heldInst || io_core_completion_bits_scalar!==heldData ||
    io_core_completion_bits_writesScalar!==heldWrite || io_core_completion_bits_illegal!==heldIllegal ||
    io_core_vl!==heldVl || io_core_vtype!==heldType)$fatal(1,"unstable program completion");
  if((op==7 || op==39) && (!io_memoryStatus_valid || io_memoryStatus_bits_fault || io_memoryStatus_bits_interrupted))
   $fatal(1,"program memory exception pc=%h inst=%h cause=%0d tval=%h",pc,inst,io_memoryStatus_bits_cause,io_memoryStatus_bits_address);
  tick();
 end
 if(heldIllegal || heldInst!==inst || io_core_completion_bits_token!==token)
  $fatal(1,"program illegal/token pc=%h inst=%h case=%0d",pc,inst,caseid);
 if(heldWrite && rd!=0)x[rd]=heldData;
 // Count dynamic vector families independently of compiler mnemonics.
 if(op==7 || op==39)begin
  if(inst[31:29]!=0 && !(inst[27:26]==0 && inst[24:20]==8))family[3]=family[3]+1;
  if(inst[27:26]==1 || inst[27:26]==3)family[4]=family[4]+1;
  if(inst[27:26]==0 && inst[24:20]==8)family[2]=family[2]+1;
  if(op==7 && inst[27:26]==0 && inst[24:20]==16)family[5]=family[5]+1;
 end
 if(op==87 && f3!=7 && !inst[25])family[6]=family[6]+1;
 if(op==87 && (f3==1 || f3==5))family[7]=family[7]+1;
 if(op==87 && f3==7)family[0]=family[0]+1;
 if(op==115)family[1]=family[1]+1;
 io_core_completion_ready=1;tick();io_core_completion_ready=0;
 commands=commands+1;
 $display("VEC %0d %h %h %0d %h %0d",caseid,pc,inst,io_core_vl,heldData,heldWrite);
end endtask

task execute(input [63:0] entry);
begin
 pc=entry;steps=0;scalarSteps=0;
 while(pc!=64'hfffffff0)begin
  if(pc[1:0]!=0 || pc<BASE || pc>=BASE+16'h4000)$fatal(1,"bad instruction PC=%h",pc);
  inst=load(pc,4);op=inst[6:0];rd=inst[11:7];rs1=inst[19:15];rs2=inst[24:20];
  f3=inst[14:12];f7=inst[31:25];a=x[rs1];b=x[rs2];nextpc=pc+4;
  if(op==87 || op==7 || op==39 || (op==115 && f3!=0))vector();
  else begin
   scalarSteps=scalarSteps+1;
   case(op)
    55:x[rd]={{32{inst[31]}},inst[31:12],12'b0}; // LUI
    23:x[rd]=pc+{{32{inst[31]}},inst[31:12],12'b0};
    111:begin imm={{43{inst[31]}},inst[31],inst[19:12],inst[20],inst[30:21],1'b0};x[rd]=pc+4;nextpc=pc+imm;end
    103:begin if(f3!=0)$fatal(1,"JALR funct3");imm={{52{inst[31]}},inst[31:20]};x[rd]=pc+4;nextpc=(a+imm)&~64'd1;end
    99:begin
     imm={{51{inst[31]}},inst[31],inst[7],inst[30:25],inst[11:8],1'b0};
     case(f3)
      0:value=a==b;1:value=a!=b;4:value=$signed(a)<$signed(b);5:value=$signed(a)>=$signed(b);
      6:value=a<b;7:value=a>=b;default:$fatal(1,"branch funct3");
     endcase
     if(value)nextpc=pc+imm;
    end
    3:begin
     addr=a+{{52{inst[31]}},inst[31:20]};
     case(f3)
      0:begin value=load(addr,1);x[rd]={{56{value[7]}},value[7:0]};end
      1:begin value=load(addr,2);x[rd]={{48{value[15]}},value[15:0]};end
      2:begin value=load(addr,4);x[rd]={{32{value[31]}},value[31:0]};end
      3:x[rd]=load(addr,8);4:x[rd]=load(addr,1);5:x[rd]=load(addr,2);6:x[rd]=load(addr,4);
      default:$fatal(1,"load funct3");
     endcase
    end
    35:begin
     addr=a+{{52{inst[31]}},inst[31:25],inst[11:7]};
     if(f3>3)$fatal(1,"store funct3");store(addr,1<<f3,b);
    end
    19,27:begin
     imm={{52{inst[31]}},inst[31:20]};
     case(f3)
      0:value=a+imm;2:value=$signed(a)<$signed(imm);3:value=a<imm;4:value=a^imm;6:value=a|imm;7:value=a&imm;
      1:begin
       if((op==27 && (inst[31:25]!=0)) || (op==19 && inst[31:26]!=0))$fatal(1,"reserved SLLI");
       value=a<<(op==27?inst[24:20]:inst[25:20]);
      end
      5:begin
       if((op==27 && inst[31:25]!=0 && inst[31:25]!=32) || (op==19 && inst[31:26]!=0 && inst[31:26]!=16))$fatal(1,"reserved shift immediate");
       if(op==27)begin
        word=a[31:0];
        if(inst[30])value=$signed(word)>>>inst[24:20];else value=word>>inst[24:20];
       end else begin
        if(inst[30])value=$signed(a)>>>inst[25:20];else value=a>>inst[25:20];
       end
      end
      default:$fatal(1,"immediate funct3");
     endcase
     x[rd]=op==27?{{32{value[31]}},value[31:0]}:value;
    end
    51,59:begin
     if(f7==1)begin
      case(f3)
       0:value=a*b;
       4:begin
        if(op==59)begin a={{32{a[31]}},a[31:0]};b={{32{b[31]}},b[31:0]};end
        if(b==0)value=64'hffffffffffffffff;
        else if(a==64'h8000000000000000 && b==64'hffffffffffffffff)value=a;
        else value=$signed(a)/$signed(b);
       end
       5:begin
        if(op==59)begin a={32'b0,a[31:0]};b={32'b0,b[31:0]};end
        value=b==0?64'hffffffffffffffff:a/b;
       end
       6:begin
        if(op==59)begin a={{32{a[31]}},a[31:0]};b={{32{b[31]}},b[31:0]};end
        if(b==0)value=a;
        else if(a==64'h8000000000000000 && b==64'hffffffffffffffff)value=0;
        else value=$signed(a)%$signed(b);
       end
       7:begin
        if(op==59)begin a={32'b0,a[31:0]};b={32'b0,b[31:0]};end
        value=b==0?a:a%b;
       end
       default:$fatal(1,"unsupported multiply-high");
      endcase
     end else begin
      if(f7!=0 && !(f7==32 && (f3==0 || f3==5)))$fatal(1,"reserved register funct7");
      case(f3)
       0:value=f7==32?a-b:a+b;1:value=a<<(op==59?b[4:0]:b[5:0]);
       2:value=$signed(a)<$signed(b);3:value=a<b;4:value=a^b;6:value=a|b;7:value=a&b;
       5:begin
        if(op==59)begin
         word=a[31:0];
         if(f7==32)value=$signed(word)>>>b[4:0];else value=word>>b[4:0];
        end else begin
         if(f7==32)value=$signed(a)>>>b[5:0];else value=a>>b[5:0];
        end
       end
       default:$fatal(1,"register funct3");
      endcase
     end
     x[rd]=op==59?{{32{value[31]}},value[31:0]}:value;
    end
    15:begin if(f3!=0)$fatal(1,"unsupported fence");end
    default:$fatal(1,"unsupported scalar pc=%h inst=%h",pc,inst);
   endcase
   tick();
  end
  x[0]=0;pc=nextpc;steps=steps+1;
  if(steps>100000)$fatal(1,"instruction limit");
 end
 if(pending || io_tl_d_valid || requests!=responses || io_core_busy || io_core_vstart!==0)$fatal(1,"program did not drain");
 // FP_STATE_CHECK
end endtask

task run_case(input integer id,input [63:0] entry,input [63:0] argA,input integer n,input string image,input string dump);
integer q;
string actualDump;
begin
 caseid=id;caseStart=cycles;reset=1;tick();tick();reset=0;tick();
 for(q=0;q<32;q=q+1)x[q]=64'hcafe000000000000+q;
 x[0]=0;x[1]=64'hfffffff0;x[2]=BASE+16'hfff0;
 x[10]=BASE+16'h4000;x[11]=argA;x[12]=BASE+16'h8000;x[13]=n;
 $readmemh(image,mem);
 cmdStart=commands;reqStart=requests;caseStart=cycles;
 execute(entry);
 actualDump=$test$plusargs("bad-tl")?{dump,".bad"}:dump;
 fd=$fopen(actualDump,"wb");if(fd==0)$fatal(1,"cannot open dump");
 for(q=0;q<16'hd000;q=q+1)$fwrite(fd,"%c",mem[q]);$fclose(fd);
 $display("CASE %0d %h %0d %0d %0d %0d",id,x[10],cycles-caseStart,commands-cmdStart,requests-reqStart,scalarSteps);
end endtask

initial begin
 commands=0;requests=0;responses=0;caseStart=0;
 for(j=0;j<8;j=j+1)family[j]=0;
 // RUN_CASES
 $display("PASS programs commands=%0d requests=%0d responses=%0d cycles=%0d",commands,requests,responses,cycles);
 $display("FAMILIES %0d %0d %0d %0d %0d %0d %0d %0d",family[0],family[1],family[2],family[3],family[4],family[5],family[6],family[7]);
 $finish;
end
endmodule
