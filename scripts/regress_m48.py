#!/usr/bin/env python3
"""Bounded parallel test families; each family's full/smoke variants remain ordered."""
import argparse,concurrent.futures,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m48-regression';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');p.add_argument('--only',help='Comma-separated completed ledger groups to replace');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
ledger=OUT/('mapped.json' if a.mapped else 'rtl.json')
prior=json.loads(ledger.read_text()) if a.only else {}
if not a.only:ledger.unlink(missing_ok=True)
py=sys.executable
from reuse_m48 import validate
cache,base42=validate(OUT)
old_ledger=ROOT/('build/m42-regression/mapped.json' if a.mapped else 'build/m42-regression/rtl.json')
old=json.loads(old_ledger.read_text()) if cache else {}
uncached={'host-boundary','memory-boundary','memory','public','monitor','test_vector_memory.py','test_monitored_memory.py','test_monitor.py','SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep'}
def variants(test):return [[test],[test,'--smoke'],[test,'--smoke','--top','RamVector'],[test,'--smoke','--top','RamVector16']]
groups={}
if a.mapped:
 groups['fp-wide-core']=[['test_fp_widen_arithmetic.py','--compact','--mapped'],['test_fp_widen_arithmetic.py','--compact','--mapped','--top','RamVectorFp16']]
 groups['fp-wide-unit']=[['test_fp_widen_arithmetic_lane.py','--compact','--mapped']]
 groups['fp-native']=[['test_fp_lane.py','--widen-native','--smoke','--mapped']]
 groups['fp-old-wide']=[['test_fp_widen_lane.py','--smoke','--mapped']]
 groups['fp-transfers']=[['test_fp_transfers.py','--compact','--mapped'],['test_fp_transfers.py','--compact','--mapped','--top','RamVectorFp16']]
 for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:groups[top]=[['test_profiles.py','--top',top,'--mapped']]
 groups['m38-new']=[['test_m38_fixed.py','--compact','--mapped']]
 groups['clip-unit']=[['test_clip_lane.py','--compact','--mapped']]
 groups['fractional-unit']=[['test_fractional_lane.py','--compact','--mapped']]
 groups['new-fixed']=[['test_m37_fixed.py','--compact','--mapped']]
 groups['fixed-unit']=[['test_fixed_point_lane.py','--compact','--mapped']]
 for test,opts in [('test_m36_integer.py',['--compact']),('test_integer_mac_netlist.py',[]),('test_reduction_interleave.py',[]),('test_vector_memory.py',['--smoke']),('test_monitored_memory.py',['--spinor','--smoke']),('test_monitor.py',[])]:groups[test]=[[test,*opts,'--mapped']]
else:
 groups['fp-wide-core']=[['test_fp_widen_arithmetic.py'],['test_fp_widen_arithmetic.py','--compact'],['test_fp_widen_arithmetic.py','--compact','--top','RamVectorFp16'],['test_fp_widen_arithmetic.py','--compact','--top','RamVector'],['test_fp_widen_arithmetic.py','--compact','--top','RamVector16']]
 groups['fp-wide-unit']=[['test_fp_widen_arithmetic_lane.py'],['test_fp_widen_arithmetic_lane.py','--compact']]
 groups['fp-native']=[['test_fp_lane.py','--widen-native'],['test_fp_lane.py','--widen-native','--smoke']]
 groups['fp-old-wide']=[['test_fp_widen_lane.py'],['test_fp_widen_lane.py','--smoke']]
 groups['fp-transfers']=[['test_fp_transfers.py'],['test_fp_transfers.py','--compact'],['test_fp_transfers.py','--compact','--top','RamVectorFp16'],['test_fp_transfers.py','--compact','--top','RamVector'],['test_fp_transfers.py','--compact','--top','RamVector16']]
 for top in ['SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep']:groups[top]=[['test_profiles.py','--top',top]]
 groups['m38-new']=[['test_m38_fixed.py'],['test_m38_fixed.py','--compact'],['test_m38_fixed.py','--compact','--top','RamVector'],['test_m38_fixed.py','--compact','--top','RamVector16']]
 groups['clip-unit']=[['test_clip_lane.py'],['test_clip_lane.py','--compact']]
 groups['fractional-unit']=[['test_fractional_lane.py'],['test_fractional_lane.py','--compact']]
 groups['new-fixed']=[['test_m37_fixed.py'],['test_m37_fixed.py','--compact'],['test_m37_fixed.py','--compact','--top','RamVector'],['test_m37_fixed.py','--compact','--top','RamVector16']]
 groups['fixed-unit']=[['test_fixed_point_lane.py'],['test_fixed_point_lane.py','--compact']]
 for test in ['test_widening_mac.py','test_integer_mac.py','test_widening_multiply.py','test_widening_arithmetic.py','test_narrowing_shifts.py','test_integer_extensions.py','test_fp_widening_reductions.py','test_widening_reductions.py','test_fp_reductions.py','test_compress.py','test_gather.py','test_slide.py','test_index_generate.py','test_mask_prefix.py']:groups[test]=variants(test)
 groups['new-integer']=[['test_m36_integer.py'],['test_m36_integer.py','--compact'],['test_m36_integer.py','--compact','--top','RamVector'],['test_m36_integer.py','--compact','--top','RamVector16']]
 groups['mask-alias']=[['test_mask_source_alias.py','--top',t] for t in ['RamVectorFp','RamVector','RamVector16']]
 for test in ['test_mask_scalar.py','test_mask_scan.py','test_reductions.py','test_streaming.py','test_reduction_interleave.py','test_integer_mac_netlist.py','test_monitor_client.py']:groups[test]=[[test]]
 groups['integer']=[['test_ram_vector.py','--fp','--multiply','--divide'],['test_ram_vector.py']]
 groups['fp']=[['test_fp_vector.py','--convert','--multiply','--divide']]
 groups['memory']=[['test_vector_memory.py'],['test_vector_memory.py','--smoke']]
 groups['public']=[['test_monitored_memory.py','--spinor'],['test_monitored_memory.py','--spinor','--smoke']]
 groups['monitor']=[['test_monitor.py'],['test_monitor.py','--tiny']]
groups['resize-core']=[['test_fp_resize.py','--compact','--mapped'],['test_fp_resize.py','--compact','--mapped','--top','RamVectorFp16']] if a.mapped else [['test_fp_resize.py'],['test_fp_resize.py','--compact'],['test_fp_resize.py','--compact','--top','RamVectorFp16'],['test_fp_resize.py','--compact','--top','RamVector'],['test_fp_resize.py','--compact','--top','RamVector16']]
groups['resize-unit']=[['test_fp_resize_lane.py','--compact','--mapped'],['test_fp_resize_lane.py','--compact','--lane','--mapped']] if a.mapped else [['test_fp_resize_lane.py'],['test_fp_resize_lane.py','--compact'],['test_fp_resize_lane.py','--lane'],['test_fp_resize_lane.py','--compact','--lane']]
groups['resize-wide']=[['test_fp_widen_arithmetic_lane.py','--resize','--compact','--mapped']] if a.mapped else [['test_fp_widen_arithmetic_lane.py','--resize'],['test_fp_widen_arithmetic_lane.py','--resize','--compact']]
groups['resize-native']=[['test_fp_lane.py','--resize-native','--smoke','--mapped']] if a.mapped else [['test_fp_lane.py','--resize-native'],['test_fp_lane.py','--resize-native','--smoke']]
groups['estimate-core']=[['test_fp_estimate.py','--compact','--mapped'],['test_fp_estimate.py','--compact','--mapped','--top','RamVectorFp16']] if a.mapped else [['test_fp_estimate.py'],['test_fp_estimate.py','--compact'],['test_fp_estimate.py','--compact','--top','RamVectorFp16'],['test_fp_estimate.py','--compact','--top','RamVector'],['test_fp_estimate.py','--compact','--top','RamVector16']]
groups['estimate-unit']=[['test_fp_estimate_lane.py','--compact','--mapped']] if a.mapped else [['test_fp_estimate_lane.py'],['test_fp_estimate_lane.py','--compact']]
if not a.mapped:groups['conversion-efficiency']=[['test_conversion_efficiency.py']]
groups['strided-engine']=[['test_strided_engine.py','--mapped'],['test_strided_engine.py','--compact','--mapped']] if a.mapped else [['test_strided_engine.py'],['test_strided_engine.py','--compact']]
groups['strided-memory']=[['test_strided_memory.py','--smoke','--mapped'],['test_strided_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_strided_memory.py'],['test_strided_memory.py','--smoke'],['test_strided_memory.py','--smoke','--top','LishiVpuMemory16']]
if not a.mapped:groups['memory-efficiency']=[['test_memory_efficiency.py']]
groups['indexed-engine']=[['test_indexed_engine.py','--mapped'],['test_indexed_engine.py','--compact','--mapped']] if a.mapped else [['test_indexed_engine.py'],['test_indexed_engine.py','--compact']]
groups['indexed-memory']=[['test_indexed_memory.py','--smoke','--mapped'],['test_indexed_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_indexed_memory.py'],['test_indexed_memory.py','--smoke'],['test_indexed_memory.py','--smoke','--top','LishiVpuMemory16']]
groups['context-engine']=[['test_context_memory_engine.py','--mapped'],['test_context_memory_engine.py','--compact','--mapped']] if a.mapped else [['test_context_memory_engine.py'],['test_context_memory_engine.py','--compact']]
groups['context-memory']=[['test_context_memory.py','--smoke','--mapped'],['test_context_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_context_memory.py'],['test_context_memory.py','--smoke'],['test_context_memory.py','--smoke','--top','LishiVpuMemory16']]
groups['segment-engine']=[['test_segment_engine.py','--mapped'],['test_segment_engine.py','--compact','--mapped']] if a.mapped else [['test_segment_engine.py'],['test_segment_engine.py','--compact']]
groups['segment-memory']=[['test_segment_memory.py','--smoke','--mapped'],['test_segment_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_segment_memory.py'],['test_segment_memory.py','--smoke'],['test_segment_memory.py','--smoke','--top','LishiVpuMemory16']]
groups['addressed-segment-engine']=[['test_addressed_segment_engine.py','--mapped'],['test_addressed_segment_engine.py','--compact','--mapped']] if a.mapped else [['test_addressed_segment_engine.py'],['test_addressed_segment_engine.py','--compact']]
groups['addressed-segment-memory']=[['test_addressed_segment_memory.py','--smoke','--mapped'],['test_addressed_segment_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_addressed_segment_memory.py'],['test_addressed_segment_memory.py','--smoke'],['test_addressed_segment_memory.py','--smoke','--top','LishiVpuMemory16']]
groups['fof-engine']=[['test_fof_engine.py','--mapped'],['test_fof_engine.py','--compact','--mapped']] if a.mapped else [['test_fof_engine.py'],['test_fof_engine.py','--compact']]
groups['fof-memory']=[['test_fof_memory.py','--smoke','--mapped'],['test_fof_memory.py','--smoke','--mapped','--top','LishiVpuMemory16']] if a.mapped else [['test_fof_memory.py'],['test_fof_memory.py','--smoke'],['test_fof_memory.py','--smoke','--top','LishiVpuMemory16']]
groups['host-boundary']=[['test_host_boundary.py','--mapped']] if a.mapped else [['test_host_boundary.py']]
groups['memory-boundary']=[['test_memory_boundary.py','--mapped']] if a.mapped else [['test_memory_boundary.py']]
# Exercise changed hardware first; preserve ordered variants within each family.
priority=['host-boundary','memory-boundary','fof-engine','fof-memory','test_monitored_memory.py','public','addressed-segment-engine','addressed-segment-memory','segment-engine','segment-memory','context-engine','context-memory','indexed-engine','indexed-memory','strided-engine','strided-memory','memory-efficiency','estimate-unit','estimate-core','conversion-efficiency','resize-unit','resize-core','resize-native','resize-wide',
 'SpinorStandard','SpinorDeep','SpinorInteger','SpinorIntegerDeep','public','monitor','test_monitored_memory.py','test_monitor.py']
groups={k:groups[k] for k in priority if k in groups}|{k:v for k,v in groups.items() if k not in priority}
if a.only:
 selected=set(a.only.split(','));assert selected<=groups.keys(),selected-groups.keys()
 groups={k:v for k,v in groups.items() if k in selected}
def run(item):
 name,cmds=item;records=[]
 if cache and name not in uncached and name in old and [x['args'] for x in old[name]]==cmds:
  assert all(x['exit_code']==0 for x in old[name])
  rows=[dict(x,reused_from='M42',original_ledger=str(old_ledger.relative_to(ROOT))) for x in old[name]]
  print(name,'REUSED',len(rows),flush=True);return name,rows
 for i,cmd in enumerate(cmds):
  log=OUT/(name+('-mapped' if a.mapped else '-rtl')+f'-{i}.log');t=time.monotonic()
  with log.open('w') as f:r=subprocess.run([py,'tests/'+cmd[0],*cmd[1:]],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  records.append(dict(args=cmd,exit_code=r.returncode,seconds=round(time.monotonic()-t,2),log=str(log.relative_to(ROOT))))
  print(name,i,r.returncode,flush=True)
  if r.returncode:break
 return name,records
# Save each completed family atomically. --only can replace selected families
# after interruption; the report still requires the entire successful matrix.
results=dict(prior)
def save():
 temporary=ledger.with_suffix('.tmp');temporary.write_text(json.dumps(results,indent=2)+'\n');temporary.replace(ledger)
# Check reset-to-first-fault ownership/progress before launching long memories.
for early in ['host-boundary','memory-boundary']:
 if early in groups:
  name,records=run((early,groups.pop(early)));results[name]=records;save()
  assert all(x['exit_code']==0 for x in records),'Boundary preflight failed; see family logs'
with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
 futures=[pool.submit(run,item) for item in groups.items()]
 for future in concurrent.futures.as_completed(futures):
  name,records=future.result();results[name]=records
  save()
assert all(x['exit_code']==0 for rows in results.values() for x in rows), 'See family logs'
