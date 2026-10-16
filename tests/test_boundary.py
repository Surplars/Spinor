#!/usr/bin/env python3
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
out=root/'build/test';out.mkdir(parents=True,exist_ok=True)
tools=root/'tools/oss-cad-suite/bin'
with (out/'ValenceBoundary.compile.log').open('w') as log:
    subprocess.run([str(tools/'iverilog'),'-g2012','-s','tb','-o',str(out/'ValenceBoundary'),
                    str(root/'tests/boundary_tb.sv'),str(root/'build/rtl/ValenceBoundary.sv')],
                   stdout=log,stderr=log,check=True)
run=subprocess.run([str(tools/'vvp'),str(out/'ValenceBoundary')],capture_output=True,text=True)
(out/'ValenceBoundary.log').write_text(run.stdout+run.stderr)
if run.returncode:raise RuntimeError(run.stdout+run.stderr)
print(run.stdout)
