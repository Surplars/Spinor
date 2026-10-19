#!/usr/bin/env python3
"""Exhaustive binary16 widening and adversarial binary32 narrowing vs SoftFloat."""
import argparse,ctypes,hashlib,json,random,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m54/half-unit';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');a=p.parse_args()
    if a.mapped:OUT=ROOT/'build/m54/half-unit-mapped';OUT.mkdir(parents=True,exist_ok=True)
    lib=ctypes.CDLL(str(ROOT/'build/m54/reference/libhalf.so'));fn=lib.spinor_half_reference
    fn.argtypes=[ctypes.c_uint,ctypes.c_uint,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint)];fn.restype=ctypes.c_uint64
    fixtures=OUT/'vectors.txt';count=0;flags_count={};rng=random.Random(0x54f16)
    with fixtures.open('w') as f:
        def add(mode,value,rm,op=28,double=0,bad=False):
            nonlocal count
            flags=ctypes.c_uint();expected=fn(mode==6,rm,value,ctypes.byref(flags)) if not bad else 0
            f.write(f'{mode:x} {value:016x} {rm:x} {op:x} {double:x} {int(bad):x} {expected:016x} {flags.value:x}\n')
            count+=1;flags_count[str(flags.value)]=flags_count.get(str(flags.value),0)+1
        for x in range(65536):add(5,x,x%5)
        values=[0,0x80000000,1,0x007fffff,0x00800000,0x33800000,0x33000000,0x387fc000,0x38800000,
                0x3f800000,0x3f801000,0x3f803000,0x477fe000,0x477ff000,0x47800000,0x7f7fffff,
                0x7f800000,0xff800000,0x7f800001,0x7fc00000,0x7fffffff,0xff800001]
        values += [rng.getrandbits(32) for _ in range(4096)]
        for value in values:
            for rm in range(5):add(6,value,rm)
        for mode in [5,6]:
            for rm in [5,6,7]:add(mode,0x3f800001,rm,bad=True)
            add(mode,0x3f800001,0,double=1,bad=True);add(mode,0x3f800001,0,op=29,bad=True)
    tb=OUT/'tb.sv';tb.write_text(r'''
module tb;
reg clock=0,reset=1;reg [2:0] io_widthMode=0;reg io_flush=0,io_in_valid=0,io_out_ready=0;
wire io_in_ready,io_out_valid;reg [63:0] io_in_bits_a=0,io_in_bits_b=0,io_in_bits_c=0;
reg io_in_bits_double=0;reg [4:0] io_in_bits_op=0;reg [2:0] io_in_bits_rounding=0;reg [7:0] io_in_bits_tag=0;
wire [63:0] io_out_bits_data;wire [4:0] io_out_bits_flags;wire [7:0] io_out_bits_tag;wire io_out_bits_illegal;
FloatingPointConvertResize dut(.*);
task tick;begin #5;clock=1;#5;clock=0;#1;end endtask
integer fd,rc,mode,rm,op,d,bad,flags,count=0,waited,k,aborted=0;reg [63:0] value,expected,held;reg [4:0] held_flags;
initial begin
tick();tick();reset=0;tick();fd=$fopen("build/m54/half-unit/vectors.txt","r");if(!fd)$fatal(1,"fixture open");
while(!$feof(fd))begin
rc=$fscanf(fd,"%h %h %h %h %h %h %h %h\n",mode,value,rm,op,d,bad,expected,flags);
if(rc!=8)$fatal(1,"fixture parse");
if(!io_in_ready)$fatal(1,"not ready");
io_widthMode=mode;io_in_bits_a=value;io_in_bits_op=op;io_in_bits_rounding=rm;io_in_bits_double=d;io_in_bits_tag=count;
io_in_valid=1;tick();io_in_valid=0;waited=0;
while(!io_out_valid)begin tick();waited=waited+1;if(waited>100)$fatal(1,"timeout");end
if(io_out_bits_tag!==count[7:0] || io_out_bits_illegal!==bad[0])$fatal(1,"identity/illegal %0d",count);
if(!bad && (io_out_bits_data!==expected || io_out_bits_flags!==flags[4:0]))$fatal(1,"numeric %0d input=%h got=%h/%h expected=%h/%h",count,value,io_out_bits_data,io_out_bits_flags,expected,flags);
held=io_out_bits_data;held_flags=io_out_bits_flags;
repeat(count%3)begin tick();if(!io_out_valid || io_out_bits_data!==held || io_out_bits_flags!==held_flags)$fatal(1,"backpressure");end
io_out_ready=1;tick();io_out_ready=0;tick();count=count+1;
end
// Abort at every recode/round/reply phase, then require clean admission.
for(mode=5;mode<=6;mode=mode+1)for(k=0;k<22;k=k+1)begin
io_widthMode=mode;io_in_bits_a=64'h7f800001;io_in_bits_op=28;io_in_bits_rounding=0;io_in_bits_double=0;
io_in_valid=1;tick();io_in_valid=0;repeat(k)tick();io_flush=1;#1;if(io_out_valid)$fatal(1,"flush reply");tick();io_flush=0;
repeat(20)begin tick();if(io_out_valid)$fatal(1,"stale after flush");end
if(!io_in_ready)$fatal(1,"flush not idle");aborted=aborted+1;
end
$display("PASS half-unit vectors=%0d flush_phases=%0d",count,aborted);$finish;
end
endmodule
'''.replace('build/m54/half-unit/vectors.txt',str(fixtures.relative_to(ROOT))))
    binary=OUT/'run';rtl=ROOT/('build/m54/synth/FloatingPointConvertResize/mapped.v' if a.mapped else 'build/m54/rtl/FloatingPointConvertResize.sv');start=time.monotonic()
    extra=[ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'] if a.mapped else []
    for cmd,name in [([ROOT/'tools/oss-cad-suite/bin/iverilog','-g2012','-s','tb','-o',binary,rtl,tb,*extra],'compile.log'),([ROOT/'tools/oss-cad-suite/bin/vvp',binary],'run.log')]:
        with (OUT/name).open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=f,stderr=f,check=True,timeout=600)
    summary=(OUT/'run.log').read_text().strip();assert f'vectors={count}' in summary and 'flush_phases=44' in summary
    result=dict(status='PASS',mapped=a.mapped,vectors=count,exhaustive_half_inputs=65536,flush_phases=44,flags_histogram=flags_count,seconds=time.monotonic()-start,summary=summary,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/fp16_reference.c']},
        artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [fixtures,tb,rtl,binary,OUT/'compile.log',OUT/'run.log',ROOT/'build/m54/reference/libhalf.so']})
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(summary)
if __name__=='__main__':main()
