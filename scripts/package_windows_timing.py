#!/usr/bin/env python3
"""Small current-RTL Windows handoff; preserve all frozen milestone scripts."""
import argparse,hashlib,json,re
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
from report_m53 import baseline_check,ROOT
from report_m51 import check
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'handoff/spinor-m53-timing-fix1.zip');a=p.parse_args()
    old,base=baseline_check();latest=ROOT/'reports/m53/receipt.json';check(json.loads(latest.read_text()))
    rtl=ROOT/'build/rtl/SpinorVpu.sv';assert sha(rtl.read_bytes())==old['artifact_sha256']['build/rtl/SpinorVpu.sv']
    files={n:(ROOT/'scripts/windows-timing'/n).read_bytes() for n in ['run.ps1','resume.ps1','pack_results.ps1','run_vivado.tcl','resume_vivado.tcl','RUN_ME_FIRST.txt']}
    files['rtl/SpinorVpu.sv']=rtl.read_bytes()
    exporter=ROOT/'third_party/rapidwright/dump_all_dsp_delay.tcl';manifest=json.loads((exporter.parent/'manifest.json').read_text())
    assert sha(exporter.read_bytes())==manifest['sha256'];files['dump_all_dsp_delay.tcl']=exporter.read_bytes()
    files['licenses/Apache-2.0.txt']=(exporter.parent/'LICENSE').read_bytes()
    files['licenses/berkeley-hardfloat.LICENSE']=(ROOT/'third_party/licenses/berkeley-hardfloat.LICENSE').read_bytes()
    notices=[]
    for src in sorted([*(ROOT/'third_party/berkeley-hardfloat/src/main/scala').glob('*.scala'),*(ROOT/'src/main/scala/vpu').glob('Staged*.scala')]):
        m=re.search(r'/\*={10,}.*?={10,}\*/',src.read_text(),re.S)
        if m and m[0] not in notices:notices.append(m[0])
    files['licenses/HardFloat-source-notices.txt']=('\n\n'.join(notices)+'\n').encode()
    files['evidence/m53-evaluation.md']=(ROOT/'reports/m53/evaluation.md').read_bytes()
    gate=ROOT/'build/timing-budget/m53-gate/results.json';d=json.loads(gate.read_text());check(d)
    for rel,h in d['input_sha256'].items():assert sha((ROOT/rel).read_bytes())==h,rel
    files['evidence/conditional-gate.json']=gate.read_bytes()
    hardware={rel:sha((ROOT/rel).read_bytes()) for rel in sorted(old['source_sha256']) if rel.endswith('.scala')}
    files['evidence/hardware-source-sha256.json']=(json.dumps(hardware,indent=2)+'\n').encode()
    provenance=dict(milestone='M53',runner_revision='M53-timing-fix1',top='SpinorVpu',preset='Standard_FP_VLEN128_ELEN64',
        hardware_baseline_commit='9dec43e',rtl_sha256=sha(rtl.read_bytes()),baseline_audit=base,
        m53_receipt_sha256=sha(latest.read_bytes()),source_builder_sha256=sha(Path(__file__).read_bytes()),
        default_part='xczu15eg-ffvb1156-2-i',default_period_ns=3.333333,DSP_exporter=manifest,
        hardware_changed=False,Windows_execution='NOT_RUN',Vivado_execution='NOT_RUN',
        post_route_SDF_simulation='NOT_RUN',passes_300MHz=None,passes_500MHz=None,
        timing_scope='Fresh standalone OOC; external IO delays and board clock location unspecified')
    files['provenance.json']=(json.dumps(provenance,indent=2)+'\n').encode()
    files['input-sha256.json']=(json.dumps({n:sha(b) for n,b in sorted(files.items())},indent=2)+'\n').encode()
    target=a.output.resolve();target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'w',compression=ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            info=ZipInfo('spinor-m53-timing/'+n,(2026,10,19,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,b)
    with ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        for n,b in files.items():assert z.read('spinor-m53-timing/'+n)==b
    target.with_suffix('.zip.sha256').write_text(sha(target.read_bytes())+'  '+target.name+'\n')
    print(target,target.stat().st_size,'bytes',sha(target.read_bytes()))
if __name__=='__main__':main()
