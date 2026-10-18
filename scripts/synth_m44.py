#!/usr/bin/env python3
"""Reuse mappings/path reports only when every recorded input/output SHA still matches."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def valid(path,keys):
 try:d=json.loads(path.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return False
 for key in keys:
  if not d.get(key):return False
  for p,h in d[key].items():
   f=ROOT/p
   if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=h:return False
 return True
tops=sys.argv[1:];assert tops
needed=[top for top in tops if not valid(ROOT/f'build/synth/{top}/summary.json',['input_sha256','netlist_sha256'])]
if needed:subprocess.run([sys.executable,'scripts/synth.py',*needed],cwd=ROOT,check=True)
paths=[top for top in tops if not valid(ROOT/f'build/synth/{top}/paths.json',['input_sha256'])]
if paths:subprocess.run([sys.executable,'scripts/path_depth.py',*paths],cwd=ROOT,check=True)
print('Mappings reused',len(tops)-len(needed),'rebuilt',len(needed),'path reports rebuilt',len(paths))
