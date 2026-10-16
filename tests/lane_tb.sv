module tb;
  reg clock=0, reset=1, io_flush=0, io_in_valid=0, io_out_ready=0;
  reg [63:0] io_in_bits_a=0,io_in_bits_b=0;
  reg [1:0] io_in_bits_sew=0;
  reg [4:0] io_in_bits_op=0;
  reg io_in_bits_select=0;
  reg [7:0] io_in_bits_tag=0;
  wire io_in_ready,io_out_valid;
  wire [63:0] io_out_bits_data;
  wire [7:0] io_out_bits_tag;
  `TOP dut(.*);
  integer f,n,status;
  initial begin
    #5;clock=1;#5;clock=0;#5;clock=1;#5;clock=0;reset=0;
    f=$fopen("build/test/lane.stim","r");
    n=0;
    while (!$feof(f)) begin
      status=$fscanf(f,"%d %d %d %h %h %d %d %d %d\n",io_in_valid,io_out_ready,io_flush,
        io_in_bits_a,io_in_bits_b,io_in_bits_sew,io_in_bits_op,io_in_bits_select,io_in_bits_tag);
      if(status!=9) $fatal(1,"bad stimulus");
      #5;
      $display("T %0d %0d %0d %016h %0d",n,io_in_ready,io_out_valid,io_out_bits_data,io_out_bits_tag);
      clock=1;#5;clock=0;n=n+1;
    end
    $finish;
  end
endmodule
