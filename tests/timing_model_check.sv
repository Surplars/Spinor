`timescale 1ns/1fs
module tb;
import timing_reference::*;
reg C=0,CE=1,D=0,R=1;
wire Q;
FDRE dut(.*);
initial begin
 #1;C=1;#1;C=0;R=0;
 #2;enabled=1;D=1;
 #0.05;C=1; // 0.05 ns setup against the independently selected 0.10 ns requirement
 #0.01;D=0; // 0.01 ns hold against 0.03 ns
 #1;
 if(setup_violations!==1 || hold_violations!==1)$fatal(1,"reference checker did not detect deliberate violations");
 $display("PASS reference checker deliberate setup=1 hold=1");$finish;
end
endmodule
