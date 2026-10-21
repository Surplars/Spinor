#!/usr/bin/env python3
"""Regenerate all direct configurations and compare complete SV bytes to M56."""
import gzip
import json
from m61_build import ROOT,OUT,TMP,MODELS,sha,run,save


def main():
    oldNames={'host':'SpinorHost','deep':'SpinorHostDeep','standalone':'SpinorStandard','integer':'SpinorIntegerDeep'}
    old=json.loads((ROOT/'reports/m56/receipt.json').read_text());rows={};artifacts={}
    configured=ROOT/'build/m56/configured/results.json'
    assert sha(configured)==old['artifact_sha256'][str(configured.relative_to(ROOT))]
    configurations=json.loads(configured.read_text())
    for model,(_,preset,fcsr) in MODELS.items():
        name=oldNames[model];reference=ROOT/(f'build/m56/configured/{name}/{name}.sv' if model=='deep' else f'build/m56/rtl/{name}.sv')
        source=configurations if model=='deep' else old
        expected=next(group[str(reference.relative_to(ROOT))] for group in source.values() if isinstance(group,dict) and str(reference.relative_to(ROOT)) in group)
        assert sha(reference)==expected
        folder=TMP/('legacy-'+model);out=OUT/'legacy'/model
        run([ROOT/'mill','Vpu.runMain','vpu.GenerateConfigured','--out',folder,'--name',name,'--preset',preset,'--fcsr-owner',fcsr],out/'generate.log')
        actual=folder/(name+'.sv');assert actual.read_bytes()==reference.read_bytes(),(model,'legacy default RTL changed')
        rel,h=save(actual,out);artifacts[rel]=h;artifacts[str(reference.relative_to(ROOT))]=expected
        artifacts[str((out/'generate.log').relative_to(ROOT))]=sha(out/'generate.log')
        rows[model]=dict(top=name,sv_sha256=expected,byte_identical=True)
    out=OUT/'legacy';result=dict(status='PASS',configs=rows,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'scripts/m61_legacy.py',*sorted((ROOT/'src/main/scala').rglob('*.scala'))]},
        artifact_sha256={**artifacts,'reports/m56/receipt.json':sha(ROOT/'reports/m56/receipt.json'),str(configured.relative_to(ROOT)):sha(configured)})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS all four legacy direct SV files byte-identical to accepted M56',flush=True)


if __name__=='__main__':main()
