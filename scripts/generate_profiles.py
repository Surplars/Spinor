#!/usr/bin/env python3
"""Generate four production presets using Mill; no global Scala parameters."""
import hashlib,json,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILE_ROOT=ROOT/'build/profiles/rtl'
PROFILES={'standard':'SpinorStandard','deep':'SpinorDeep','integer':'SpinorInteger','integer-deep':'SpinorIntegerDeep'}
def main():
 for preset,top in PROFILES.items():
  out=PROFILE_ROOT/top
  subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateConfigured','--out',str(out),'--name',top,'--preset',preset],cwd=ROOT,check=True)
  # Shared helper module names differ across presets. Keep their layers local.
  # Flat top/manifest copies preserve existing simulation and synthesis paths.
  for ext in ['sv','json']:shutil.copy2(out/f'{top}.{ext}',ROOT/f'build/rtl/{top}.{ext}')
if __name__=='__main__':main()
