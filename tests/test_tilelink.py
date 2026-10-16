#!/usr/bin/env python3
"""A/D reservation protocol tests; includes held-A flush and same-cycle D."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
def main():
 p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');p.add_argument('--wrapper',action='store_true');args=p.parse_args();assert not(args.mapped and args.wrapper);rng=random.Random(0x9a0)
 lines=['''module tb;
reg clock=0,reset=1,io_flush=0,io_request_valid=0,io_response_ready=0;
reg [63:0] io_request_bits_address=0,io_request_bits_data=0;reg [2:0] io_request_bits_size=0;
reg io_request_bits_write=0,io_request_bits_irrevocable=0;reg [7:0] io_request_bits_mask=0;reg [79:0] io_request_bits_token=0;
wire io_request_ready,io_response_valid,io_busy;wire [63:0] io_response_bits_data;wire [79:0] io_response_bits_token;
wire io_response_bits_denied,io_response_bits_corrupt,io_response_bits_protocolError,io_response_bits_localError;
wire io_tl_a_valid;reg io_tl_a_ready=0;wire [2:0] io_tl_a_bits_opcode,io_tl_a_bits_param,io_tl_a_bits_size;
wire [3:0] io_tl_a_bits_source;wire [63:0] io_tl_a_bits_address,io_tl_a_bits_data;wire [7:0] io_tl_a_bits_mask;wire io_tl_a_bits_corrupt;
reg io_tl_d_valid=0;wire io_tl_d_ready;reg [2:0] io_tl_d_bits_opcode=0,io_tl_d_bits_param=0,io_tl_d_bits_size=0;
reg [3:0] io_tl_d_bits_source=0;reg io_tl_d_bits_sink=0,io_tl_d_bits_denied=0,io_tl_d_bits_corrupt=0;reg [63:0] io_tl_d_bits_data=0;
TileLinkReservation dut(.*);integer cycles=0,checks=0,apublished=0,drained=0;
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>100000)$fatal(1,"timeout");end endtask
task run(input [63:0] addr,data,retdata,input integer size,wr,mask,auth,localbad,aop,amask,
 input [63:0] adata,expected,input integer derror,denied,corrupt,kill,zeroDelay,input [79:0] token);
integer k;reg [130:0] saved;begin
 io_tl_a_ready=0;io_tl_d_valid=0;io_response_ready=0;io_flush=0;
 #1;if(!io_request_ready || io_busy)$fatal(1,"busy source reused");
 io_request_valid=1;io_request_bits_address=addr;io_request_bits_data=data;io_request_bits_size=size;
 io_request_bits_write=wr;io_request_bits_mask=mask;io_request_bits_irrevocable=auth;io_request_bits_token=token;
 tick();io_request_valid=0;
 if(localbad)begin
  if(io_tl_a_valid || !io_response_valid || !io_response_bits_localError)$fatal(1,"bad local request reached bus");
 end else begin
  repeat(3)begin
   #1;if(!io_tl_a_valid || io_tl_a_bits_opcode!==aop || io_tl_a_bits_address!==addr || io_tl_a_bits_size!==size ||
    io_tl_a_bits_mask!==amask || io_tl_a_bits_data!==adata || io_tl_a_bits_source!==0 || io_tl_a_bits_param!==0 || io_tl_a_bits_corrupt)
    $fatal(1,"A payload not stable/expected");
   if(io_request_ready || io_tl_d_ready)$fatal(1,"accepted before A");
   if(kill==1)io_flush=1;tick();io_flush=0;
  end
  io_tl_a_ready=1;io_tl_d_bits_opcode=wr?0:1;io_tl_d_bits_size=size;io_tl_d_bits_source=0;io_tl_d_bits_param=0;
  if(derror==1)io_tl_d_bits_source=3;
  if(derror==2)io_tl_d_bits_opcode=5;
  if(derror==3)io_tl_d_bits_size=size^1;
  if(derror==4)io_tl_d_bits_param=1;
  io_tl_d_bits_data=retdata;io_tl_d_bits_denied=denied;io_tl_d_bits_corrupt=corrupt;
  io_tl_d_valid=zeroDelay;
  if(zeroDelay)begin #1;if(!io_tl_d_ready)$fatal(1,"same cycle D blocked");end
  tick();apublished=apublished+1;io_tl_a_ready=0;
  if(!zeroDelay)begin
   repeat(3)begin
    if(io_request_ready || io_tl_a_valid)$fatal(1,"source reused before response");
    if(kill==2)io_flush=1;tick();io_flush=0;
   end
   io_tl_d_valid=1;if(kill==3)io_flush=1;
   #1;if(!io_tl_d_ready)$fatal(1,"D not drained");tick();io_flush=0;
  end
  io_tl_d_valid=0;drained=drained+1;
  if(kill>=1 && kill<=3)begin
   if(io_response_valid || io_busy)$fatal(1,"killed reply leaked");
  end else begin
   if(!io_response_valid || io_response_bits_data!==expected || io_response_bits_denied!==denied ||
    io_response_bits_corrupt!==corrupt || io_response_bits_protocolError!==(derror!=0) || io_response_bits_localError)
    $fatal(1,"wrong reply data=%h expected=%h",io_response_bits_data,expected);
  end
 end
 if(io_response_valid)begin
  if(io_response_bits_token!==token)$fatal(1,"wrong token");
  repeat(3)begin
   if(!io_response_valid || io_request_ready)$fatal(1,"reply unstable");tick();
  end
  if(kill==4)begin io_flush=1;tick();io_flush=0;end
  else begin io_response_ready=1;tick();io_response_ready=0;end
 end
 #1;if(io_busy || !io_request_ready)$fatal(1,"did not return idle");checks=checks+1;
end endtask
initial begin tick();tick();reset=0;tick();''']
 counts={'transactions':0,'local_rejects':0,'same_cycle_D':0,'flush_cases':0,'protocol_errors':0}
 for n in range(600):
  size=rng.randrange(4);wr=rng.randrange(2);length=1<<size;offset=rng.randrange(8//length)*length
  addr=0x80000000+rng.randrange(64)*8+offset;natural=(1<<length)-1;mask=rng.randrange(1,natural+1);auth=1
  if not wr:mask=natural
  localbad=n%17==0
  if localbad:
   which=n%5
   if which==0:size=4
   elif which==1:wr=1;auth=0
   elif which==2:wr=1;mask=0
   elif which==3:size=3;addr|=1
   else:size=0;wr=1;mask=2
  data=rng.getrandbits(64);retdata=rng.getrandbits(64);kill=n%5;zeroDelay=int(n%3==0 and kill not in [2,3])
  derror=n%5 if n%11==0 else 0;denied=int(n%13==0);corrupt=int(n%19==0)
  aop=(0 if mask==natural else 1) if wr else 4;amask=(mask if wr else natural)<<offset;adata=data<<(offset*8)&((1<<64)-1)
  expected=0 if wr else retdata>>(offset*8)&((1<<(length*8))-1)
  lines.append(f"run(64'h{addr:x},64'h{data:x},64'h{retdata:x},{size},{wr},{mask},{auth},{int(localbad)},{aop},{amask},64'h{adata:x},64'h{expected:x},{derror},{denied},{corrupt},{kill},{zeroDelay},80'h{(0x1234<<64)|n:x});")
  counts['transactions']+=1;counts['local_rejects']+=localbad;counts['same_cycle_D']+=zeroDelay and not localbad;counts['flush_cases']+=(kill!=0 and not localbad) or (kill==4 and localbad);counts['protocol_errors']+=derror!=0 and not localbad
 lines.append('$display("PASS tilelink checks=%0d A=%0d drainedD=%0d",checks,apublished,drained);$finish;end endmodule')
 if args.wrapper:
  from test_vector import HEADER
  declarations=HEADER.split('`TOP dut')[0].split('module tb;\n')[1].replace('io_','io_core_')
  declarations=declarations.replace('reg clock=0, reset=1, io_core_flush=0;','')
  declarations=declarations.replace('wire [4:0] io_core_vl;','wire [7:0] io_core_vl;wire [6:0] io_core_vstart;wire [1:0] io_core_vxrm;wire io_core_vxsat;wire [31:0] io_core_versions;wire [2:0] io_core_frm;wire [4:0] io_core_fflags;')
  lines=[s.replace('io_request','io_memoryRequest').replace('io_response','io_memoryResponse').replace('io_busy','io_memoryBusy').replace('io_flush','io_core_flush').replace('TileLinkReservation dut(.*);',declarations+'LishiVpuTileLinkReserved dut(.*);') for s in lines]
 name='tilelink-wrapper' if args.wrapper else 'tilelink-mapped' if args.mapped else 'tilelink-rtl';tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
 rtl=ROOT/('build/rtl/LishiVpuTileLinkReserved.sv' if args.wrapper else 'build/synth/TileLinkReservation/mapped.v' if args.mapped else 'build/rtl/TileLinkReservation.sv');files=[tb,rtl]
 if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v']
 with (OUT/(name+'.compile.log')).open('w') as log:
  subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb','-o',str(exe),*map(str,files)],stdout=log,stderr=log,check=True)
 run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 result=dict(status='PASS',coverage=counts,trace=run.stdout.strip(),rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest())
 (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
