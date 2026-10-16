#!/usr/bin/env python3
"""Record a packaging-only repair without rewriting the original M31 evidence."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/m31-fix1';OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=json.loads((ROOT/'reports/m31/receipt.json').read_text())
assert sha(ROOT/'spinor-windows-m31.zip')==base['artifact_sha256']['spinor-windows-m31.zip']
for name,h in base['source_sha256'].items():
 if name.startswith('src/'):assert sha(ROOT/name)==h,name
check_path=ROOT/'build/windows-m31-fix1-validation/results.json';check=json.loads(check_path.read_text());assert check['status']=='PASS'
assert check['scope']=='LINUX_POWERSHELL_7_5_4_MOCK_LAUNCH_AND_REAL_ZIP_RECOVERY; WINDOWS_5_1_NOT_EXECUTED'
assert sha(ROOT/'spinor-windows-m31-fix1.zip')==check['bundle_sha256']
for name,h in check['input_sha256'].items():assert sha(ROOT/name)==h,name
with ZipFile(ROOT/'spinor-windows-m31-fix1.zip') as z:
 assert z.testzip() is None
 for name in ['run.ps1','pack_results.ps1','run_vivado.tcl','RUN_ME_FIRST.txt']:
  assert z.read('spinor-m31-fix1/'+name)==(ROOT/'scripts/windows-current'/name).read_bytes()
source=[Path(__file__).resolve(),ROOT/'scripts/windows_current_bundle.py',ROOT/'tests/test_windows_pack_results.py',ROOT/'docs/m31-windows-fix1.md',*sorted((ROOT/'scripts/windows-current').glob('*'))]
artifacts=[check_path,ROOT/'spinor-windows-m31-fix1.zip',ROOT/'spinor-windows-m31-fix1.zip.sha256',ROOT/'reports/m31/receipt.json',*sorted((ROOT/'build/windows-m31-fix1-validation').glob('*.log'))]
result=dict(status='PASS',milestone='M31-fix1',scope='PACKAGING_ONLY_NO_RTL_OR_TIMING_CHANGE',
 original_M31_commit='2deb1e742e1fdff7bd837a967991c1625d9a51ef',hardware_sources_unchanged=True,validation=check,
 Windows_PowerShell_5_1_execution=False,Vivado_reports_received=False,passes_300MHz=None,passes_500MHz=None,
 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source},artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
(OUT/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS packaging repair; original M31 bundle and RTL preserved')
