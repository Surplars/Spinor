#!/usr/bin/env python3
"""Create a current, self-contained Windows XSim + fresh Vivado OOC handoff."""
import argparse,hashlib,json,re
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'spinor-windows-m31.zip');p.add_argument('--prefix',default='spinor-m31');a=p.parse_args()
 assert re.fullmatch(r'[A-Za-z0-9_-]+',a.prefix),'Invalid ZIP prefix'
 files={n:(ROOT/'scripts/windows-current'/n).read_bytes() for n in ['run.ps1','pack_results.ps1','run_vivado.tcl','RUN_ME_FIRST.txt']}
 files.update({f'rtl/{top}.sv':(ROOT/f'build/rtl/{top}.sv').read_bytes() for top in ['SpinorVpu','RamVectorFp']})
 records={}
 for name,stem,rtl in [('extensions','build/integer-extensions/RamVectorFp-smoke-rtl','RamVectorFp'),('integration','build/monitor/integration-spinor/vector-memory-smoke','SpinorVpu')]:
  result=ROOT/(stem+'-results.json');d=json.loads(result.read_text());assert d['status']=='PASS'
  if 'sha256' in d:
   for path,h in d['sha256'].items():assert sha((ROOT/path).read_bytes())==h,path
  else:
   assert d['rtl_or_netlist_sha256']==sha(files[f'rtl/{rtl}.sv'])
   assert d['testbench_sha256']==sha((ROOT/(stem+'-tb.sv')).read_bytes())
  tbname='integer-extensions.sv' if name=='extensions' else 'spinor-integration.sv'
  original=(ROOT/(stem+'-tb.sv')).read_bytes()
  # Source tests intentionally use an abstract 10ns tick plus drive settling.
  # A timescale makes these functional delays explicit for XSim. No SDF claim.
  files['tb/'+tbname]=b'`timescale 1ns/1ps\n'+original
  records[name]={'RTL_sha256':sha(files[f'rtl/{rtl}.sv']),'original_testbench_sha256':sha(original),
    'packaged_testbench_sha256':sha(files['tb/'+tbname]),'cloud_result_sha256':sha(result.read_bytes()),
    'cloud_simulator':'Icarus Verilog; packaged TB replay also required','local_XSim_execution':'NOT_RUN'}
  files[f'evidence/{name}-results.json']=result.read_bytes()
 gate=ROOT/'build/timing-budget/m31-gate/results.json';d=json.loads(gate.read_text());assert d['status']=='PASS'
 for path,h in d['input_sha256'].items():assert sha((ROOT/path).read_bytes())==h,path
 files['evidence/conditional-gate.json']=gate.read_bytes()
 files['dump_all_dsp_delay.tcl']=(ROOT/'third_party/rapidwright/dump_all_dsp_delay.tcl').read_bytes()
 manifest=json.loads((ROOT/'third_party/rapidwright/manifest.json').read_text());assert sha(files['dump_all_dsp_delay.tcl'])==manifest['sha256']
 files['licenses/Apache-2.0.txt']=(ROOT/'third_party/rapidwright/LICENSE').read_bytes()
 files['licenses/berkeley-hardfloat.LICENSE']=(ROOT/'third_party/licenses/berkeley-hardfloat.LICENSE').read_bytes()
 notices=[]
 for src in [*(ROOT/'third_party/berkeley-hardfloat/src/main/scala').glob('*.scala'),*(ROOT/'src/main/scala/vpu').glob('Staged*.scala')]:
  m=re.search(r'/\*={10,}.*?={10,}\*/',src.read_text(),re.S)
  if m and m[0] not in notices:notices.append(m[0])
 files['licenses/HardFloat-source-notices.txt']=('\n\n'.join(notices)+'\n').encode()
 files['provenance.json']=(json.dumps(dict(milestone='M31',runner_revision='M31-fix1',top='SpinorVpu',part='xczu15eg-ffvb1156-2-i',
  tests=records,DSP_exporter=manifest,default_period_ns=3.333333,source_builder_sha256=sha(Path(__file__).read_bytes()),
  Vivado_execution='NOT_RUN',Windows_execution='NOT_RUN',post_route_SDF_simulation='NOT_RUN',
  passes_300MHz=None,passes_500MHz=None,clock_scope='OOC, host IO delays and HD.CLK_SRC unspecified'),indent=2)+'\n').encode()
 files['input-sha256.json']=(json.dumps({n:sha(b) for n,b in sorted(files.items())},indent=2)+'\n').encode()
 target=a.output.resolve();target.parent.mkdir(parents=True,exist_ok=True)
 with ZipFile(target,'w',compression=ZIP_DEFLATED) as z:
  for name,data in sorted(files.items()):z.writestr(a.prefix+'/'+name,data)
 with ZipFile(target) as z:
  assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
  for n,b in files.items():assert z.read(a.prefix+'/'+n)==b
 target.with_suffix('.zip.sha256').write_text(sha(target.read_bytes())+'  '+target.name+'\n')
 print(target,target.stat().st_size,'bytes',sha(target.read_bytes()))
if __name__=='__main__':main()
