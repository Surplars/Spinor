#!/usr/bin/env python3
"""Pinned Linux-only PowerShell for handoff orchestration checks, not FPGA simulation."""
import hashlib,json,platform,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'tools/pwsh';OUT.mkdir(parents=True,exist_ok=True)
assert platform.system()=='Linux' and platform.machine()=='x86_64','Cloud checker requires Linux x86_64; Windows users only run the supplied run.ps1'
VERSION='7.5.4';EXPECTED='1fd7983fe56ca9e6233f126925edb24bf6b6b33e356b69996d925c4db94e2fef'
URL=f'https://github.com/PowerShell/PowerShell/releases/download/v{VERSION}/powershell-{VERSION}-linux-x64.tar.gz'
target=OUT/'pwsh.tar.gz'
if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=EXPECTED:
 with urllib.request.urlopen(URL) as response:raw=response.read()
 assert hashlib.sha256(raw).hexdigest()==EXPECTED,'PowerShell download hash mismatch';target.write_bytes(raw)
with tarfile.open(target) as t:t.extractall(OUT,filter='data')
(OUT/'pwsh').chmod(0o755)
print('Pinned Linux PowerShell ready',VERSION,EXPECTED)
