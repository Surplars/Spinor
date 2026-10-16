#!/usr/bin/env python3
"""Event-driven what-if simulation. ZERO DELAY must pass before any scenario.

Assumptions are declared explicitly, not calibrated to XCZU15EG or any device.
No result here is a routed STA, manufacturer SDF, or frequency qualification.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_lane import check

OUT=ROOT/'build/timing-reference';OUT.mkdir(parents=True,exist_ok=True)
BIN=ROOT/'tools/oss-cad-suite/bin'
SCENARIOS={
 'zero':{'LUT':0.0,'LINK':0.0,'CARRY':0.0,'CQ':0.0,'SETUP':0.0,'HOLD':0.0,'RAM':0.0},
 'assumption_A':{'LUT':.10,'LINK':.05,'CARRY':.025,'CQ':.12,'SETUP':.06,'HOLD':.02,'RAM':.20},
 'assumption_B':{'LUT':.16,'LINK':.10,'CARRY':.035,'CQ':.18,'SETUP':.10,'HOLD':.03,'RAM':.30}}
TOPS=[('IntegerLaneBaseline',2),('IntegerLaneSplit',6),('IntegerLaneSplit16',7)]

def check_monitor():
    model_exe=OUT/'model-check'
    with (OUT/'model-check.compile.log').open('w') as log:
        flags=[f'-DREF_{k}={v}' for k,v in SCENARIOS['assumption_B'].items()]
        subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb']+flags+['-o',str(model_exe),
                       str(ROOT/'tests/timing_reference_cells.sv'),str(ROOT/'tests/timing_model_check.sv')],
                       stdout=log,stderr=log,check=True)
    monitor_check=subprocess.run([str(BIN/'vvp'),str(model_exe)],capture_output=True,text=True,check=True)
    (OUT/'model-check.log').write_text(monitor_check.stdout+monitor_check.stderr)
    assert 'PASS reference checker deliberate setup=1 hold=1' in monitor_check.stdout
    return monitor_check.stdout.strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check-monitor-only',action='store_true',help='validate setup/hold instrumentation without repeating the sweep')
    args=parser.parse_args()
    monitor_check=check_monitor()
    if args.check_monitor_only:
        print(monitor_check)
        return
    source=ROOT/'build/test/lane.stim'
    if not source.exists():raise SystemExit('Run tests/test_lane.py first')
    selected=source.read_text().splitlines()[:1088]+['0 1 0 0 0 0 0 0 0']*20
    stimulus=ROOT/'build/test/timing-reference.stim';stimulus.write_text('\n'.join(selected)+'\n')
    rows=[]
    for line in selected:
        iv,rd,fl,a,b,sew,op,sel,tag=line.split()
        rows.append(tuple(map(int,[iv,rd,fl]))+(int(a,16),int(b,16))+tuple(map(int,[sew,op,sel,tag])))
    def run(job):
        top,latency,scenario,mhz=job
        tag=f'{top}-{scenario}-{mhz}MHz';exe=OUT/tag
        args=[str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={top}',f'-DPERIOD_NS={1000/mhz:.12f}',f'-DSTIM_COUNT={len(rows)}']
        args += [f'-DREF_{k}={v}' for k,v in SCENARIOS[scenario].items()]
        args += ['-o',str(exe),str(ROOT/'tests/timing_reference_cells.sv'),
                 str(ROOT/'tests/timing_lane_tb.sv'),str(ROOT/f'build/synth/{top}/mapped.v')]
        with (OUT/f'{tag}.compile.log').open('w') as log:
            subprocess.run(args,stdout=log,stderr=log,check=True)
        sim=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True,check=True,cwd=ROOT)
        (OUT/f'{tag}.log').write_text(sim.stdout+sim.stderr)
        trace=[s for s in sim.stdout.splitlines() if s.startswith('T ')]
        counts=next(s for s in sim.stdout.splitlines() if s.startswith('REFERENCE_COUNTS')).split()[1:]
        functional=True;error=None
        try:
            assert len(trace)==len(rows)
            assert all(int(s.split()[1])==i for i,s in enumerate(trace))
            check(rows,trace,latency,top!='IntegerLaneBaseline')
        except (AssertionError,ValueError) as e:functional=False;error=str(e)[:200]
        result={'top':top,'scenario':scenario,'clock_MHz':mhz,'period_ns':1000/mhz,
                'source_launch_delay_ns':.25,'setup_violations':int(counts[0]),'hold_violations':int(counts[1]),
                'ram_write_violations':int(counts[2]),'functional_trace_matches':functional,
                'first_trace_mismatch':error,'device_frequency_qualified':False}
        if scenario=='zero' and (not functional or any(map(int,counts))):raise RuntimeError('Reference model zero-delay control failed: '+str(result))
        print(json.dumps(result),flush=True);return result
    # Gate the sweep on all zero-delay controls; an invalid model must not be
    # misreported as the hardware failing a frequency target.
    results=[run((t,l,'zero',300)) for t,l in TOPS]
    jobs=[(t,l,s,f) for s in ['assumption_A','assumption_B'] for f in [300,500] for t,l in TOPS]
    with ThreadPoolExecutor(max_workers=2) as pool:results+=list(pool.map(run,jobs))
    report={'scope':'UNCALIBRATED_REFERENCE_TIMING_SIMULATION_OF_INTEGER_LANES_ONLY',
            'not_AMD_SDF':True,'not_device_STA':True,'not_full_VPU_timing_simulation':True,
            'assumptions_ns':SCENARIOS,'monitor_negative_control':monitor_check,
            'stimulus_cycles':len(rows),'results':results,
            'stimulus_sha256':hashlib.sha256(stimulus.read_bytes()).hexdigest()}
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
