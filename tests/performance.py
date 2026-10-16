#!/usr/bin/env python3
"""Checked cycle benchmarks against frozen M7 RTL; no measured device MHz."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
from test_vector import HEADER
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/performance';BIN=ROOT/'tools/oss-cad-suite/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 global OUT
 p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,default=ROOT/'archive/m7/rtl/RamVectorFp.sv')
 p.add_argument('--current',type=Path,default=ROOT/'build/rtl/RamVectorFp.sv');p.add_argument('--baseline-label',default='M7');p.add_argument('--current-label',default='M8');p.add_argument('--current-top',default='RamVectorFp');p.add_argument('--output',type=Path,default=OUT);a=p.parse_args();OUT=a.output;OUT.mkdir(parents=True,exist_ok=True)
 header=HEADER.replace('wire [4:0] io_vl;','wire [7:0] io_vl;wire [6:0] io_vstart;wire [1:0] io_vxrm;wire io_vxsat;wire [31:0] io_versions;wire [2:0] io_frm;wire [4:0] io_fflags;')
 header=header.replace('input [4:0] expectedVl','input [7:0] expectedVl').replace('1000000','4000000')
 lines=[header];cases=[];repeats=8
 def ctx(reg,value,write=True):
  for k in range(2):
   v=(value>>(64*k))&((1<<64)-1);lines.append(f"ctx({2*reg+k},1'b{int(write)},64'h{v:x},64'h{v:x});")
 def command(inst,vl,t,scalar=0,result=0,wr=False):
  return f"command(32'h{inst:x},64'h{scalar:x},0,{vl},0,0,{result},{int(wr)},0,{vl},64'h{t:x});"
 def case(sew,lmul,vl,density,name,form=0):
  w=8<<sew;n=1<<lmul;maximum=(128//w)*n;t=(sew<<3)|lmul;vm=int(density=='all')
  mask=(1<<128)-1 if density=='all' else sum(1<<e for e in range(0,128,2)) if density=='half' else 0
  active=sum(1 for e in range(vl) if vm or mask>>e&1)
  fp=name=='vfadd';one=(0x3f800000 if sew==2 else 0x3ff0000000000000) if fp else 1
  initial=one if fp else 32 if name=='vdivu' else 0 if name!='vmul' else 3
  source=one if fp else 2 if name in ['vmul','vdivu'] else 1
  ctx(0,mask)
  for j in range(n):
   ctx(16+j,sum(source<<(e*w) for e in range(128//w)))
   ctx(24+j,sum(initial<<(e*w) for e in range(128//w)))
  lines.append(command((t<<20)|(1<<15)|(7<<12)|(3<<7)|0x57,vl,t,result=vl,wr=True))
  f6={'vadd':0,'vxor':0x0b,'vmul':0x25,'vdivu':0x20,'vfadd':0}[name]
  f3=1 if fp else 2 if name in ['vmul','vdivu'] else form
  inst=(f6<<26)|(vm<<25)|(24<<20)|(16<<15)|(f3<<12)|(24<<7)|0x57
  ident=len(cases);lines.append(f'begin: b{ident} integer start,k;start=cycles;')
  lines.append(f'for(k=0;k<{repeats};k=k+1) '+command(inst,vl,t,scalar=source))
  lines.append(f'$display("PERF {ident} %0d",cycles-start);end')
  expected=[]
  for e in range(maximum):
   x=initial
   if e<vl and (vm or mask>>e&1):
    for _ in range(repeats):
     if name=='vadd':x=(x+source)&((1<<w)-1)
     elif name=='vxor':x^=source
     elif name=='vmul':x=(x*source)&((1<<w)-1)
     elif name=='vdivu':x//=source
     else:
      value=float(1+repeats);x=int.from_bytes(struct.pack('<f' if sew==2 else '<d',value),'little')
   expected.append(x)
  for j in range(n):ctx(24+j,sum(expected[j*(128//w)+k]<<(w*k) for k in range(128//w)),False)
  cases.append(dict(id=ident,operation=name,form='vx' if form==4 else 'vv',sew=w,lmul=n,vl=vl,mask=density,active_elements=active,instructions=repeats))
 for sew in range(4):
  for lmul in range(4):
   for vl in sorted({1,(128//(8<<sew))*(1<<lmul)}):
    for density in ['all','half','none']:
     for form in [0,4]:case(sew,lmul,vl,density,'vadd',form)
 for sew in range(4):
  for lmul in [0,3]:
   for name in ['vxor','vmul','vdivu']+(['vfadd'] if sew>=2 else []):
    case(sew,lmul,(128//(8<<sew))*(1<<lmul),'all',name)
 lines.append('$display("PASS checked performance cases");$finish;end endmodule')
 tb=OUT/'performance-tb.sv';tb.write_text('\n'.join(lines));results={}
 for label,rtl in [(a.baseline_label,a.baseline),(a.current_label,a.current)]:
  exe=OUT/label
  with (OUT/(label+'.compile.log')).open('w') as log:
   subprocess.run([str(BIN/'iverilog'),'-g2012','-s','tb',f'-DTOP={a.current_top if label==a.current_label else "RamVectorFp"}','-o',str(exe),str(tb),str(rtl)],stdout=log,stderr=log,check=True)
  run=subprocess.run([str(BIN/'vvp'),str(exe)],capture_output=True,text=True,check=True);(OUT/(label+'.log')).write_text(run.stdout+run.stderr)
  ticks={int(s[1]):int(s[2]) for line in run.stdout.splitlines() if line.startswith('PERF ') for s in [line.split()]}
  assert len(ticks)==len(cases) and 'PASS checked performance cases' in run.stdout
  data=[]
  for c in cases:
   total=ticks[c['id']];active=c['active_elements']*repeats
   data.append({**c,'cycles':total,'cycles_per_instruction':total/repeats,
    'cycles_per_active_element':total/active if active else None,'active_elements_per_cycle':active/total,
    'hypothetical_Melements_per_second_at_300MHz':active/total*300})
  results[label]=dict(rtl_sha256=sha(rtl),cases=data);print(label,'PASS',len(data),'checked cases',flush=True)
 report=dict(scope='SIMULATED_CYCLES_WITH_CHECKED_RESULTS_NO_DEVICE_FREQUENCY_OR_MEMORY_BANDWIDTH',
  testbench_sha256=sha(tb),benchmark_source_sha256=sha(Path(__file__)),clock_assumption_MHz=300,results=results)
 (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 for w in [8,16,32,64]:
  for form in ['vv','vx']:
   old=next(c for c in results[a.baseline_label]['cases'] if c['operation']=='vadd' and c['sew']==w and c['lmul']==8 and c['vl']==1024//w and c['mask']=='all' and c['form']==form)
   new=results[a.current_label]['cases'][old['id']]
   print(w,form,old['cycles_per_instruction'],new['cycles_per_instruction'],'speedup',round(old['cycles']/new['cycles'],3))
if __name__=='__main__':main()
