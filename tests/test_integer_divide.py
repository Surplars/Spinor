#!/usr/bin/env python3
"""Arbitrary precision signed/unsigned division oracle; flush and held-response checks."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
def main():
 p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
 rng=random.Random(0x7a15);OUT.mkdir(parents=True,exist_ok=True);rows=[]
 tb=['''module tb;
reg clock=0,reset=1,io_flush=0,io_in_valid=0,io_out_ready=0;
reg [63:0] io_in_bits_a=0,io_in_bits_b=0;reg [1:0] io_in_bits_sew=0;
reg [4:0] io_in_bits_op=0;reg io_in_bits_select=0;reg [7:0] io_in_bits_tag=0;
wire io_in_ready,io_out_valid;wire [63:0] io_out_bits_data;wire [7:0] io_out_bits_tag;
IntegerDivide dut(.*);integer cycles=0,checks=0,kills=0;
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>2000000)$fatal(1,"timeout");end endtask
task run(input integer sew,op,input [63:0] a,b,expected,input integer delayCycles,kill);
reg [63:0] held;integer start,n;begin
 if(!io_in_ready)$fatal(1,"not idle");
 io_in_bits_sew=sew;io_in_bits_op=op;io_in_bits_a=a;io_in_bits_b=b;
 io_in_bits_tag=checks%256;io_in_valid=1;tick();io_in_valid=0;start=cycles;
 if(kill)begin
  repeat(delayCycles)tick();io_flush=1;#1;
  if(io_out_valid || io_in_ready)$fatal(1,"flush handshake");tick();io_flush=0;
  repeat(275)begin tick();if(io_out_valid)$fatal(1,"stale result");end
  if(!io_in_ready)$fatal(1,"flush recovery");kills=kills+1;
 end else begin
  while(!io_out_valid)begin tick();if(io_in_ready)$fatal(1,"lost request");end
  if(io_out_bits_data !== expected || io_out_bits_tag !== checks%256)
   $fatal(1,"divide mismatch sew=%d op=%d a=%h b=%h got=%h expected=%h",sew,op,a,b,io_out_bits_data,expected);
  if(cycles-start!=(4*(8<<sew)+8))$fatal(1,"divider latency changed");
  held=io_out_bits_data;
  repeat(delayCycles)begin
   io_in_valid=1;io_in_bits_a=~a;io_in_bits_b=~b;
   if(io_in_ready)$fatal(1,"over-accept");tick();
   if(!io_out_valid || io_out_bits_data !== held || io_out_bits_tag !== checks%256)$fatal(1,"unstable response");
  end
  io_in_valid=0;io_out_ready=1;tick();io_out_ready=0;checks=checks+1;
 end
end endtask
initial begin tick();tick();reset=0;tick();''']
 def add(sew,op,a,b,kill=0,delay=None):
  w=8<<sew;m=(1<<w)-1;x=a&m;y=b&m
  if op in [22,24] and x>>(w-1):x-=1<<w
  if op in [22,24] and y>>(w-1):y-=1<<w
  if y==0:q=-1;rem=x
  else:
   q=abs(x)//abs(y)
   if (x<0)!=(y<0):q=-q
   rem=x-q*y
  expected=(q if op in [21,22] else rem)&m
  tb.append(f"run({sew},{op},64'h{a:016x},64'h{b:016x},64'h{expected:016x},{rng.randrange(6) if delay is None else delay},{kill});")
  if not kill:rows.append((sew,op))
 for sew in range(4):
  w=8<<sew;m=(1<<w)-1;edge=[0,1,2,m,m-1,1<<(w-1),(1<<(w-1))-1,1<<(w//2)]
  for op in [21,22,23,24]:
   for a in edge:
    for b in edge:add(sew,op,a,b)
   for _ in range(100):add(sew,op,rng.getrandbits(64),rng.getrandbits(64))
 for delay in range(270):
  add(3,22,0x8000000000000001,0xfffffffffffffffd,1,delay)
  add(0,24,0x80,0xff)
 tb.append('$display("PASS divider checks=%0d flushes=%0d cycles=%0d",checks,kills,cycles);$finish;end endmodule')
 path=OUT/'integer-divide-tb.sv';path.write_text('\n'.join(tb));name='integer-divide'+('-mapped' if args.mapped else '-rtl')
 files=[path,ROOT/'build/synth/IntegerDivide/mapped.v' if args.mapped else ROOT/'build/rtl/IntegerDivide.sv']
 if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv']
 with (OUT/(name+'.compile.log')).open('w') as log:
  subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',*(['-s','glbl'] if args.mapped else []),'-o',str(OUT/name),*map(str,files)],stdout=log,stderr=log,check=True)
 run=subprocess.run([str(BIN/'vvp'),str(OUT/name)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 result=dict(rtl_or_netlist_sha256=hashlib.sha256(files[1].read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),status='PASS',checks=len(rows),flushes=270,model=name,trace=run.stdout.strip())
 (OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
