module tb;
reg clock=0,reset=1;
reg io_readEnable=0,io_readCandidate=0,io_writeEnable=0,io_writeCandidate=0,io_commit=0;
reg [4:0] io_readAddress=0,io_writeAddress=0;
reg [127:0] io_writeData=0;
reg [15:0] io_writeMask=0;
reg [31:0] io_commitMask=0;
wire [31:0] io_versions;
wire [127:0] io_readData;
VersionedRegisterFileRam dut(.*);
integer fd,status,n=0;
initial begin
#5;clock=1;#5;clock=0;reset=0;
fd=$fopen("build/test/versioned-rf.stim","r");
while(!$feof(fd))begin
 status=$fscanf(fd,"%d %d %d %d %d %d %h %h %d %h\n",io_readEnable,io_readAddress,io_readCandidate,
  io_writeEnable,io_writeAddress,io_writeCandidate,io_writeMask,io_writeData,io_commit,io_commitMask);
 if(status!=10)$fatal(1,"bad stimulus");
 #5;clock=1;#5;
 $display("R %0d %032h %08h",n,io_readData,io_versions);
 clock=0;n=n+1;
end
$finish;end
endmodule
