module BitManipProof(input clock,reset,input [63:0] a,b,input [1:0] sew,input [5:0] op,
                    output mismatch,done);
reg [3:0] step=0;reg [63:0] heldA,heldB;reg [1:0] heldSew;reg [5:0] heldOp;
always @(posedge clock)begin
 if(reset)step<=0;
 else begin
  if(step<9)step<=step+1;
  if(step==0)begin heldA<=a;heldB<=b;heldSew<=sew;heldOp<=op;end
 end
end
wire [63:0] mask=64'hffffffffffffffff>>(64-(8<<heldSew));
wire [63:0] normA=heldA&mask,normB=heldB&mask;wire [63:0] result;
BitManipPipeline dut(.clock(clock),.io_in_a(normA),.io_in_b(normB),.io_in_sew(heldSew),.io_in_op(heldOp),.io_result(result));
wire [63:0] expected[3:0];
genvar s;
generate for(s=0;s<4;s=s+1)begin:g
 localparam W=8<<s;
 wire [W-1:0] x=heldA[W-1:0];wire [5:0] n=heldB[5:0]&(W-1),negative=(-n)&(W-1);
 reg [W-1:0] reverse,bytes,brev8,ref;reg [6:0] leading,trailing,pop;integer i;
 always @*begin
  reverse=0;bytes=0;brev8=0;leading=W;trailing=W;pop=0;ref=0;
  for(i=0;i<W;i=i+1)begin
   reverse[W-1-i]=x[i];brev8[(i/8)*8+7-i%8]=x[i];bytes[(W/8-1-i/8)*8+i%8]=x[i];
   if(x[i])leading=W-1-i;pop=pop+x[i];
  end
  for(i=W-1;i>=0;i=i-1)if(x[i])trailing=i;
  case(heldOp)
   30:ref=brev8;31:ref=reverse;32:ref=bytes;33:ref=leading;34:ref=trailing;35:ref=pop;
   36:ref=(x<<n)|(x>>negative);37:ref=(x>>n)|(x<<negative);
  endcase
 end
 assign expected[s]={{(64-W){1'b0}},ref};
end endgenerate
assign done=step>=5;
assign mismatch=done && heldOp>=30 && heldOp<=37 && ((result&mask)!=expected[heldSew]);
endmodule
