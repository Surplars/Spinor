#!/usr/bin/env python3
"""Conservative M42 evidence reuse: exact arithmetic RTL, dependencies and artifacts."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED_TESTS={'tests/test_vector_memory.py','tests/test_monitored_memory.py','tests/test_monitor.py','tests/test_profiles.py'}
PARENT_NAMES=('Lishi','Spinor','VectorMemoryEngine','VpuMonitor')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(out):
 frozen=ROOT/'archive/m42/reports/receipt.json';base=json.loads(frozen.read_text());inputs={str(frozen.relative_to(ROOT)):sha(frozen),str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__).resolve())}
 candidates={}
 for p,h in base['source_sha256'].items():
  if p.startswith(('third_party/','software/')) or p in ['tools.lock.json','.mill-version','build.mill','scripts/synth.py'] or p.startswith('tests/') and p not in EXCLUDED_TESTS or p.startswith('src/') and Path(p).name not in ['VectorMemoryEngine.scala','VpuMonitor.scala','GenerateConfigured.scala']:
   candidates[p]=h
 for p,h in base['artifact_sha256'].items():
  if p.startswith('build/rtl/'):
   if any(name in Path(p).name for name in PARENT_NAMES):continue
   candidates[p]=h;continue
  if not p.startswith('build/'):continue
  if p=='build/synth/summary.json' or p.startswith(('build/monitor/','build/configuration/','build/profiles/','build/timing-budget/','build/baseline-','build/rapidwright/','build/test/vector-memory','build/test/cloud-budget')) or '-proof/' in p or 'regeneration' in p:continue
  if p.startswith('build/synth/') and p.split('/')[2].startswith(PARENT_NAMES):continue
  candidates[p]=h
 missing=[]
 for p,h in candidates.items():
  f=ROOT/p
  if not f.is_file() or sha(f)!=h:missing.append(p)
  else:inputs[p]=h
 used=not missing
 if not used:inputs={p:h for p,h in inputs.items() if not p.startswith('build/')}
 result=dict(status='PASS',scope='EXACT_M42_ARITHMETIC_RTL_DEPENDENCIES_AND_PUBLISHED_ARTIFACTS; MEMORY_MONITOR_PRESETS_ALWAYS_RERUN',cache_available=used,checked_files=len(candidates),mismatches=missing,input_sha256=inputs)
 out.mkdir(parents=True,exist_ok=True);(out/'reuse-inputs.json').write_text(json.dumps(result,indent=2)+'\n')
 print('M42 arithmetic cache', 'VALID' if used else 'MISS',len(candidates),'files',missing[:8],flush=True)
 return used,base
