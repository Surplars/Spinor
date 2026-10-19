#!/usr/bin/env python3
"""Family-cell and explicit interconnect sensitivity budget; NEVER device STA."""
import argparse,hashlib,json,gzip
from collections import Counter,defaultdict,deque
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def family():
 spec=json.loads((ROOT/'tools.lock.json').read_text())['rapidwright']['artifact']
 jar=ROOT/'tools/rapidwright-research'/spec['url'].rsplit('/',1)[1]
 assert sha(jar)==spec['sha256']
 name='timing/ultrascaleplus/intrasite_delay_terms.txt'
 with ZipFile(jar) as z:raw=z.read(name)
 sections=defaultdict(list);bel=''
 for line in raw.decode().splitlines():
  f=line.split()
  if not f or f[0].startswith('#'):continue
  if f[0]=='bel':bel=f[1].split(',')[0];continue
  if f[0]=='site':bel='';continue
  if len(f)>=3:
   try:v=int(f[2])
   except ValueError:continue
   sections[bel].append((f[0],f[1],v))
 lut=max(v for a,b,v in sections['A6LUT'] if a.startswith('A') and b=='O6')
 carry=max(v for a,b,v in sections['CARRY8'] if v>=0)
 ram=max(v for a,b,v in sections['A5LUT']+sections['A6LUT'] if a.startswith('A') and b in ['O5','O6'])
 cq=next(v for a,b,v in sections['AFF'] if a=='CLK' and b=='Q')
 return dict(LUT=lut,CARRY4=carry,RAM_READ=ram,CQ=cq,SETUP_ASSUMPTION=100),dict(jar_sha256=sha(jar),table_sha256=hashlib.sha256(raw).hexdigest())
def analyze(path,top,out):
 out.mkdir(parents=True,exist_ok=True)
 for name in ["budget.json","budget.md"]:(out/name).unlink(missing_ok=True)
 weights,provenance=family();m=json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())['modules'][top];orig=m['cells']
 ff={n:c for n,c in orig.items() if c['type'].startswith(('FDRE','FDSE','FDCE','FDPE'))}
 ram={n:c for n,c in orig.items() if c['type'].startswith('RAM')}
 dsp={n:c for n,c in orig.items() if c['type']=='DSP48E2'}
 for c in dsp.values():assert not any(int(v,2) for k,v in c['parameters'].items() if k.endswith('REG'))
 comb={n:c for n,c in orig.items() if n not in ff and n not in ram and c['type']!='$scopeinfo'}
 for n,c in ram.items():
  assert c['type'] in ['RAM32M16','RAM64M8','RAM32M','RAM64M']
  for p,d in c['port_directions'].items():
   if d=='output':
    a='ADDR'+p[2:];comb[n+'.'+p]={'type':'RAM_READ','port_directions':{a:'input',p:'output'},'connections':{a:c['connections'][a],p:c['connections'][p]}}
 def inputs(c):return [b for p,d in c['port_directions'].items() if d=='input' for b in c['connections'][p] if isinstance(b,int)]
 def outputs(c):return [b for p,d in c['port_directions'].items() if d=='output' for b in c['connections'][p] if isinstance(b,int)]
 driver={b:n for n,c in comb.items() for b in outputs(c)}
 deps={n:{driver[b] for b in inputs(c) if b in driver} for n,c in comb.items()};nexts=defaultdict(list)
 for n,ds in deps.items():
  for d in ds:nexts[d].append(n)
 indegree={n:len(d) for n,d in deps.items()};q=deque(n for n,d in indegree.items() if not d);order=[]
 while q:
  n=q.popleft();order.append(n)
  for x in nexts[n]:
   indegree[x]-=1
   if not indegree[x]:q.append(x)
 assert len(order)==len(comb),'combinational cycle'
 aliases=defaultdict(list)
 for n,v in m['netnames'].items():
  if not n.startswith('$'):
   for i,b in enumerate(v['bits']):
    if isinstance(b,int):aliases[b].append(f'{n}[{i}]')
 def label(bits,fallback):return next((aliases[b][0] for b in bits if aliases[b]),fallback)
 scenarios=[]
 for link in [50,100,200]:
  paths={};taint=set()
  for n,c in ff.items():
   for b in c['connections']['Q']:paths[b]=(weights['CQ'],label([b],n),[])
  for n,c in ram.items():
   for b in outputs(c):paths[b]=(312,n+'.stored-data',[]) # family LUTRAM CLK->O6; no write setup checks
  for n in order:
   c=comb[n];ins=inputs(c);outs=outputs(c);typ=c['type']
   if typ=='DSP48E2' or any(b in taint for b in ins):taint.update(outs)
   if typ=='DSP48E2':continue # NEVER use old-instance DSP tables on a new unplaced DSP
   if typ.startswith(('LUT','INV','BUF')):delay=weights['LUT']
   elif typ.startswith('MUXF'):delay=77
   elif typ=='CARRY4':delay=weights['CARRY4'] # deliberately uses worst full CARRY8 arc, not a CARRY4 calibration
   elif typ=='RAM_READ':delay=weights['RAM_READ']
   else:raise ValueError('unsupported primitive '+typ)
   candidates=[paths[b] for b in ins if b in paths]
   if candidates:
    t,start,chain=max(candidates,key=lambda x:x[0]);value=(t+delay+link,start,chain+[(n,typ)])
    for b in outs:
     if b not in paths or value[0]>paths[b][0]:paths[b]=value
  endpoints=[];uncovered=0
  for n,c in ff.items():
   for p in ['D','CE','R','S','CLR','PRE']:
    for b in c['connections'].get(p,[]):
     if b in taint:uncovered+=1;continue
     if b in paths:
      t,start,chain=paths[b];total=t+link+weights['SETUP_ASSUMPTION']
      endpoints.append(dict(budget_ns=total/1000,start=start,end=label(c['connections']['Q'],n)+'.'+p,kind='data' if p=='D' else 'control',hops=len(chain),types=dict(Counter(t for _,t in chain)),chain=[dict(cell=n,type=t) for n,t in chain],budget_residual_300MHz_ns=1000/300-total/1000,budget_residual_500MHz_ns=2-total/1000))
  endpoints.sort(key=lambda x:x['budget_ns'],reverse=True)
  scenarios.append(dict(assumed_link_ps=link,DSP_tainted_endpoints_excluded=uncovered,covered_endpoint_count=len(endpoints),worst=endpoints[0],top_paths=endpoints[:10]))
 result=dict(scope='UNPLACED_FAMILY_MAX_CELL_AND_ASSUMED_LINK_BUDGET_NOT_STA',top=top,weights_ps=weights,scenarios=scenarios,provenance=provenance,input_sha256={str(path):sha(path),'scripts/cloud_budget_m56.py':sha(Path(__file__))},uncharacterized_DSP_cells=len(dsp),speed_grade_calibrated=False,placed=False,routed=False,passes_300MHz=None,passes_500MHz=None,limitations=['worst cell-class arcs independent of mapped pin and LUT permutation','CARRY4 charged worst full CARRY8 arc','link delay assumptions are not calibrated routing','FF setup 100ps assumed; no hold, clock, recovery or memory-write checks','primary input/output paths excluded','DSP-tainted endpoints excluded; not full VPU coverage'])
 out.mkdir(parents=True,exist_ok=True);(out/'budget.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# 云端条件延迟预算','','这是未布局网表的连线敏感性分析，不是 STA 或 Fmax。RapidWright 家族表提供单元参考，50/100/200 ps 每段连线及100 ps建立预算为显式假设。DSP相关端点排除，CARRY4保守计完整CARRY8最慢弧；没有针对 -2 校准。','', '| 每段假设连线ps | 最大预算ns | 300MHz预算余量ns | 500MHz预算余量ns | 排除DSP相关端点 |','|---:|---:|---:|---:|---:|']
 for s in scenarios:
  w=s['worst'];lines.append(f"| {s['assumed_link_ps']} | {w['budget_ns']:.3f} | {w['budget_residual_300MHz_ns']:.3f} | {w['budget_residual_500MHz_ns']:.3f} | {s['DSP_tainted_endpoints_excluded']} |")
 lines+=['','余量只表示该假设下的算术差值，不是 WNS；负值提示应切分的候选链，正值不能说明通过频率。路径和SHA见 budget.json。']
 (out/'budget.md').write_text('\n'.join(lines)+'\n')
 for s in scenarios:print(top,s['assumed_link_ps'],'ps/link',s['worst']['budget_ns'],'ns',s['worst']['start'],'->',s['worst']['end'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,required=True);p.add_argument('--top',default='LishiVpuMemory');p.add_argument('--output',type=Path,required=True);a=p.parse_args();analyze(a.netlist,a.top,a.output)
