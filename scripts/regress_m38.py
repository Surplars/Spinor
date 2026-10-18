#!/usr/bin/env python3
"""Bounded parallel test families; each family's full/smoke variants remain ordered."""
import argparse,concurrent.futures,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/m38-regression';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--mapped',action='store_true');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
(OUT/('mapped.json' if a.mapped else 'rtl.json')).unlink(missing_ok=True)
py=sys.executable
def variants(test):return [[test],[test,'--smoke'],[test,'--smoke','--top','RamVector'],[test,'--smoke','--top','RamVector16']]
groups={}
if a.mapped:
 groups['m38-new']=[['test_m38_fixed.py','--compact','--mapped']]
 groups['clip-unit']=[['test_clip_lane.py','--compact','--mapped']]
 groups['fractional-unit']=[['test_fractional_lane.py','--compact','--mapped']]
 groups['new-fixed']=[['test_m37_fixed.py','--compact','--mapped']]
 groups['fixed-unit']=[['test_fixed_point_lane.py','--compact','--mapped']]
 for test,opts in [('test_m36_integer.py',['--compact']),('test_integer_mac_netlist.py',[]),('test_reduction_interleave.py',[]),('test_vector_memory.py',['--smoke']),('test_monitored_memory.py',['--spinor','--smoke']),('test_monitor.py',[])]:groups[test]=[[test,*opts,'--mapped']]
else:
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
def run(item):
 name,cmds=item;records=[]
 for i,cmd in enumerate(cmds):
  log=OUT/(name+('-mapped' if a.mapped else '-rtl')+f'-{i}.log');t=time.monotonic()
  with log.open('w') as f:r=subprocess.run([py,'tests/'+cmd[0],*cmd[1:]],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
  records.append(dict(args=cmd,exit_code=r.returncode,seconds=round(time.monotonic()-t,2),log=str(log.relative_to(ROOT))))
  print(name,i,r.returncode,flush=True)
  if r.returncode:break
 return name,records
with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:results=dict(pool.map(run,groups.items()))
(OUT/('mapped.json' if a.mapped else 'rtl.json')).write_text(json.dumps(results,indent=2)+'\n')
assert all(x['exit_code']==0 for rows in results.values() for x in rows), 'See family logs'
