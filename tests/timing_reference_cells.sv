// UNCALIBRATED WHAT-IF MODELS. Not AMD simulation libraries or ZU15EG speed files.
// Uniform link delay is an assumption; no placement, fanout, PVT or clock skew.
`timescale 1ns/1fs
`ifndef REF_LUT
`define REF_LUT 0.0
`define REF_LINK 0.0
`define REF_CARRY 0.0
`define REF_CQ 0.0
`define REF_SETUP 0.0
`define REF_HOLD 0.0
`define REF_RAM 0.0
`endif
package timing_reference;
  localparam real LUT_NS=`REF_LUT, LINK_NS=`REF_LINK, CARRY_NS=`REF_CARRY;
  localparam real CQ_NS=`REF_CQ, SETUP_NS=`REF_SETUP, HOLD_NS=`REF_HOLD, RAM_NS=`REF_RAM;
  bit enabled=0;
  integer setup_violations=0,hold_violations=0,ram_violations=0;
endpackage

// Mux-tree semantics preserve known outputs when unused LUT inputs are X.
// Direct INIT[index] would pessimistically turn those outputs into X.
module REF_LUT #(parameter integer N=1,parameter [(1<<N)-1:0] INIT=0)(input [N-1:0] I,output O);
wire [(1<<N)-1:0] level[0:N];
assign level[0]=INIT;
genvar l,j;
generate for(l=0;l<N;l=l+1)begin:layers
 for(j=0;j<(1<<(N-l-1));j=j+1)begin:bitmux
  assign level[l+1][j]=I[l]?level[l][2*j+1]:level[l][2*j];
 end
end endgenerate
assign #(timing_reference::LUT_NS+timing_reference::LINK_NS) O=level[N][0];
endmodule
module LUT1 #(parameter [1:0] INIT=0)(input I0,output O);
REF_LUT #(.N(1),.INIT(INIT)) lut(.I({I0}),.O(O));endmodule
module LUT2 #(parameter [3:0] INIT=0)(input I0,I1,output O);
REF_LUT #(.N(2),.INIT(INIT)) lut(.I({I1,I0}),.O(O));endmodule
module LUT3 #(parameter [7:0] INIT=0)(input I0,I1,I2,output O);
REF_LUT #(.N(3),.INIT(INIT)) lut(.I({I2,I1,I0}),.O(O));endmodule
module LUT4 #(parameter [15:0] INIT=0)(input I0,I1,I2,I3,output O);
REF_LUT #(.N(4),.INIT(INIT)) lut(.I({I3,I2,I1,I0}),.O(O));endmodule
module LUT5 #(parameter [31:0] INIT=0)(input I0,I1,I2,I3,I4,output O);
REF_LUT #(.N(5),.INIT(INIT)) lut(.I({I4,I3,I2,I1,I0}),.O(O));endmodule
module LUT6 #(parameter [63:0] INIT=0)(input I0,I1,I2,I3,I4,I5,output O);
REF_LUT #(.N(6),.INIT(INIT)) lut(.I({I5,I4,I3,I2,I1,I0}),.O(O));endmodule
module INV(input I,output O);
assign #(timing_reference::LUT_NS+timing_reference::LINK_NS) O=~I;endmodule
module CARRY4(input CI,CYINIT,input [3:0] DI,S,output [3:0] O,CO);
wire cin;wire [3:0] sd,dd;
assign #(timing_reference::LINK_NS) cin=CI|CYINIT;
assign #(timing_reference::LINK_NS) sd=S,dd=DI;
genvar b;
generate for(b=0;b<4;b=b+1)begin:bitslice
 wire carryIn;
 if(b==0)assign carryIn=cin;else assign carryIn=CO[b-1];
 assign #(timing_reference::CARRY_NS) CO[b]=sd[b]?carryIn:dd[b];
 assign #(timing_reference::CARRY_NS) O[b]=sd[b]^carryIn;
end endgenerate
endmodule

module FDRE #(parameter [0:0] INIT=0,parameter IS_C_INVERTED=0)(input C,CE,D,R,output reg Q=INIT);
import timing_reference::*;
wire clk=C^IS_C_INVERTED;
realtime lastD=-10000.0,lastCE=-10000.0,lastR=-10000.0,lastEdge=-10000.0;
bit capturing=0;
always @(D)begin
 if(enabled && capturing && $realtime-lastEdge < HOLD_NS)hold_violations=hold_violations+1;
 lastD=$realtime;
end
always @(CE)begin
 if(enabled && $realtime-lastEdge < HOLD_NS)hold_violations=hold_violations+1;
 lastCE=$realtime;
end
always @(R)begin
 if(enabled && $realtime-lastEdge < HOLD_NS)hold_violations=hold_violations+1;
 lastR=$realtime;
end
always @(posedge clk)begin
 if(enabled && ((!R && CE && $realtime-lastD < SETUP_NS) ||
     (!R && $realtime-lastCE < SETUP_NS) || $realtime-lastR < SETUP_NS))begin
   setup_violations=setup_violations+1;
   if(setup_violations<=8)$display("REF_SETUP %m t=%0.3f D_age=%0.3f CE_age=%0.3f",$realtime,$realtime-lastD,$realtime-lastCE);
 end
 lastEdge=$realtime;capturing=!R && CE;
 if(R)Q<=#(CQ_NS+LINK_NS)0;else if(CE)Q<=#(CQ_NS+LINK_NS)D;
end
endmodule

module RAM32M16 #(
 parameter [63:0] INIT_A=0,INIT_B=0,INIT_C=0,INIT_D=0,INIT_E=0,INIT_F=0,INIT_G=0,INIT_H=0,
 parameter IS_WCLK_INVERTED=0
)(output [1:0] DOA,DOB,DOC,DOD,DOE,DOF,DOG,DOH,
 input [4:0] ADDRA,ADDRB,ADDRC,ADDRD,ADDRE,ADDRF,ADDRG,ADDRH,
 input [1:0] DIA,DIB,DIC,DID,DIE,DIF,DIG,DIH,input WCLK,WE);
import timing_reference::*;
reg [63:0] ma=INIT_A,mb=INIT_B,mc=INIT_C,md=INIT_D,me=INIT_E,mf=INIT_F,mg=INIT_G,mh=INIT_H;
wire clk=WCLK^IS_WCLK_INVERTED;
assign #(RAM_NS+LINK_NS) DOA=ma[2*ADDRA+:2],DOB=mb[2*ADDRB+:2],DOC=mc[2*ADDRC+:2],DOD=md[2*ADDRD+:2],
 DOE=me[2*ADDRE+:2],DOF=mf[2*ADDRF+:2],DOG=mg[2*ADDRG+:2],DOH=mh[2*ADDRH+:2];
realtime lastWriteChange=-10000.0;
always @(DIA,DIB,DIC,DID,DIE,DIF,DIG,DIH,ADDRH,WE)lastWriteChange=$realtime;
always @(posedge clk)begin
 if(enabled && WE && $realtime-lastWriteChange < SETUP_NS)ram_violations=ram_violations+1;
 if(WE)begin
  ma[2*ADDRH+:2]<=#(CQ_NS)DIA;mb[2*ADDRH+:2]<=#(CQ_NS)DIB;mc[2*ADDRH+:2]<=#(CQ_NS)DIC;md[2*ADDRH+:2]<=#(CQ_NS)DID;
  me[2*ADDRH+:2]<=#(CQ_NS)DIE;mf[2*ADDRH+:2]<=#(CQ_NS)DIF;mg[2*ADDRH+:2]<=#(CQ_NS)DIG;mh[2*ADDRH+:2]<=#(CQ_NS)DIH;
 end
end
endmodule
