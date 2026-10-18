#!/usr/bin/env python3
"""Generate four production presets using Mill; no global Scala parameters."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILES={'standard':'SpinorStandard','deep':'SpinorDeep','integer':'SpinorInteger','integer-deep':'SpinorIntegerDeep'}
def main():
 for preset,top in PROFILES.items():
  subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateConfigured','--out','build/rtl','--name',top,'--preset',preset],cwd=ROOT,check=True)
if __name__=='__main__':main()
