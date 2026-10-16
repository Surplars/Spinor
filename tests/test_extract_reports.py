#!/usr/bin/env python3
"""Replay the reports-only ZIP selector using real Linux PowerShell ZIP APIs."""
import hashlib,json,os,subprocess
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/report-extractor';OUT.mkdir(parents=True,exist_ok=True)
for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data')]:
 p=OUT/folder;p.mkdir(exist_ok=True);os.environ[key]=str(p)
source=OUT/'large result with spaces.zip';target=OUT/'reports only.zip'
keep={'run-summary.txt':b'setup_slack_ns=0.01','timing_routed.rpt':b'report','run-inputs.json':b'{}','output-sha256.json':b'{}','dsp-export-coverage.txt':b'coverage','simulation/integration/result.txt':b'PASS','simulation/integration/project/xsim/simulate.log':b'PASS vector-memory'}
skip={'routed.dcp':b'checkpoint','routed.edf':b'netlist','simulation/trace.wdb':b'wave','.Xil/cache.txt':b'cache','simulation/integration/xsim.dir/cache.log':b'cache','dsp_delay/dsp0.txt':b'arcs'}
with ZipFile(source,'w',compression=ZIP_DEFLATED) as z:
 for n,b in (keep|skip).items():z.writestr(n,b)
if target.exists():target.unlink()
args=[str(ROOT/'tools/pwsh/pwsh'),'-NoProfile','-File',str(ROOT/'scripts/windows-current/extract_reports.ps1'),'-ResultZip',str(source),'-DestinationZip',str(target)]
run=subprocess.run(args,capture_output=True,text=True);(OUT/'run.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
with ZipFile(target) as z:
 assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
 assert set(z.namelist())==set(keep)
 for n,b in keep.items():assert z.read(n)==b
again=subprocess.run(args,capture_output=True,text=True);(OUT/'no-overwrite.log').write_text(again.stdout+again.stderr);assert again.returncode!=0
files=[Path(__file__).resolve(),ROOT/'scripts/windows-current/extract_reports.ps1',source,target,OUT/'run.log',OUT/'no-overwrite.log']
result=dict(status='PASS',scope='LINUX_POWERSHELL_7_5_4_REAL_ZIP_SELECTION; WINDOWS_5_1_NOT_EXECUTED',preserved_entries=len(keep),excluded_entries=len(skip),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS report selection, exact bytes, paths with spaces, caches and no overwrite')
