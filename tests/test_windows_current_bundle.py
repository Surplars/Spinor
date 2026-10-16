#!/usr/bin/env python3
"""Replay the real handoff TBs and test Tcl/PowerShell orchestration with fake tools.

Only Icarus, Tcl and Linux PowerShell execute here. This does not run XSim,
Vivado, Windows, P&R, SDF or the real DSP exporter.
"""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/windows-m31-validation';OUT.mkdir(parents=True,exist_ok=True)
# PowerShell uses XDG directories; keep all check-time state in the workspace.
for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data')]:
 path=OUT/'powershell-state'/folder;path.mkdir(parents=True,exist_ok=True);os.environ[key]=str(path)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
bundle=ROOT/'spinor-windows-m31.zip'
with ZipFile(bundle) as z:
 assert z.testzip() is None
 z.extractall(OUT/'path with spaces')
work=OUT/'path with spaces/spinor-m31'
manifest=json.loads((work/'input-sha256.json').read_text())
for n,h in manifest.items():assert sha(work/n)==h,n
provenance=json.loads((work/'provenance.json').read_text());replays={}
for name,top,tb,marker in [('extensions','RamVectorFp','integer-extensions.sv','PASS integer-extensions'),('integration','SpinorVpu','spinor-integration.sv','PASS vector-memory')]:
 output=OUT/(name+'.vvp');log=OUT/(name+'-compile.log')
 with log.open('w') as f:subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/iverilog'),'-g2012','-s','tb','-D'+'TOP='+top,'-o',str(output),str(work/'rtl'/f'{top}.sv'),str(work/'tb'/tb)],stdout=f,stderr=f,check=True)
 run=subprocess.run([str(ROOT/'tools/oss-cad-suite/bin/vvp'),str(output)],capture_output=True,text=True);(OUT/(name+'.log')).write_text(run.stdout+run.stderr)
 assert run.returncode==0 and marker in run.stdout,run.stdout+run.stderr
 if name=='integration':assert 'PASS monitored-mmio' in run.stdout
 replays[name]={'status':'PASS','RTL_sha256':sha(work/'rtl'/f'{top}.sv'),'testbench_sha256':sha(work/'tb'/tb),'summary':[s for s in run.stdout.splitlines() if s.startswith('PASS ')]}
# Exercise the actual Tcl file with a small fake Vivado command surface.
# Its source hook deliberately demands global property_list, reproducing the
# older failure mode; fake XSim logs can omit PASS or contain Fatal messages.
harness=OUT/'mock-vivado.tcl'
harness.write_text(r'''
set scenario [lindex $argv 0]
set root [lindex $argv 1]
set out [lindex $argv 2]
set mode [lindex $argv 3]
file mkdir $out
set trace [open [file join $out commands.txt] w]
proc record {name args} {global trace;puts $trace [list $name {*}$args];flush $trace}
foreach cmd {set_param add_files update_compile_order log_wave run close_sim close_project read_verilog opt_design place_design phys_opt_design route_design check_timing} {
 proc $cmd {args} [format {record %s {*}$args} $cmd]
}
proc create_project {args} {global project_dir project_name;record create_project {*}$args;if {[lindex $args 0] eq "-force"} {set project_name [lindex $args 1];set project_dir [lindex $args 2]}}
proc get_filesets {args} {return [lindex $args end]}
proc set_property {args} {record set_property {*}$args}
proc version {args} {return MOCK_ONLY_NOT_VIVADO}
proc get_parts {args} {return xczu15eg-ffvb1156-2-i}
proc get_ports {args} {return clock}
proc get_clocks {args} {global scenario;if {$scenario eq "missing-clock"} {return {}};return vpu_clk}
proc read_xdc {p} {record read_xdc $p}
proc synth_design {args} {if {[lsearch -exact $args SpinorVpu]<0 || [lsearch -exact $args out_of_context]<0} {error "wrong synthesis boundary"};record synth_design {*}$args}
foreach cmd {report_utilization write_checkpoint report_timing_summary write_edif write_xdc report_route_status report_clocks report_timing} {
 proc $cmd {args} [format {record %s {*}$args;set p [lindex $args end];set f [open $p w];puts $f MOCK_ARTIFACT_NOT_VIVADO;close $f} $cmd]
}
proc get_timing_paths {args} {return path}
proc get_cells {args} {return dsp0}
proc get_property {name object} {if {$name eq "SLACK"} {return -0.12};return 1}
proc launch_simulation {args} {
 global project_dir project_name scenario
 set log_dir [file join $project_dir ${project_name}.sim sim_1 behav xsim];file mkdir $log_dir
 set text [expr {[string match *extensions $project_name]?"PASS integer-extensions commands=884":"PASS monitored-mmio\nPASS vector-memory"}]
 if {$scenario eq "sim-fatal"} {append text "\nFatal: induced simulation failure"}
 if {$scenario eq "sim-no-pass"} {set text "simulation ended without oracle"}
 if {$scenario eq "monitor-no-pass"} {set text [string map {{PASS monitored-mmio} {monitor absent}} $text]}
 set f [open [file join $log_dir simulate.log] w];puts $f $text;close $f
}
rename source real_source
proc source {p} {
 if {[file tail $p] eq "dump_all_dsp_delay.tcl"} {
  if {[info level]!=1} {error "DSP exporter was not sourced globally"}
  set ::property_list {AREG PREG}
  proc ::dump_all_dsp_delay {{properties $::property_list}} {
   global scenario
   set f [open dsp0.txt w];if {$scenario ne "dsp-empty"} {puts $f "A P 1.25"};close $f
  }
  record exporter-global-scope
  return
 }
 uplevel 1 [list real_source $p]
}
set argv [list $mode 3.333333 $out 4]
source [file join $root run_vivado.tcl]
''')
mock_cases=[]
for scenario,mode,good in [('normal','Rtl',True),('normal','Implement',True),('normal','All',True),('sim-fatal','Rtl',False),('sim-no-pass','Rtl',False),('monitor-no-pass','Rtl',False),('missing-clock','Implement',False),('dsp-empty','Implement',False),('normal','Bogus',False)]:
 dest=OUT/f'tcl-{scenario}-{mode}'
 run=subprocess.run(['tclsh',str(harness),scenario,str(work),str(dest),mode],capture_output=True,text=True);(OUT/f'tcl-{scenario}-{mode}.log').write_text(run.stdout+run.stderr)
 assert (run.returncode==0)==good,(scenario,run.stdout,run.stderr)
 if good and mode in ['All','Implement']:
  assert '3.333333' in (dest/'clock.xdc').read_text()
  assert 'setup_slack_ns=-0.12' in (dest/'run-summary.txt').read_text() # flow success must not imply timing passed
  trace=(dest/'commands.txt').read_text();assert 'route_design' in trace and 'exporter-global-scope' in trace
 if not good:assert (dest/'flow-error.txt').is_file()
 mock_cases.append({'scenario':scenario,'mode':mode,'expected_success':good,'exit':run.returncode})
pwsh=ROOT/'tools/pwsh/pwsh';assert pwsh.is_file(),'Install pinned portable PowerShell to tools/pwsh first'
# Parse the actual PS file, then execute it with a fake native Vivado launcher
# under a path containing spaces. This exercises hashes, arguments, nonzero
# exits, recursive ZIP streaming and failure-result preservation.
parser=OUT/'parse.ps1';parser.write_text('param([string]$Path)\n$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){$errors|Out-String|Write-Error;exit 1};Write-Host "PASS PowerShell parser"\n')
run=subprocess.run([str(pwsh),'-NoProfile','-File',str(parser),'-Path',str(work/'run.ps1')],capture_output=True,text=True);(OUT/'powershell-parse.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stderr
fake=OUT/'fake vivado launcher'
fake.write_text('#!/usr/bin/env python3\nimport sys,pathlib,os,json\na=sys.argv[1:];i=a.index("-tclargs");mode,period,out,threads=a[i+1:];p=pathlib.Path(out);(p/"nested").mkdir();(p/"nested/log.txt").write_text("MOCK_ONLY");(p/"arguments.json").write_text(json.dumps(a));(p/"run-summary.txt").write_text("MOCK_ONLY_NOT_VIVADO");sys.exit(int(os.getenv("MOCK_EXIT","0")))\n');fake.chmod(0o755)
ps_cases=[]
for code in [0,7]:
 env=dict(os.environ,MOCK_EXIT=str(code));run=subprocess.run([str(pwsh),'-NoProfile','-File',str(work/'run.ps1'),'-VivadoBat',str(fake),'-Mode','All'],capture_output=True,text=True,env=env)
 (OUT/f'powershell-exit-{code}.log').write_text(run.stdout+run.stderr)
 assert (run.returncode==0)==(code==0),run.stdout+run.stderr
 zipname=re.search(r'Upload this ZIP: (.+)',run.stdout).group(1).strip()
 with ZipFile(zipname) as z:
  assert z.testzip() is None;assert z.read('nested/log.txt')==b'MOCK_ONLY'
  hashes=json.loads(z.read('output-sha256.json'))
  for n,h in hashes.items():assert hashlib.sha256(z.read(n)).hexdigest()==h,n
  inputs=json.loads(z.read('run-inputs.json').decode('utf-8-sig'));assert inputs['top']=='SpinorVpu'
  arguments=json.loads(z.read('arguments.json'));assert arguments[arguments.index('-tclargs')+2]=='3.333333'
 ps_cases.append({'native_exit':code,'runner_exit':run.returncode,'result_zip_preserved':True})
# Changed RTL must fail before launching the tool or creating a result run.
rtl=work/'rtl/SpinorVpu.sv';original=rtl.read_bytes();rtl.write_bytes(original+b'\n// changed\n')
try:
 run=subprocess.run([str(pwsh),'-NoProfile','-File',str(work/'run.ps1'),'-VivadoBat',str(fake)],capture_output=True,text=True)
 (OUT/'powershell-mutated-input.log').write_text(run.stdout+run.stderr)
 assert run.returncode!=0 and 'Input hash mismatch' in run.stderr
finally:rtl.write_bytes(original)
files=[Path(__file__).resolve(),ROOT/'scripts/windows_current_bundle.py',*sorted((ROOT/'scripts/windows-current').glob('*'))]
for p in sorted((OUT).glob('*.log')):files.append(p)
result=dict(status='PASS',scope='EXACT_PACKAGED_TB_ICARUS_REPLAY_AND_MOCK_ORCHESTRATION; NO_WINDOWS_XSIM_VIVADO_PNR_SDF_EXECUTION',
 bundle_sha256=sha(bundle),manifest_entries=len(manifest),replays=replays,tcl_mock_cases=mock_cases,powershell_mock_cases=ps_cases,
 powershell_version='7.5.4 Linux; Windows 5.1 not executed',tampered_input_rejected=True,
 input_sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2))
