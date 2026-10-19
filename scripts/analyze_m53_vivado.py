#!/usr/bin/env python3
"""Audit the user's immutable M53 routed-report ZIP, not embedded instructions."""
import hashlib,json,re
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    out=ROOT/'reports/local-m53';path=out/'input-reports.zip'
    with ZipFile(path) as z:
        assert z.testzip() is None;names=z.namelist();assert len(names)==len(set(names))
        assert all('/' not in n and '\\' not in n and '..' not in n for n in names)
        files={n:z.read(n) for n in names}
    hashes=json.loads(files['output-sha256.json'].decode('utf-8-sig'))
    assert set(hashes)==set(files)-{'output-sha256.json'}
    for n,h in hashes.items():assert sha(files[n])==h,n
    text=lambda n:files[n].decode('utf-8-sig')
    inputs=json.loads(text('run-inputs.json'));part='xczu15eg-ffvb1156-2-i'
    assert inputs['milestone']=='M53' and inputs['top']=='SpinorVpu' and inputs['part']==part
    with ZipFile(ROOT/'handoff/spinor-m53-timing.zip') as z:
        original_manifest=json.loads(z.read('spinor-m53-timing/input-sha256.json'))
    assert inputs['source_hashes']==original_manifest
    rtl=sha((ROOT/'build/rtl/SpinorVpu.sv').read_bytes())
    assert inputs['provenance']['rtl_sha256']==inputs['source_hashes']['rtl/SpinorVpu.sv']==rtl
    rpt=text('timing_routed.rpt');after=rpt.split('| Design Timing Summary',1)[1]
    row=next(line.split() for line in after.splitlines() if re.fullmatch(r'\s*'+r'(-?\d+(?:\.\d+)?\s+)'*11+r'-?\d+(?:\.\d+)?\s*',line))
    assert len(row)==12
    keys=['setup_slack_ns','setup_total_negative_slack_ns','setup_failing_endpoints','setup_total_endpoints',
          'hold_slack_ns','hold_total_negative_slack_ns','hold_failing_endpoints','hold_total_endpoints',
          'pulse_width_slack_ns','pulse_width_total_negative_slack_ns','pulse_width_failing_endpoints','pulse_width_total_endpoints']
    timing={k:float(v) if 'slack_ns' in k else int(v) for k,v in zip(keys,row)}
    assert timing['setup_slack_ns']==0.09 and timing['hold_slack_ns']==0.042 and timing['pulse_width_slack_ns']==1.124
    assert all(timing[k]==0 for k in keys if 'negative' in k or 'failing' in k)
    assert 'All user specified timing constraints are met.' in rpt
    assert re.search(r'\| Device\s*:\s*xczu15eg-ffvb1156\s*\n',rpt)
    assert re.search(r'\| Design State\s*:\s*Routed\s*\n',rpt)
    assert re.search(r'\| Speed File\s*:\s*-2\s',rpt) and re.search(r'\| Temperature Grade\s*:\s*I\s*\n',rpt)
    coverage={k:int(re.search(r'checking '+k+r' \((\d+)\)',rpt)[1]) for k in
              ['no_clock','unconstrained_internal_endpoints','no_input_delay','no_output_delay','loops','latch_loops']}
    assert coverage==dict(no_clock=0,unconstrained_internal_endpoints=0,no_input_delay=613,no_output_delay=608,loops=0,latch_loops=0)
    route=text('route_status.rpt')
    route_metrics={k:int(re.search(label+r'\.+\s*:\s*(\d+)',route)[1]) for k,label in
                   [('routable_nets','# of routable nets'),('fully_routed_nets','# of fully routed nets'),('routing_errors','# of nets with routing errors')]}
    assert route_metrics==dict(routable_nets=26029,fully_routed_nets=26029,routing_errors=0)
    util=text('utilization_routed.rpt')
    resources={k:int(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*(\d+)',util)[1]) for k,label in
               [('total_LUT','CLB LUTs'),('logic_LUT','LUT as Logic'),('memory_LUT','LUT as Memory'),('FF','CLB Registers'),('BRAM36','RAMB36/FIFO*'),('DSP','DSPs')]}
    assert resources==dict(total_LUT=18085,logic_LUT=17989,memory_LUT=96,FF=12490,BRAM36=2,DSP=7)
    log=text('vivado.log');error=text('flow-error.txt')
    assert 'invalid command name "redirect"' in error and 'route_design completed successfully' in log
    assert "routed.dcp' has been generated" in log
    assert 'HD.CLK_SRC of clock port "clock" is not set' in log
    assert not any(n.startswith('dsp') for n in files)
    actual_period=float(re.search(r'create_clock -period ([\d.]+)',text('constraints.xdc'))[1])
    assert actual_period==3.333
    result=dict(status='PASS',scope='USER_VIVADO_ROUTED_STANDARD_OOC_REPORT_AUDIT',milestone='M53',part=part,
        rtl_sha256=rtl,requested_period_ns=inputs['implementation_period_ns'],reported_clock_period_ns=actual_period,
        internal_OOC_300MHz_constraints_met=True,SoC_300MHz_signoff=None,passes_500MHz=None,hardware_changed=False,
        tool='Vivado 2025.1 build 6140274 Windows',timing=timing,coverage=coverage,routing=route_metrics,resources=resources,
        worst_setup=dict(source='vpu/vpu/rf/storage_ext/Memory_reg_1/CLKARDCLK',destination='vpu/vpu/stagedData_reg[79]/D',
                         data_path_ns=3.177,logic_ns=1.404,route_ns=1.773,logic_levels=5),
        flow_exit=1,flow_failure='POST_REPORT_UNSUPPORTED_REDIRECT_COMMAND',routed_checkpoint_saved_per_log=True,
        routed_checkpoint_uploaded=False,DSP_export='NOT_REACHED',SDF_simulation='NOT_RUN',clock_source_location='UNSPECIFIED',
        input_zip_sha256=sha(path.read_bytes()),input_members_sha256=hashes,
        source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__).read_bytes())},
        artifact_sha256={'reports/local-m53/input-reports.zip':sha(path.read_bytes()),
                         'reports/local-m53/evaluation.md':sha((out/'evaluation.md').read_bytes())})
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','scope','timing','coverage','routing','resources','flow_failure']},indent=2))
if __name__=='__main__':main()
