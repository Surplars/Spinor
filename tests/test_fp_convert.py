#!/usr/bin/env python3
"""Same-width conversions versus independent SoftFloat and explicit anchors."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from reference_fp import Reference
from test_fp_lane import HEADER,check
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
def main():
 p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');p.add_argument('--lane',action='store_true');args=p.parse_args()
 assert not(args.mapped and args.lane)
 ref=Reference();rng=random.Random(0x9c0);rows=[];top='FloatingPointLane' if args.lane else 'FloatingPointConvert'
 header=HEADER.replace('FloatingPointLane dut',top+' dut').replace("64'h3ff0000000000001","64'h1")
 lines=[header];flushes=0
 def add(d,op,rm,a):
  legal=op in range(21,27) and (rm<=4 or op>=25)
  v,f=ref(op,d,rm,a) if legal else (0,0);i=len(rows)
  rows.append((d,op,rm,a,0,0,v,f,int(not legal)))
  lines.append(f"run(1'b{int(d)},{op},{rm},64'h{a:x},0,0,8'd{i%256},{rng.randrange(5)});")
 anchors=0
 for d in [False,True]:
  w=64 if d else 32;one=0x3ff0000000000000 if d else 0x3f800000;inf=0x7ff0000000000000 if d else 0x7f800000
  sign=1<<(w-1);nan=inf|(1<<(51 if d else 22));mask=(1<<w)-1
  for op,rm,a,v,f in [(21,0,nan,mask,16),(22,0,nan,sign-1,16),(22,0,one,1,0),
    (21,0,one|sign,0,16),(23,0,1,one,0),(24,0,mask,one|sign,0),(25,4,one+1,1,1)]:
   assert ref(op,d,rm,a)==(v,f),(d,op,ref(op,d,rm,a),(v,f));anchors+=1
  edges=[0,sign,1,sign|1,one-1,one,one+1,inf-1,inf,inf|sign,nan,inf|1,mask,mask-1,sign-1,sign+1]
  for k in [1,22,23,24,30,31,32,51,52,53,62,63]:
   if k<w:
    for delta in [-1,0,1]:edges.append(((1<<k)+delta)&mask)
  for op in range(21,27):
   for rm in range(5):
    for a in edges:add(d,op,rm,a)
    for _ in range(40):add(d,op,rm,rng.getrandbits(64))
   for rm in [5,6,7]:add(d,op,rm,one)
  for op in ([31] if args.lane else [0,31]):add(d,op,0,one)
 for op in range(21,27):
  for delay in list(range(80)) if not args.mapped else [0,1,3,8,20,40,63,75]:
   lines.append(f'cancel({op},{delay},0,0);');flushes+=1
  for atReply,reset in [(1,0),(0,1)]:lines.append(f'cancel({op},2,{atReply},{reset});');flushes+=1
 add(False,24,0,0xffffffff)
 lines.append('$display("PASS fp-convert vectors=%0d cancels=%0d cycles=%0d",n,cancels,cycles);$finish;end endmodule')
 name='fp-convert'+('-lane' if args.lane else '-mapped' if args.mapped else '-rtl');tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
 rtl=ROOT/(f'build/synth/{top}/mapped.v' if args.mapped else f'build/rtl/{top}.sv');files=[tb,rtl]
 if args.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v']
 with (OUT/(name+'.compile.log')).open('w') as log:
  subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb','-o',str(exe),*map(str,files)],stdout=log,stderr=log,check=True)
 run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 latency=check([s for s in run.stdout.splitlines() if s.startswith('F ')],rows)
 result=dict(status='PASS',vectors=len(rows),conversion_anchors=anchors,flush_reset_cases=flushes,latency=latency,
  rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(tb.read_bytes()).hexdigest())
 (OUT/(name+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print('PASS',name,len(rows),'vectors',flushes,'flush/reset')
if __name__=='__main__':main()
