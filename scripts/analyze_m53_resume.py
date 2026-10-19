#!/usr/bin/env python3
"""Audit received Windows report-only resume against the immutable first run."""
import hashlib,json,re
from pathlib import Path
from zipfile import ZipFile
from report_m51 import ROOT,check
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    out=ROOT/'reports/local-m53-resume';path=out/'input-reports.zip'
    prior=json.loads((ROOT/'reports/local-m53/receipt.json').read_text());check(prior)
    with ZipFile(path) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        assert all('/' not in n and '\\' not in n and '..' not in n for n in z.namelist())
        data={n:z.read(n) for n in z.namelist()}
    text=lambda n:data[n].decode('utf-8-sig')
    hashes=json.loads(text('output-sha256.json'));assert set(hashes)==set(data)-{'output-sha256.json'}
    for n,h in hashes.items():assert sha(data[n])==h,n
    inputs=json.loads(text('run-inputs.json'))
    with ZipFile(ROOT/'handoff/spinor-m53-timing-fix1.zip') as z:
        manifest=json.loads(z.read('spinor-m53-timing/input-sha256.json'))
    assert inputs['source_hashes']==manifest
    assert inputs['milestone']=='M53' and inputs['top']=='SpinorVpu' and inputs['part']==prior['part']
    assert inputs['mode']=='ResumeReports' and not inputs['implementation_repeated']
    assert inputs['source_hashes']['rtl/SpinorVpu.sv']==prior['rtl_sha256']
    assert inputs['previous_inputs_sha256']==prior['input_members_sha256']['run-inputs.json']
    with ZipFile(ROOT/'reports/local-m53/input-reports.zip') as z:
        assert inputs['prior_run_inputs']==json.loads(z.read('run-inputs.json').decode('utf-8-sig'))
    summary=dict(line.split('=',1) for line in text('run-summary.txt').splitlines())
    assert summary['standalone_setup_hold_nonnegative']=='1'
    assert float(summary['setup_slack_ns'])==prior['timing']['setup_slack_ns']
    assert float(summary['hold_slack_ns'])==prior['timing']['hold_slack_ns']
    assert float(summary['period_ns'])==prior['reported_clock_period_ns']
    assert summary['DSP_export_status']=='NONEMPTY_FILES_ARC_COMPLETENESS_UNVERIFIED'
    # Verify the detailed timing table as well as the wrapper summary.
    rpt=text('timing_routed.rpt').split('| Design Timing Summary',1)[1]
    row=next(s.split() for s in rpt.splitlines() if re.fullmatch(r'\s*'+r'(-?\d+(?:\.\d+)?\s+)'*11+r'-?\d+(?:\.\d+)?\s*',s))
    assert [float(x) for x in row]==[float(v) for v in prior['timing'].values()]
    route=text('route_status.rpt')
    for key,label in [('routable_nets','# of routable nets'),('fully_routed_nets','# of fully routed nets'),('routing_errors','# of nets with routing errors')]:
        assert int(re.search(label+r'\.+\s*:\s*(\d+)',route)[1])==prior['routing'][key]
    for name,count in prior['coverage'].items():assert re.search(r'checking '+name+r' \('+str(count)+r'\)',text('check_timing.rpt'))
    log=text('vivado.log');loaded=text('checkpoint-loaded.txt')
    assert 'implementation_repeated=NO' in loaded and 'period_ns=3.333' in loaded
    assert 'Command: open_checkpoint' in log and 'DONE: M53 routed reports' in log
    assert not any(n in data for n in ['flow-error.txt','launch-error.txt','dsp-export-error.txt'])
    assert not re.search(r'^(?:FLOW FAILED:|ERROR:|CRITICAL WARNING:)',log,re.M)
    assert not re.search(r'^(?:Command: )?(?:synth_design|opt_design|place_design|phys_opt_design|route_design)\b',log,re.M)
    configs={};current=None
    for line in text('dsp-configurations.txt').splitlines():
        if line.startswith('DSP '):current=line[4:];assert current not in configs;configs[current]={}
        else:key,value=line.split('=',1);configs[current][key]=value
    assert len(configs)==7 and all(c['MREG']=='0' and c['PREG']=='1' for c in configs.values())
    groups={}
    for dsp,config in configs.items():groups.setdefault(tuple(sorted(config.items())),[]).append(dsp)
    assert sorted(len(v) for v in groups.values())==[1,6]
    coverage=dict((name,int(count)) for name,count in re.findall(r'^(\S+) timing_rows=(\d+)\r?$',text('dsp-export-coverage.txt'),re.M))
    assert set(coverage)=={name.replace('/','-')+'.txt' for name in configs}
    assert sorted(coverage.values())==[65,91,91,91,91,91,91] and sum(coverage.values())==611
    assert not any(n.startswith('dsp_delay/') for n in data)
    result=dict(status='PASS',scope='USER_WINDOWS_VIVADO_REPORT_ONLY_RESUME_AUDIT',part=inputs['part'],
        rtl_sha256=prior['rtl_sha256'],reported_checkpoint_sha256=inputs['checkpoint_sha256'],checkpoint_uploaded=False,
        implementation_repeated=False,actual_Windows_Vivado_resume_completed=True,internal_OOC_300MHz_constraints_met=True,
        SoC_300MHz_signoff=None,passes_500MHz=None,timing=prior['timing'],routing=prior['routing'],resources=prior['resources'],
        DSP_export_status=summary['DSP_export_status'],DSP_instances=7,DSP_distinct_recorded_configurations=2,
        DSP_export_reported_total_rows=611,DSP_reported_rows_per_file=coverage,DSP_configurations=configs,
        raw_DSP_tables_in_this_report_zip=False,DSP_arc_completeness_verified=False,cloud_DSP_calibration_updated=False,
        source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__).read_bytes())},
        artifact_sha256={'reports/local-m53-resume/input-reports.zip':sha(path.read_bytes()),
                         'reports/local-m53/receipt.json':sha((ROOT/'reports/local-m53/receipt.json').read_bytes()),
                         'reports/local-m53-resume/evaluation.md':sha((out/'evaluation.md').read_bytes())},
        input_members_sha256=hashes)
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS M53 Windows/Vivado resume; unchanged +0.090/+0.042ns; 7 DSPs, 611 reported rows; raw DSP tables not in report ZIP')
if __name__=='__main__':main()
