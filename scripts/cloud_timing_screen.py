#!/usr/bin/env python3
"""One-command offline reference analysis of an existing Vivado results folder."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--label',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=a.results.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=True)
    for name in ['screening-receipt.json','comparison.json','probe.json','matched-paths.tsv']:
        (o/name).unlink(missing_ok=True)
    compare=[sys.executable,str(ROOT/'scripts/cloud_timing_compare.py'),'--results',str(r),'--reference',str(o)]
    subprocess.run(compare+['--prepare'],check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/cloud_reference.py'),
        '--checkpoint',str(r/'routed.dcp'),'--dsp-dir',str(r/'dsp_delay'),
        '--output',str(o),'--queries',str(o/'queries.tsv'),'--label',a.label],check=True)
    subprocess.run(compare,check=True)
    files=[ROOT/'scripts'/n for n in ['cloud_timing_screen.py','cloud_timing_compare.py','cloud_reference.py','java/CloudTimingAudit.java']]
    files += [o/n for n in ['probe.json','probe.log','queries.tsv','matched-paths.tsv','comparison.json']]
    files += [r/'output-sha256.json',r/'run-inputs.json']
    receipt=dict(status='REFERENCE_ANALYSIS_COMPLETE',label=a.label,signoff_STA=False,
        input_rtl_sha256=json.loads((r/'run-inputs.json').read_text(encoding='utf-8-sig'))['source_hashes']['rtl/RamVectorFp.sv'],
        source_and_output_sha256={str(f):sha(f) for f in files})
    (o/'screening-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
