#!/usr/bin/env python3
"""FP32/FP64 bit/flag differential against pinned SoftFloat, not host floats."""
import argparse,hashlib,json
from pathlib import Path
import random
import subprocess
from reference_fp import Reference

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
HEADER=r'''
module tb;
reg clock=0,reset=1,io_flush=0,io_in_valid=0,io_out_ready=0;
reg [63:0] io_in_bits_a=0,io_in_bits_b=0,io_in_bits_c=0;
reg io_in_bits_double=0;
reg [4:0] io_in_bits_op=0;
reg [2:0] io_in_bits_rounding=0;
reg [7:0] io_in_bits_tag=0;
wire io_in_ready,io_out_valid,io_out_bits_illegal;
wire [63:0] io_out_bits_data;
wire [4:0] io_out_bits_flags;
wire [7:0] io_out_bits_tag;
FloatingPointLane dut(.*);
integer cycles=0,n=0,stalls=0,cancels=0;
task tick;
begin #5;clock=1;#5;clock=0;cycles=cycles+1;if(cycles>2000000)$fatal(1,"timeout");end
endtask
task offer(input bit d,input integer op,rm,input [63:0] a,b,c,input [7:0] tag);
begin
 if(!io_in_ready)$fatal(1,"FP lane unavailable");
 io_in_bits_double=d;io_in_bits_op=op;io_in_bits_rounding=rm;
 io_in_bits_a=a;io_in_bits_b=b;io_in_bits_c=c;io_in_bits_tag=tag;io_in_valid=1;
 tick();io_in_valid=0;
end
endtask
task run(input bit d,input integer op,rm,input [63:0] a,b,c,input [7:0] tag,input integer stall);
reg [63:0] saved;reg [4:0] flags;reg [7:0] token;reg illegal;integer start;
begin
 start=cycles;offer(d,op,rm,a,b,c,tag);
 while(!io_out_valid)begin if(io_in_ready)$fatal(1,"lost FP owner");tick();end
 saved=io_out_bits_data;flags=io_out_bits_flags;token=io_out_bits_tag;illegal=io_out_bits_illegal;
 repeat(stall)begin
  // A second offered request must not alter the held response or be accepted.
  io_in_valid=1;io_in_bits_a=~a;io_in_bits_tag=~tag;
  if(io_in_ready)$fatal(1,"FP capacity exceeded");tick();
  if(!io_out_valid || io_out_bits_data !== saved || io_out_bits_flags !== flags ||
    io_out_bits_tag !== token || io_out_bits_illegal !== illegal)$fatal(1,"unstable FP result");
  stalls=stalls+1;
 end
 io_in_valid=0;
 $display("F %0d %016h %02h %02h %0d %0d",n,saved,flags,token,illegal,cycles-start-stall);
 io_out_ready=1;tick();io_out_ready=0;n=n+1;
end
endtask
task cancel(input integer op,delayCycles,input bit atReply,doReset);
begin
 offer(1'b1,op,0,64'h3ff0000000000001,64'h4008000000000000,64'hbff0000000000000,8'hcd);
 if(atReply)begin while(!io_out_valid)tick();end else repeat(delayCycles)tick();
 if(doReset)reset=1;else io_flush=1;
 #1;if(!doReset && (io_in_ready || io_out_valid))$fatal(1,"FP flush handshake");
 tick();reset=0;io_flush=0;
 repeat(400)begin tick();if(io_out_valid)$fatal(1,"stale FP reply");end
 if(!io_in_ready)$fatal(1,"FP did not recover");cancels=cancels+1;
end
endtask
initial begin tick();tick();reset=0;tick();
'''

def check(trace,rows):
    assert len(trace)==len(rows),(len(trace),len(rows))
    latencies={}
    for i,(line,row) in enumerate(zip(trace,rows,strict=True)):
        _,n,data,flags,tag,illegal,lat=line.split()
        d,op,rm,a,b,c,expected,ef,ei=row
        assert int(n)==i
        actual=(int(data,16),int(flags,16),int(tag,16),int(illegal))
        assert actual==(expected,ef,i%256,ei),(i,'FP numerical mismatch',d,op,rm,hex(a),hex(b),hex(c),actual,(expected,ef,i%256,ei))
        key=f'{"FP64" if d else "FP32"}_op{op}'+('_illegal' if ei else '')
        latencies.setdefault(key,set()).add(int(lat))
    return {k:sorted(v) for k,v in latencies.items()}

def main():
    p=argparse.ArgumentParser();p.add_argument("--resize-native",action="store_true");p.add_argument("--widen-native",action="store_true");p.add_argument("--smoke",action="store_true");p.add_argument("--mapped",action="store_true");args=p.parse_args();assert not args.mapped or args.smoke
    OUT.mkdir(parents=True,exist_ok=True)
    ref=Reference();rng=random.Random(0x3f15e62);rows=[];lines=[HEADER.replace("repeat(400)","repeat(100)") if args.smoke else HEADER]
    if args.widen_native:
        lines[0]=lines[0].replace("FloatingPointLane dut", "reg [1:0] narrowOperands=0;FloatingPointLaneWiden dut")
    if args.resize_native:
        lines[0]=lines[0].replace("FloatingPointLane dut", "reg [1:0] narrowOperands=0;reg [2:0] conversionWidths=0;FloatingPointLaneResize dut")
    def add(d,op,rm,a,b=0,c=0):
        legal=op<=20 and rm<=4
        value,flags=ref(op,d,rm,a,b,c) if legal else (0,0)
        i=len(rows);rows.append((d,op,rm,a,b,c,value,flags,int(not legal)))
        lines.append(f"run(1'b{int(d)},{op},{rm},64'h{a:x},64'h{b:x},64'h{c:x},8'd{i%256},{rng.randrange(6)});")
    for d in [False,True]:
        one=0x3ff0000000000000 if d else 0x3f800000
        inf=0x7ff0000000000000 if d else 0x7f800000
        sign=1<<(63 if d else 31);quiet=1<<(51 if d else 22)
        tiny=0x0010000000000000 if d else 0x00800000
        boundary=[0,sign,1,sign|1,tiny-1,tiny,tiny+1,one,one-1,one+1,one|sign,
                  inf-1,inf,inf|sign,inf|quiet,inf|1,inf|quiet|123,(inf|1)|sign]
        for op in range(21):
            for rm in ([0] if args.smoke else range(5)):
                for j,a in enumerate(boundary[::3] if args.smoke else boundary):
                    add(d,op,rm,a,boundary[(j*7+op)%len(boundary)],boundary[(j*5+rm)%len(boundary)])
                for _ in range(1 if args.smoke else 14):add(d,op,rm,rng.getrandbits(64),rng.getrandbits(64),rng.getrandbits(64))
        for rm in range(5):
            add(d,5,rm,one+1,one-2,one|sign)
            add(d,0,rm,1,tiny-1) # exact subnormal -> normal boundary
            add(d,0,rm,one,0x3ca0000000000000 if d else 0x33800000)
            for op in [0,2,3,4,5]:add(d,op,rm,sign,one,sign)
        for rm in [5,6,7]:add(d,0,rm,one,one)
        for op in [30,31]:add(d,op,0,one,one)
    cancels=0
    for op in ([0,5] if args.smoke else [0,2,5,3,4]):
        for delay in ([0,1,2,3,*range(25,33)] if args.smoke else list(range(33))+[40,60,100,180,250,280]):
            lines.append(f"cancel({op},{delay},0,0);");cancels+=1
        lines.append(f"cancel({op},0,1,0);")
        lines.append(f"cancel({op},2,0,1);");cancels+=2
    add(False,0,0,0x3f800000,0x3f800000)
    lines.append('$display("PASS fp-lane vectors=%0d stalls=%0d cancels=%0d cycles=%0d",n,stalls,cancels,cycles);$finish;end endmodule\n')
    name='fp-lane-mapped' if args.mapped else 'fp-lane-smoke' if args.smoke else 'fp-lane'
    if args.widen_native:name=name.replace('fp-lane','fp-native')
    if args.resize_native:name=name.replace('fp-lane','fp-resize-native')
    tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
    rtl=ROOT/('build/synth/FloatingPointLane/mapped.v' if args.mapped else 'build/rtl/FloatingPointLane.sv')
    if args.widen_native:rtl=ROOT/('build/synth/FloatingPointLaneWiden/mapped.v' if args.mapped else 'build/rtl/FloatingPointLaneWiden.sv')
    if args.resize_native:rtl=ROOT/('build/synth/FloatingPointLaneResize/mapped.v' if args.mapped else 'build/rtl/FloatingPointLaneResize.sv')
    files=[str(tb),str(rtl)]
    if args.mapped:files += [str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'),str(ROOT/'third_party/xilinx-unisim/DSP48E2.v'),str(ROOT/'tests/fp_mapped_global.sv')]
    with (OUT/(name+'.compile.log')).open('w') as log:
        subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',*(['-s','glbl'] if args.mapped else []),'-o',str(exe),*files],stdout=log,stderr=log,check=True)
    run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True,cwd=ROOT,check=True)
    (OUT/(name+'.log')).write_text(run.stdout+run.stderr)
    trace=[s for s in run.stdout.splitlines() if s.startswith('F ')]
    latency=check(trace,rows)
    bad=trace.copy();tokens=bad[0].split();tokens[2]=f'{int(tokens[2],16)^1:x}';bad[0]=' '.join(tokens)
    try:check(bad,rows)
    except AssertionError:rejected=True
    else:raise AssertionError('FP oracle accepted corrupt data')
    result={'vectors':len(rows),'known_answer_anchors':ref.anchors,'flush_reset_cases':cancels,'rtl_or_netlist_sha256':hashlib.sha256(rtl.read_bytes()).hexdigest(),'testbench_sha256':hashlib.sha256(tb.read_bytes()).hexdigest(),
            'precision':['FP32','FP64'],'rounding_modes':[0,1,2,3,4],
            'corrupt_result_rejected':rejected,'observed_latency_cycles':latency,
            'status':'PASS','test_summary':next(s for s in run.stdout.splitlines() if s.startswith('PASS fp-lane'))}
    (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
