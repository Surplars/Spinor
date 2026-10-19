#!/usr/bin/env python3
"""Independent SoftFloat wrapper for legacy and new half resize cases."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
soft=ROOT/'tools/fp/softfloat';out=ROOT/'build/m54/reference';out.mkdir(parents=True,exist_ok=True)
subprocess.run(['gcc','-std=c11','-O2','-fPIC','-shared','-I'+str(soft/'source/include'),ROOT/'tests/fp_resize_reference_m54.c',soft/'build/Linux-x86_64-GCC/softfloat.a','-o',out/'libresize.so'],cwd=ROOT,check=True)
