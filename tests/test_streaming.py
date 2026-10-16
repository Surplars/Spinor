#!/usr/bin/env python3
"""Check overlapped integer issue, aliasing, flush, drain, and physical RAM safety."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test';BIN=ROOT/'tools/oss-cad-suite/bin'
def main():
 p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');p.add_argument('--top',choices=['RamVectorFp','RamVectorFp16'],default='RamVectorFp');a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 h=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;')
 h=h.replace('input [4:0] expectedVl','input [7:0] expectedVl')
 h=h.replace('reg [31:0] saved;', 'reg [31:0] saved,oldVersions;')
 h=h.replace('io_command_bits_instruction=inst;io_command_bits_scalar=scalar;', 'oldVersions=io_versions;io_command_bits_instruction=inst;io_command_bits_scalar=scalar;')
 h=h.replace('while(!io_completion_valid) tick();','while(!io_completion_valid)begin tick();if(io_versions!==oldVersions)$fatal(1,"early map commit");end ',1)
 h=h.replace('repeat(stall) begin','repeat(stall) begin\nif(io_versions!==oldVersions)$fatal(1,"commit under backpressure");')
 monitor='''
integer max_inflight=0,overlap_rw=0;
`ifndef MAPPED
always @(posedge clock) if(!reset && !io_flush)begin
 if(dut.outstanding>max_inflight)max_inflight=dut.outstanding;
 if(dut.rf.io_readEnable && dut.rf.io_writeEnable)begin
  overlap_rw=overlap_rw+1;
  if(dut.rf.io_readAddress===dut.rf.io_writeAddress &&
     dut.rf.io_readCandidate===dut.rf.io_writeCandidate)$fatal(1,"same physical RAM row collision");
 end
 if(io_completion_valid && dut.outstanding!==0)$fatal(1,"completion before drain");
end
`endif
'''
 h=h.replace('initial begin',monitor+'initial begin',1)
 rng=random.Random(0x815);regs=[rng.getrandbits(128) for _ in range(32)];lines=[h];versions=0;commands=0
 def ctx(r,write=False):
  for k in range(2):
   v=(regs[r]>>(64*k))&((1<<64)-1);lines.append(f"ctx({2*r+k},1'b{int(write)},64'h{v:x},64'h{v:x});")
 def cmd(inst,vl,t,scalar=0,result=0,wr=0,stall=0):
  nonlocal commands
  lines.append(f"command(32'h{inst:x},64'h{scalar:x},0,{vl},{commands},0,{result},{wr},{stall},{vl},64'h{t:x});");commands+=1
 def operation(sew,lmul,vl,form,masked,prestart=0):
  nonlocal versions
  w=8<<sew;n=1<<lmul;t=(sew<<3)|lmul
  cmd((t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,vl,t,result=vl,wr=1)
  if prestart:cmd((8<<20)|(1<<15)|(1<<12)|0x73,vl,t,scalar=prestart)
  inst=(int(not masked)<<25)|(8<<20)|(16<<15)|(form<<12)|(8<<7)|0x57
  group=sum(regs[8+j]<<(128*j) for j in range(n));source=sum(regs[16+j]<<(128*j) for j in range(n))
  for e in range(prestart,vl):
   if masked and not (regs[0]>>e&1):continue
   m=(1<<w)-1;x=group>>(e*w)&m;y=source>>(e*w)&m if form==0 else 3
   group=(group&~(m<<(e*w)))|(((x+y)&m)<<(e*w))
  if vl>prestart:versions^=((1<<n)-1)<<8
  cmd(inst,vl,t,scalar=3,stall=5)
  for j in range(n):regs[8+j]=group>>(128*j)&((1<<128)-1);ctx(8+j)
  lines.append(f'if(io_versions!==32\'h{versions:x})$fatal(1,"bad map");')
 for r in range(32):ctx(r,True)
 # Adjacent byte-enabled returns with destination/source aliases across SEWs.
 for sew in range(4):
  for lmul in [0,3]:
   for form in [0,4]:operation(sew,lmul,1024//(8<<sew) if lmul==3 else 128//(8<<sew),form,True,1)
 # Sweep flush across front end, overlapping requests, retirement, and held completion.
 t=3;vl=128;cmd((t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,vl,t,result=vl,wr=1)
 inst=(1<<25)|(8<<20)|(16<<15)|(8<<7)|0x57
 delays=[0,15,24,30,40,60,80,100,200,400,700,800] if a.mapped else list(range(96))+[100,200,400,700,800]
 for delay in delays:
  lines.append(f"cancel(32'h{inst:x},{delay},0);")
  lines.append(f'if(io_versions!==32\'h{versions:x})$fatal(1,"flush committed");')
  for r in range(8,16):ctx(r)
  operation(0,3,128,0,False)
 lines.append(f"cancel(32'h{inst:x},0,1);")
 for r in range(8,16):ctx(r)
 lines.append('''
`ifndef MAPPED
if(max_inflight<2 || overlap_rw==0)$fatal(1,"streaming not exercised");
`endif
$display("PASS streaming commands=%0d max_inflight=%0d overlap_rw=%0d",cmds,max_inflight,overlap_rw);$finish;end endmodule''')
 name=('streaming16' if a.top.endswith('16') else 'streaming')+('-mapped' if a.mapped else '-rtl');tb=OUT/(name+'-tb.sv');tb.write_text('\n'.join(lines));exe=OUT/name
 rtl=ROOT/(f'build/synth/{a.top}/mapped.v' if a.mapped else f'build/rtl/{a.top}.sv');files=[tb,rtl]
 if a.mapped:files += [ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v',ROOT/'third_party/xilinx-unisim/DSP48E2.v',ROOT/'tests/fp_mapped_global.sv']
 with (OUT/(name+'.compile.log')).open('w') as log:
  subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={a.top}',*(['-DMAPPED','-s','glbl'] if a.mapped else []),'-o',str(exe),*map(str,files)],stdout=log,stderr=log,check=True)
 run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 result=dict(status='PASS',commands=commands,flushes=len(delays)+1,mapped=a.mapped,
  rtl_or_netlist_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest(),testbench_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),trace=run.stdout.strip())
 (OUT/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
