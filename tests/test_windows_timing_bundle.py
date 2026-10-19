#!/usr/bin/env python3
"""Real PowerShell/Tcl/ZIP control flow with MOCK Vivado, no FPGA timing claim."""
import hashlib,json,os,re,subprocess
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/windows-m53-timing-check';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    bundle=ROOT/'handoff/spinor-m53-timing-fix1.zip';pwsh=ROOT/'tools/pwsh/pwsh'
    environment=dict(os.environ)
    for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data')]:
        path=OUT/folder;path.mkdir(exist_ok=True);environment[key]=str(path)
    with ZipFile(bundle) as z:
        assert z.testzip() is None
        assert all('..' not in Path(n).parts and n.startswith('spinor-m53-timing/') for n in z.namelist())
        z.extractall(OUT/'path with spaces')
    work=OUT/'path with spaces/spinor-m53-timing';manifest=json.loads((work/'input-sha256.json').read_text())
    for n,h in manifest.items():assert sha((work/n).read_bytes())==h,n
    assert (work/'rtl/SpinorVpu.sv').read_bytes()==(ROOT/'build/rtl/SpinorVpu.sv').read_bytes()
    mock=OUT/'mock-vivado.tcl'
    mock.write_text(r'''
set trace [open [file join [lindex $argv 2] mock-calls.txt] w]
set actual_script [lindex $argv 0];set argv [lrange $argv 1 end]
proc unknown {command args} {
    puts $::trace "$command $args";flush $::trace
    # Reject unmodelled commands. The first mock incorrectly accepted
    # Synopsys redirect, which actual Vivado 2025.1 rejected after routing.
    if {$command ni {version get_parts get_ports get_clocks get_cells get_timing_paths get_property read_verilog read_xdc synth_design open_checkpoint current_design create_project set_param report_utilization write_checkpoint opt_design place_design report_timing_summary phys_opt_design route_design write_edif write_xdc report_route_status report_clocks report_drc report_timing check_timing}} {
        error "Unsupported mock/Vivado command: $command"
    }
    switch -- $command {
        version {return MOCK_NOT_VIVADO}
        get_parts {return xczu15eg-ffvb1156-2-i}
        get_ports {
            if {$::env(MOCK_CASE) eq "wrong-top" && [lindex $args end] eq "io_core_command_valid"} {return {}}
            return [lindex $args end]
        }
        get_clocks {return vpu_clk}
        current_design {return SpinorVpu}
        get_cells {error "MOCK optional DSP export failure"}
        get_timing_paths {
            if {$::env(MOCK_CASE) eq "empty"} {return {}}
            if {[lsearch -exact $args min]>=0} {return hold}
            return setup
        }
        get_property {
            if {[lindex $args 0] eq "PART"} {
                if {$::env(MOCK_CASE) eq "wrong-part"} {return xczu7ev-ffvc1156-2-e}
                return xczu15eg-ffvb1156-2-i
            }
            if {[lindex $args 0] eq "PERIOD"} {return 3.333}
            if {[lindex $args 1] eq "hold"} {
                if {$::env(MOCK_CASE) eq "negative"} {return -0.005}
                return 0.01
            }
            return 0.123
        }
        check_timing {if {$args ne "-verbose"} {error "Unsupported check_timing options"}}
        read_verilog {if {![file isfile [lindex $args end]]} {error "Missing RTL"}}
        read_xdc {if {![file isfile [lindex $args end]]} {error "Missing XDC"}}
        synth_design {if {[lsearch -exact $args SpinorVpu]<0 || [lsearch -exact $args out_of_context]<0} {error "Wrong synthesis top/mode"}}
        open_checkpoint {if {![file isfile [lindex $args end]]} {error "Missing checkpoint"}}
    }
    set i [lsearch -exact $args -file]
    if {$i>=0} {set f [open [lindex $args [expr {$i+1}]] w];puts $f MOCK_REPORT;close $f}
    if {$command in {write_checkpoint write_edif write_xdc}} {
        set f [open [lindex $args end] w];puts $f MOCK_ARTIFACT;close $f
    }
    return ""
}
source $actual_script
''')
    launcher=OUT/'fake Vivado launcher'
    launcher.write_text('#!/usr/bin/env python3\nimport sys,subprocess\na=sys.argv[1:];s=a[a.index("-source")+1];i=a.index("-tclargs");sys.exit(subprocess.call(["tclsh",'+repr(str(mock))+',s,*a[i+1:]]))\n');launcher.chmod(0o755)
    def call(args,label,ok=True,case='positive'):
        result=subprocess.run([pwsh,'-NoProfile','-File',*map(str,args)],cwd=work,env=dict(environment,MOCK_CASE=case),capture_output=True,text=True)
        (OUT/(label+'.log')).write_text(result.stdout+result.stderr)
        assert (result.returncode==0)==ok,(label,result.stdout,result.stderr)
        return result
    def audit_zip(path,full=False):
        with ZipFile(path) as z:
            names=z.namelist();assert len(names)==len(set(names)) and z.testzip() is None
            assert names.count('output-sha256.json')==1 and 'run-inputs.json' in names
            assert ('routed.dcp' in names)==full
            hashes=json.loads(z.read('output-sha256.json').decode('utf-8-sig'))
            assert 'output-sha256.json' not in hashes
            assert set(hashes)==set(names)-{'output-sha256.json'}
            for n,h in hashes.items():assert sha(z.read(n))==h,n
    cases=[]
    for case in ['positive','negative','empty','dsp-error']:
        args=[work/'run.ps1','-VivadoBat',launcher]
        if case!='dsp-error':args.append('-SkipDspExport')
        result=call(args,case,ok=case!='empty',case=case)
        archive=Path(re.search(r'Upload this ZIP: (.+)',result.stdout)[1].strip());audit_zip(archive)
        run=Path(re.search(r'Result folder: (.+)',result.stdout)[1].strip())
        trace=(run/'mock-calls.txt').read_text()
        assert all(x in trace for x in ['synth_design','opt_design','place_design','phys_opt_design','route_design'])
        assert 'open_checkpoint' not in trace
        if case=='empty':assert 'Missing setup or hold paths' in (run/'flow-error.txt').read_text()
        else:
            summary=(run/'run-summary.txt').read_text()
            assert 'standalone_setup_hold_nonnegative='+('0' if case=='negative' else '1') in summary
            if case=='dsp-error':assert 'DSP_export_status=ERROR_' in summary and (run/'timing_routed.rpt').is_file()
        if case=='positive':
            source_run=run
            for repeat in range(2):
                target=OUT/f'repack-{repeat}.zip'
                if target.exists():target.unlink()
                call([work/'pack_results.ps1','-RunDirectory',run,'-DestinationZip',target],f'repack-{repeat}');audit_zip(target)
            target=OUT/'full.zip'
            if target.exists():target.unlink()
            call([work/'pack_results.ps1','-RunDirectory',run,'-DestinationZip',target,'-Full'],'full');audit_zip(target,full=True)
            call([work/'pack_results.ps1','-RunDirectory',run,'-DestinationZip',target],'existing-refused',ok=False)
            call([work/'pack_results.ps1','-RunDirectory',run,'-DestinationZip',run/'inside.zip'],'inside-refused',ok=False)
        cases.append(dict(case=case,runner_exit=result.returncode,zip_audited=True))
    checkpoint=source_run/'routed.dcp';original_checkpoint=checkpoint.read_bytes()
    for case in ['resume','resume-dsp-error','wrong-part','wrong-top']:
        args=[work/'resume.ps1','-PreviousRun',source_run]
        if case!='resume-dsp-error':args.append('-SkipDspExport')
        result=call(args,case,ok=case not in ['wrong-part','wrong-top'],case=case)
        archive=Path(re.search(r'Upload this ZIP: (.+)',result.stdout)[1].strip());audit_zip(archive)
        run=Path(re.search(r'Result folder: (.+)',result.stdout)[1].strip());trace=(run/'mock-calls.txt').read_text()
        assert 'open_checkpoint' in trace
        for forbidden in ['synth_design','opt_design','place_design','phys_opt_design','route_design','read_xdc','write_checkpoint']:
            assert forbidden not in trace,(case,forbidden)
        if case.startswith('resume'):
            assert 'period_ns=3.333' in (run/'checkpoint-loaded.txt').read_text()
            assert 'standalone_setup_hold_nonnegative=1' in (run/'run-summary.txt').read_text()
        else:assert 'Checkpoint' in (run/'flow-error.txt').read_text()
        assert checkpoint.read_bytes()==original_checkpoint
        cases.append(dict(case=case,runner_exit=result.returncode,zip_audited=True,implementation_repeated=False))
    prior_path=source_run/'run-inputs.json';original_prior=prior_path.read_bytes();prior=json.loads(original_prior.decode('utf-8-sig'))
    prior['source_hashes']['rtl/SpinorVpu.sv']='0'*64;prior_path.write_text(json.dumps(prior))
    mismatch=call([work/'resume.ps1','-PreviousRun',source_run],'wrong-rtl-refused',ok=False)
    assert 'RTL does not match' in mismatch.stderr;prior_path.write_bytes(original_prior)
    bad_script=OUT/'unsupported.tcl';bad_script.write_text('redirect -file forbidden.txt {check_timing -verbose}\n')
    rejected=subprocess.run(['tclsh',mock,bad_script,'3.333',OUT,'4','xczu15eg-ffvb1156-2-i','0'],capture_output=True,text=True,env=dict(environment,MOCK_CASE='negative-control'))
    (OUT/'unsupported-command.log').write_text(rejected.stdout+rejected.stderr)
    assert rejected.returncode!=0 and 'Unsupported mock/Vivado command: redirect' in rejected.stderr
    script=work/'run_vivado.tcl';original=script.read_bytes();script.write_bytes(original+b'\n# changed\n')
    invalid=call([work/'run.ps1','-VivadoBat',launcher],'changed-input-refused',ok=False)
    assert 'Input hash mismatch' in invalid.stderr;script.write_bytes(original)
    for name in ['run.ps1','resume.ps1','pack_results.ps1']:
        text=(work/name).read_text();assert text.index('Add-Type -AssemblyName System.IO.Compression\n')<text.index('Add-Type -AssemblyName System.IO.Compression.FileSystem')
    files=[Path(__file__).resolve(),ROOT/'scripts/package_windows_timing.py',*sorted((ROOT/'scripts/windows-timing').glob('*')),*sorted(OUT.glob('*.log'))]
    receipt=dict(status='PASS',scope='LINUX_POWERSHELL_7_AND_TCL_MOCK_VIVADO_ONLY',Windows_5_1_executed=False,Vivado_executed=False,
                 bundle_sha256=sha(bundle.read_bytes()),cases=cases,input_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in files})
    (OUT/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_sha256'},indent=2))
if __name__=='__main__':main()
