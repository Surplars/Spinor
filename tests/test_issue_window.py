#!/usr/bin/env python3
"""Independent ordered-list hazard oracle and variable-latency execution model."""
import argparse,hashlib,json,random,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/issue-window';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin';rng=random.Random(0x118001)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');args=p.parse_args()
q=[];held=None;head=tail=0;drain=False;ack_at=0;serial=0;pending={};stats=dict(dispatched=0,issued=0,retired=0,flushes=0,faults=0,out_of_order_issue=0,out_of_order_complete=0,held_stalls=0,max_occupancy=0,max_executing=0)
lines=['''module tb;
reg clock=0,reset=1,io_flush=0,io_flushAck=0;
reg io_command_valid=0;wire io_command_ready;
reg [31:0] io_command_bits_reads=0,io_command_bits_writes=0;
reg [1:0] io_command_bits_unit=0;reg io_command_bits_barrier=0;
reg [127:0] io_command_bits_payload=0;reg [7:0] io_command_bits_tag=0;
reg [3:0] io_unitReady=0;wire io_issue_valid;reg io_issue_ready=0;
wire [2:0] io_issue_bits_slot;wire [1:0] io_issue_bits_unit;wire [127:0] io_issue_bits_payload;
reg io_complete_valid=0;reg [2:0] io_complete_bits_slot=0;reg io_complete_bits_fault=0;
wire io_retire_valid;reg io_retire_ready=0;wire [2:0] io_retire_bits_slot;
wire [7:0] io_retire_bits_tag;wire io_retire_bits_fault,io_draining;wire [3:0] io_occupancy;
VectorIssueWindow dut(.*);
task tick;begin #5;clock=1;#5;clock=0;end endtask
initial begin tick();tick();reset=0;
''']
for cycle in range(10000):
 flush=(rng.random()<.008) if cycle<9500 else False
 ack=drain and cycle>=ack_at
 active=not drain and not flush
 fault_pending=any(x['done'] and x['fault'] for x in q)
 offer=rng.random()<.85 and cycle<9500
 read=sum(1<<r for r in set(rng.sample(range(32),rng.randrange(4))))
 write=(1<<rng.randrange(32)) if rng.random()<.9 else 0
 cmd=dict(slot=tail,reads=read,writes=write,unit=rng.randrange(4),barrier=rng.random()<.08,payload=serial+1,tag=serial%256,issued=False,done=False,fault=False)
 unit_ready=sum(1<<u for u in range(4) if not any(x['unit']==u for x in pending.values()))
 ir=rng.random()<.7;rr=rng.random()<.7
 due=[x for x in pending.values() if x['due']<=cycle]
 complete=rng.choice(due) if due and not drain else None
 # Exercise ignored stale responses while draining; they must not acquire ownership.
 if drain and rng.random()<.5:complete=dict(slot=rng.randrange(8),fault=True)
 cv=bool(complete);cs=complete['slot'] if cv else 0;cf=complete['fault'] if cv else False
 cr=active and not fault_pending and len(q)<8
 iv=active and held is not None
 rv=active and bool(q) and q[0]['done']
 expected=[f'io_command_ready !== 1\'b{int(cr)}',f'io_issue_valid !== 1\'b{int(iv)}',f'io_retire_valid !== 1\'b{int(rv)}',f'io_occupancy !== 4\'d{len(q)}',f'io_draining !== 1\'b{int(drain)}']
 if iv:expected += [f'io_issue_bits_slot !== 3\'d{held["slot"]}',f'io_issue_bits_unit !== 2\'d{held["unit"]}',f'io_issue_bits_payload !== 128\'d{held["payload"]}']
 if rv:expected += [f'io_retire_bits_slot !== 3\'d{q[0]["slot"]}',f'io_retire_bits_tag !== 8\'d{q[0]["tag"]}',f'io_retire_bits_fault !== 1\'b{int(q[0]["fault"])}']
 lines += [f"io_flush={int(flush)};io_flushAck={int(ack)};io_command_valid={int(offer)};io_command_bits_reads=32'h{read:x};io_command_bits_writes=32'h{write:x};io_command_bits_unit={cmd['unit']};io_command_bits_barrier={int(cmd['barrier'])};io_command_bits_payload=128'd{cmd['payload']};io_command_bits_tag={cmd['tag']};io_unitReady={unit_ready};io_issue_ready={int(ir)};io_retire_ready={int(rr)};io_complete_valid={int(cv)};io_complete_bits_slot={cs};io_complete_bits_fault={int(cf)};#1;",
 f'if ({" || ".join(expected)}) $fatal(1,"window mismatch cycle {cycle}");tick();']
 selection=None
 if active and held is None and not fault_pending:
  for age,x in enumerate(q):
   blocked=any(o['barrier'] or x['barrier'] or (o['writes']&(x['reads']|x['writes'])) or (o['reads']&x['writes']) for o in q[:age])
   if not x['issued'] and not blocked and unit_ready>>x['unit']&1:selection=x;break
 fault_retire=rv and rr and q[0]['fault']
 if active:
  if selection is not None:held=selection
  if iv and ir:
   x=held;x['issued']=True
   stats['out_of_order_issue']+=int(x is not q[0]);stats['issued']+=1
   pending[x['slot']]=dict(slot=x['slot'],unit=x['unit'],due=cycle+rng.randrange(4,80),fault=rng.random()<.025)
   held=None
  elif iv:stats['held_stalls']+=1
  if cv:
   x=next(x for x in q if x['slot']==cs)
   assert x['issued'] and not x['done']
   stats['out_of_order_complete']+=int(any(o['issued'] and not o['done'] for o in q[:q.index(x)]))
   x['done']=True;x['fault']=cf;pending.pop(cs)
  if rv and rr:
   q.pop(0);head=(head+1)%8;stats['retired']+=1
  if offer and cr:q.append(cmd);tail=(tail+1)%8;serial+=1;stats['dispatched']+=1
 if flush or fault_retire:
  q=[];held=None;head=tail=0;drain=True;ack_at=cycle+3
  stats['flushes']+=int(flush);stats['faults']+=int(fault_retire)
 elif drain and ack:
  drain=False;pending={}
 stats['max_occupancy']=max(stats['max_occupancy'],len(q));stats['max_executing']=max(stats['max_executing'],len(pending))
assert not q and not pending and not held and not drain
assert all(stats[k]>0 for k in ['out_of_order_issue','out_of_order_complete','faults','held_stalls'])
assert stats['max_occupancy']==8 and stats['max_executing']>=3
lines+=['$display("PASS issue-window 10000 cycles");$finish;end endmodule']
label='mapped' if args.mapped else 'rtl'
tb=OUT/'tb.sv';tb.write_text('\n'.join(lines));rtl=ROOT/('build/synth/VectorIssueWindow/mapped.v' if args.mapped else 'build/rtl/VectorIssueWindow.sv')
extra=[str(ROOT/'tools/oss-cad-suite/share/yosys/xilinx/cells_sim.v'),str(ROOT/'tests/fp_mapped_global.sv')] if args.mapped else []
with (OUT/(label+'-compile.log')).open('w') as log:
 subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',*(['-s','glbl'] if args.mapped else []),'-o',str(OUT/label),str(tb),str(rtl),*extra],check=True,stdout=log,stderr=log)
run=subprocess.run([str(BIN/'vvp'),str(OUT/label)],capture_output=True,text=True)
(OUT/(label+'-simulation.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
d=dict(status='PASS',mapped=args.mapped,cycles=10000,stats=stats,scope='STANDALONE_SCHEDULER_NO_VPU_EXECUTION_INTEGRATION',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [rtl,tb,Path(__file__).resolve(),ROOT/'src/main/scala/vpu/VectorIssueWindow.scala']})
(OUT/('results-'+label+'.json')).write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
