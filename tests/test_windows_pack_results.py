#!/usr/bin/env python3
"""Check fresh and recovery ZIP paths with Linux PowerShell; not Windows/Vivado."""
import hashlib,json,os,re,subprocess
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/windows-m31-fix1-validation';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key,folder in [('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data')]:
 p=OUT/folder;p.mkdir(exist_ok=True);os.environ[key]=str(p)
bundle=ROOT/'spinor-windows-m31-fix1.zip'
with ZipFile(bundle) as z:
 assert z.testzip() is None;z.extractall(OUT/'path with spaces')
work=OUT/'path with spaces/spinor-m31-fix1'
manifest=json.loads((work/'input-sha256.json').read_text())
for n,h in manifest.items():assert sha(work/n)==h
# Hardware/Tcl/testbench payloads must match the exact original user bundle.
with ZipFile(ROOT/'spinor-windows-m31.zip') as old,ZipFile(bundle) as new:
 for name in ['rtl/SpinorVpu.sv','rtl/RamVectorFp.sv','tb/integer-extensions.sv','tb/spinor-integration.sv','run_vivado.tcl','dump_all_dsp_delay.tcl']:
  assert old.read('spinor-m31/'+name)==new.read('spinor-m31-fix1/'+name),name
pwsh=ROOT/'tools/pwsh/pwsh'
def call(args,label,code=0,env=None):
 run=subprocess.run([str(pwsh),'-NoProfile','-File',*map(str,args)],capture_output=True,text=True,env=env)
 (OUT/(label+'.log')).write_text(run.stdout+run.stderr)
 assert (run.returncode==0)==(code==0),(label,run.stdout,run.stderr)
 return run
fake=OUT/'fake Vivado launcher'
fake.write_text('#!/usr/bin/env python3\nimport sys,pathlib,json,os\na=sys.argv[1:];i=a.index("-tclargs");mode,period,out,threads=a[i+1:];p=pathlib.Path(out);(p/"nested").mkdir();(p/"nested/report.txt").write_text("MOCK_ONLY");(p/"run-summary.txt").write_text("MOCK_ONLY");(p/".Xil").mkdir();(p/".Xil/cache").write_text("OMIT");(p/"xsim.dir").mkdir();(p/"xsim.dir/cache").write_text("OMIT");sys.exit(int(os.getenv("MOCK_EXIT","0")))\n');fake.chmod(0o755)
def check_zip(path):
 with ZipFile(path) as z:
  assert z.testzip() is None;names=z.namelist();assert len(names)==len(set(names))
  assert names.count('output-sha256.json')==1
  assert not any('.Xil/' in n or 'xsim.dir/' in n for n in names)
  assert z.read('nested/report.txt')==b'MOCK_ONLY'
  hashes=json.loads(z.read('output-sha256.json').decode('utf-8-sig'))
  assert 'output-sha256.json' not in hashes
  for n,h in hashes.items():assert hashlib.sha256(z.read(n)).hexdigest()==h,n
cases=[]
for code in [0,7]:
 run=call([work/'run.ps1','-VivadoBat',fake],f'fresh-exit-{code}',code,dict(os.environ,MOCK_EXIT=str(code)))
 path=Path(re.search('Upload this ZIP: (.+)',run.stdout).group(1).strip());check_zip(path)
 out=Path(re.search('Result folder: (.+)',run.stdout).group(1).strip())
 before={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='output-sha256.json'}
 # A pre-existing output manifest must neither hash itself nor be duplicated.
 for repeat in [0,1]:
  dest=OUT/f'recovered-{code}-{repeat}.zip'
  if dest.exists():dest.unlink()
  recovered=call([work/'pack_results.ps1','-RunDirectory',out,'-DestinationZip',dest],f'repack-{code}-{repeat}')
  check_zip(dest)
 after={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='output-sha256.json'}
 assert before==after
 call([work/'pack_results.ps1','-RunDirectory',out,'-DestinationZip',dest],f'existing-destination-{code}',1)
 call([work/'pack_results.ps1','-RunDirectory',out,'-DestinationZip',out/'inside.zip'],f'inside-destination-{code}',1)
 cases.append(dict(native_exit=code,runner_exit=run.returncode,repacked_twice=True,payloads_unchanged=True))
# Both scripts must explicitly load the .NET Framework enum's assembly before
# referring to any Compression type; PS7's implicit loading is insufficient.
for name in ['run.ps1','pack_results.ps1']:
 text=(work/name).read_text();assert text.index('Add-Type -AssemblyName System.IO.Compression\n')<text.index('Add-Type -AssemblyName System.IO.Compression.FileSystem')
files=[Path(__file__).resolve(),ROOT/'scripts/windows_current_bundle.py',*sorted((ROOT/'scripts/windows-current').glob('*')),*sorted(OUT.glob('*.log'))]
result=dict(status='PASS',scope='LINUX_POWERSHELL_7_5_4_MOCK_LAUNCH_AND_REAL_ZIP_RECOVERY; WINDOWS_5_1_NOT_EXECUTED',bundle_sha256=sha(bundle),hardware_Tcl_TB_unchanged=True,cases=cases,
 input_sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2))
