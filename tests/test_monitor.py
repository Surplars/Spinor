#!/usr/bin/env python3
"""Cycle reference for TL monitor: atomic snapshots, denied accesses and wrap."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/monitor/test';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--tiny',action='store_true');p.add_argument('--mapped',action='store_true');p.add_argument('--base',type=lambda x:int(x,0),default=0);p.add_argument('--rtl-dir',default='build/monitor/rtl');args=p.parse_args()
top='VpuMonitorTiny' if args.tiny else 'VpuMonitor';width=8 if args.tiny else 32;rng=random.Random(0x1881)
live=[0]*13;snap=live.copy();seq=0;valid=False;overflow=False;sticky=False;err=(0,0,0,0)
ss=sv=sc=0;se=(0,0,0,0);pending=None;reads=writes=denied=held=snaps=clears=wraps=0
header='''module tb;
reg clock=0,reset=1;
reg [12:0] io_signals_events=0;
reg io_signals_busy=0,io_signals_memoryOwned=0,io_signals_tlPending=0,io_signals_owned=0;
reg [63:0] io_signals_vtype=0;reg [31:0] io_signals_config=0;
reg io_signals_error=0;reg [15:0] io_signals_cause=0;
reg [63:0] io_signals_address=0;reg [79:0] io_signals_token=0;reg [7:0] io_signals_element=0;
reg io_mmio_a_valid=0;wire io_mmio_a_ready;reg [2:0] io_mmio_a_bits_opcode=0,io_mmio_a_bits_param=0,io_mmio_a_bits_size=0;
reg [3:0] io_mmio_a_bits_source=0;reg [63:0] io_mmio_a_bits_address=0,io_mmio_a_bits_data=0;
reg [7:0] io_mmio_a_bits_mask=0;reg io_mmio_a_bits_corrupt=0;
wire io_mmio_d_valid;reg io_mmio_d_ready=0;
wire [2:0] io_mmio_d_bits_opcode,io_mmio_d_bits_param,io_mmio_d_bits_size;
wire [3:0] io_mmio_d_bits_source;wire io_mmio_d_bits_sink,io_mmio_d_bits_denied,io_mmio_d_bits_corrupt;wire [63:0] io_mmio_d_bits_data;
TOP dut(.*);
task tick;begin #5;clock=1;#5;clock=0;end endtask
initial begin tick();tick();reset=0;
'''
lines=[header.replace('TOP',top)]
known=list(range(16))+list(range(32,45))+list(range(48,55))
for cycle in range(2600):
 events=rng.getrandbits(13)|1;busy=rng.randrange(2);mem=rng.randrange(2);tl=rng.randrange(2);owned=rng.randrange(2)
 vt=rng.getrandbits(64);config=rng.getrandbits(32);error=rng.random()<.04
 ei=(rng.getrandbits(16),rng.getrandbits(64),rng.getrandbits(80),rng.randrange(256))
 av=rng.random()<.8 and cycle<2500;dr=rng.random()<.45
 opcode=4;size=rng.randrange(4);addr=8*rng.choice(known)+(rng.randrange(8//(1<<size))*(1<<size));data=0;param=0;corrupt=0
 if rng.random()<.22:opcode=rng.choice([0,1]);addr=0x40;size=rng.choice([2,3]);data=1 if cycle<800 else rng.choice([1,1,2])
 mask=(((1<<(1<<size))-1)<<(addr&7))&255
 if rng.random()<.17:
  defect=rng.randrange(8)
  if defect==0:addr+=4096
  if defect==1:addr=0x88
  if defect==2:opcode=rng.choice([2,3,5])
  if defect==3:param=1
  if defect==4:corrupt=1
  if defect==5:mask^=1
  if defect==6:opcode=0;addr=0
  if defect==7:size=4
 source=rng.randrange(16)
 addr+=args.base
 if opcode in [0,1] and size==2:data |= rng.getrandbits(32)<<32
 status=int(busy)|(mem<<1)|(tl<<2)|(owned<<3)|(int(valid)<<4)|32|(int(overflow)<<6)|(int(sticky)<<7)
 table={0:0x4c495348,1:0x10000,2:0x3201,3:0xfffff,4:(1<<48)|(32<<32)|(64<<16)|128,5:(8<<32)|512,6:width,7:status,8:0,9:seq,
 10:err[0]|(err[3]<<16),11:err[1],12:err[2]&((1<<64)-1),13:err[2]>>64,14:vt,15:config,
 48:ss,49:sv,50:sc,51:se[0]|(se[3]<<16),52:se[1],53:se[2]&((1<<64)-1),54:se[2]>>64}
 table.update({32+i:x for i,x in enumerate(snap)})
 check=[f"io_mmio_a_ready !== 1'b{int(pending is None)}",f"io_mmio_d_valid !== 1'b{int(pending is not None)}"]
 if pending:
  op,sz,src,bad,value=pending
  check += [f"io_mmio_d_bits_opcode !== 3'd{op}",f"io_mmio_d_bits_size !== 3'd{sz}",f"io_mmio_d_bits_source !== 4'd{src}",f"io_mmio_d_bits_denied !== 1'b{int(bad)}",f"io_mmio_d_bits_data !== 64'h{value:x}","io_mmio_d_bits_corrupt !== 1'b0","io_mmio_d_bits_param !== 3'b0","io_mmio_d_bits_sink !== 1'b0"]
 lines += [f"io_signals_events=13'h{events:x};io_signals_busy={busy};io_signals_memoryOwned={mem};io_signals_tlPending={tl};io_signals_owned={owned};io_signals_vtype=64'h{vt:x};io_signals_config=32'h{config:x};io_signals_error={int(error)};io_signals_cause=16'h{ei[0]:x};io_signals_address=64'h{ei[1]:x};io_signals_token=80'h{ei[2]:x};io_signals_element={ei[3]};",
 f"io_mmio_a_valid={int(av)};io_mmio_d_ready={int(dr)};io_mmio_a_bits_opcode={opcode};io_mmio_a_bits_size={size};io_mmio_a_bits_source={source};io_mmio_a_bits_address=64'h{addr:x};io_mmio_a_bits_data=64'h{data:x};io_mmio_a_bits_mask=8'h{mask:x};io_mmio_a_bits_param={param};io_mmio_a_bits_corrupt={corrupt};#1;",
 f'if ({" || ".join(check)}) $fatal(1,"monitor mismatch cycle {cycle}");tick();']
 capture=clear=False
 if pending is None and av:
  word=(addr-args.base)//8;isread=opcode==4
  bus=addr//4096==args.base//4096 and size<=3 and param==0 and not corrupt and addr%min(1<<size,8)==0 and mask==((((1<<(1<<min(size,3)))-1)<<(addr&7))&255)
  control=data&0xffffffff if size==2 else data
  cw=opcode in [0,1] and word==8 and addr%8==0 and size>=2 and control<=2
  allowed=bus and ((isread and word in table) or cw)
  pending=(1 if opcode in [2,3,4] else 2 if opcode==5 else 0,size,source,not allowed,table.get(word,0) if allowed and isread else 0)
  reads+=int(isread);writes+=int(not isread);denied+=int(not allowed)
  capture=allowed and cw and control==1;clear=allowed and cw and control==2
 elif pending:
  held+=int(not dr)
  if dr:pending=None
 if capture:
  snap=live.copy();seq=(seq+1)&0xffffffff;valid=True;ss=status;sv=vt;sc=config;se=err;snaps+=1
 if error:sticky=True;err=ei
 for i in range(13):
  if events>>i&1:
   if live[i]==(1<<width)-1:overflow=True;wraps+=1
   live[i]=(live[i]+1)&((1<<width)-1)
 if clear:
  live=[0]*13;snap=[0]*13;valid=False;overflow=sticky=False;err=(0,0,0,0);ss=sv=sc=0;se=err;clears+=1
assert pending is None and reads>100 and snaps>10 and clears>0 and denied>10 and held>100
if args.tiny:assert wraps>0
lines+=['$display("PASS monitor 2600 cycles");$finish;end endmodule']
label=top+('-base' if args.base else '')+('-mapped' if args.mapped else '-rtl');tb=OUT/(label+'-tb.sv');tb.write_text('\n'.join(lines))
rtl=ROOT/(f'build/synth/{top}/mapped.v' if args.mapped else f'{args.rtl_dir}/{top}.sv')
files=[str(tb),str(rtl)]
if args.mapped:files += [str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'),str(ROOT/'tests/fp_mapped_global.sv')]
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb',*(['-s','glbl'] if args.mapped else []),'-o',str(OUT/label),*files],stdout=log,stderr=log,check=True)
run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
result=dict(status='PASS',cycles=2600,reads=reads,writes=writes,denied=denied,held_cycles=held,snapshots=snaps,clears=clears,wraps=wraps,
 sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VpuMonitor.scala']})
(OUT/(label+'-results.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
