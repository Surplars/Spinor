#!/usr/bin/env python3
"""Build the M5 Windows handoff from verified RTL and the proven fix3 runner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT.parent/'zu15-vpu-windows-m5.zip')
    a=p.parse_args();receipt=ROOT/'reports/m5/receipt.json'
    if not receipt.exists():raise SystemExit('Generate reports/m5 first')
    result=json.loads(receipt.read_text())
    for field in ['source_sha256','artifact_sha256']:
        for rel,h in result[field].items():
            if sha((ROOT/rel).read_bytes())!=h:raise SystemExit('Changed since M5 report: '+rel)
    files={n:(ROOT/'scripts/windows'/n).read_bytes() for n in ['run.ps1','run_vivado.tcl','RUN_ME_FIRST.txt']}
    files.update({'rtl/RamVectorFp.sv':(ROOT/'build/rtl/RamVectorFp.sv').read_bytes(),
       'dump_all_dsp_delay.tcl':(ROOT/'third_party/rapidwright/dump_all_dsp_delay.tcl').read_bytes(),
       'licenses/Apache-2.0.txt':(ROOT/'third_party/rapidwright/LICENSE').read_bytes(),
       'licenses/berkeley-hardfloat.LICENSE':(ROOT/'third_party/licenses/berkeley-hardfloat.LICENSE').read_bytes()})
    notices=[]
    for src in [*(ROOT/'third_party/berkeley-hardfloat/src/main/scala').glob('*.scala'),*(ROOT/'src/main/scala/vpu').rglob('Staged*.scala')]:
        m=re.search(r'/\*={10,}.*?={10,}\*/',src.read_text(),re.S)
        if m and m[0] not in notices:notices.append(m[0])
    files['licenses/HardFloat-source-notices.txt']=('\n\n'.join(notices)+'\n').encode()
    exporter=json.loads((ROOT/'third_party/rapidwright/manifest.json').read_text())
    assert sha(files['dump_all_dsp_delay.tcl'])==exporter['sha256']
    metadata={'target':'xczu15eg-ffvb1156-2-i','top':'RamVectorFp','RTL_milestone':'M5',
       'RTL_sha256':sha(files['rtl/RamVectorFp.sv']),'M5_receipt_sha256':sha(receipt.read_bytes()),
       'DSP_exporter':exporter,'clock_scope':'OOC matching M4 comparison; host IO and HD.CLK_SRC unspecified',
       'runner_Tcl_origin':'same Tcl as user-successful M4 fix3; new RTL implementation not executed here'}
    validation={'vector_RTL_status':result['vector_test']['status'],
       'DSP_mapped_status':result['DSP_mapped_test']['status'],
       'vector_commands':result['vector_test']['commands'],
       'instruction_flush_cases':result['vector_test']['coverage']['flushes'],
       'context_write_flush_cases':result['vector_test']['coverage']['context_write_flush'],
       'M5_Vivado_execution':'NOT_RUN','Windows_PowerShell_execution_of_M5_bundle':'NOT_RUN',
       'passes_300MHz':None,'passes_500MHz':None}
    files['provenance.json']=(json.dumps(metadata,indent=2)+'\n').encode()
    files['validation.json']=(json.dumps(validation,indent=2)+'\n').encode()
    files['input-sha256.json']=(json.dumps({n:sha(b) for n,b in sorted(files.items())},indent=2)+'\n').encode()
    target=a.output.resolve();target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'w',compression=ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):z.writestr('vpu-m5/'+name,data)
    with ZipFile(target) as z:
        assert z.testzip() is None
        for name,data in files.items():assert z.read('vpu-m5/'+name)==data
    h=sha(target.read_bytes());target.with_suffix('.zip.sha256').write_text(h+'  '+target.name+'\n')
    print(target,target.stat().st_size,'bytes',h)

if __name__=='__main__':main()
