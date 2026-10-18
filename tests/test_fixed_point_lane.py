#!/usr/bin/env python3
"""Exact integer oracle; no dependence on the RTL byte/shift decomposition."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def golden(a,b,sew,mode,rounding,carry=0):
 w=8<<sew;mask=(1<<w)-1;a&=mask;b&=mask
 signed=lambda x:x-(1<<w) if x>>(w-1) else x
 sat=False
 if mode<4:
  value=a-b-carry if mode&1 else a+b+carry
  if mode>=2:value=int(value<0 if mode&1 else value>mask)
 elif mode<8:
  x,y=(signed(a),signed(b)) if mode&1 else (a,b)
  value=x-y if mode&2 else x+y
  lo,hi=(-(1<<(w-1)),(1<<(w-1))-1) if mode&1 else (0,mask)
  sat=not lo<=value<=hi;value=min(hi,max(lo,value))
 else:
  if mode<12:
   x,y=(signed(a),signed(b)) if mode&1 else (a,b)
   value=x-y if mode&2 else x+y;distance=1
  else:value=signed(a) if mode==13 else a;distance=b&(w-1)
  # Mathematical floor quotient and positive remainder for signed inputs.
  quotient,remainder=divmod(value,1<<distance)
  half=1<<(distance-1) if distance else 0
  increment=(remainder>=half) if rounding==0 and distance else (remainder>half or remainder==half and quotient&1) if rounding==1 and distance else bool(remainder and not quotient&1) if rounding==3 else False
  value=quotient+int(increment)
 return value&mask,int(sat)
def main():
 p=argparse.ArgumentParser();p.add_argument('--compact',action='store_true');p.add_argument('--mapped',action='store_true');args=p.parse_args();assert not args.mapped or args.compact
 out=ROOT/'build/fixed-point-lane';out.mkdir(parents=True,exist_ok=True);label=('compact' if args.compact else 'full')+('-mapped' if args.mapped else '-rtl');rng=random.Random(0x370ace);rows=[]
 for sew in range(4):
  w=8<<sew;mask=(1<<w)-1
  for mode in range(14):
   rounds=range(4) if mode>=8 else [0]
   values=[0,1,2,3,mask,mask-1,1<<(w-1),(1<<(w-1))-1,(1<<(w-1))+1]
   pairs=[(x,y) for x in values for y in values]
   if args.compact:pairs=pairs[::20]+[(mask,1),(1<<(w-1),1<<(w-1))]
   else:pairs += [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(60)]
   if mode>=12:pairs += [(x,y) for x in values[:(2 if args.compact else 9)] for y in ([0,1,w-1,w,w+1] if args.compact else range(2*w))]
   if not args.compact and sew==0 and mode<12:pairs += [(x,y) for x in range(256) for y in [0,1,127,128,254,255]]
   for rounding in rounds:
    for a,b in pairs:
     for carry in ([0,1] if mode<4 else [0]):
      expect,sat=golden(a,b,sew,mode,rounding,carry);rows.append((a,b,sew,mode,rounding,carry,expect,sat,rng.randrange(4),-1))
 # Cancel at every state boundary, including completion with ready asserted.
 for mode in range(14):
  for delay in range(0,4 if args.compact else 25):
   rows.append(((1<<64)-1,1,3,mode,1,0,0,0,0,delay))
  rows.append(((1<<64)-1,1,3,mode,1,0,0,0,0,99))
 stimulus=out/(label+'.stim');stimulus.write_text(''.join(f'{a:x} {b:x} {s} {m} {r} {c} {v:x} {sat} {stall} {kill}\n' for a,b,s,m,r,c,v,sat,stall,kill in rows))
 tb=out/(label+'-tb.sv');tb.write_text(r'''
module tb;
reg clock=0,reset=1,io_flush=0,io_in_valid=0,io_out_ready=0;
reg [63:0] io_in_bits_a=0,io_in_bits_b=0;
reg [1:0] io_in_bits_sew=0,io_in_bits_rounding=0;
reg [3:0] io_in_bits_mode=0;
reg io_in_bits_carry=0;
reg [7:0] io_in_bits_tag=0;
wire io_in_ready,io_out_valid,io_out_bits_saturated;
wire [63:0] io_out_bits_data;wire [7:0] io_out_bits_tag;
FixedPointLane dut(.*);
integer cycles=0,fd,n,count=0,stall,kill,i,age;reg [63:0] expected;reg sat;integer s,m,r,c;
task tick;begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>100000000)$fatal(1,"timeout");end endtask
initial begin tick();tick();reset=0;tick();fd=$fopen("STIMULUS","r");
while(!$feof(fd)) begin
 n=$fscanf(fd,"%h %h %d %d %d %d %h %b %d %d\n",io_in_bits_a,io_in_bits_b,s,m,r,c,expected,sat,stall,kill);
 if(n==10)begin
 io_in_bits_sew=s;io_in_bits_mode=m;io_in_bits_rounding=r;io_in_bits_carry=c;io_in_bits_tag=count;io_in_valid=1;
 #1;if(!io_in_ready)$fatal(1,"not ready");tick();io_in_valid=0;age=0;
 if(kill>=0 && kill!=99)repeat(kill)tick();
 else while(!io_out_valid)begin tick();age=age+1;if(age>40)$fatal(1,"late response");end
 if(kill>=0)begin
  io_out_ready=1;io_flush=1;#1;if(io_out_valid || io_in_ready)$fatal(1,"flush handshake");tick();io_flush=0;io_out_ready=0;
  repeat(4)begin tick();if(io_out_valid)$fatal(1,"stale after flush");end
 end else begin
  repeat(stall+1)begin
   if(!io_out_valid || io_out_bits_data!==expected || io_out_bits_saturated!==sat || io_out_bits_tag!==(count&255))
    $fatal(1,"case=%0d mode=%0d sew=%0d rm=%0d a=%h b=%h got=%h/%b want=%h/%b",count,m,s,r,io_in_bits_a,io_in_bits_b,io_out_bits_data,io_out_bits_saturated,expected,sat);
   tick();
  end
  io_out_ready=1;tick();io_out_ready=0;
 end
 count=count+1;
 end
end
$display("PASS fixed-point-lane cases=%0d cycles=%0d",count,cycles);$finish;end
endmodule
'''.replace('STIMULUS',str(stimulus)))
 rtl=ROOT/('build/synth/FixedPointLane/mapped.v' if args.mapped else 'build/rtl/FixedPointLane.sv');files=[tb,rtl]
 if args.mapped:files.append(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v')
 with (out/(label+'-compile.log')).open('w') as f:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-o',str(out/label),*map(str,files)],stdout=f,stderr=f,check=True)
 run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(out/label)],capture_output=True,text=True);(out/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
 result=dict(status='PASS',cases=len(rows),modes=14,sews=4,rounding_modes=4,flush_cases=sum(x[-1]>=0 for x in rows),summary=run.stdout.strip(),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,stimulus,Path(__file__).resolve()]})
 (out/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
