#!/usr/bin/env python3
"""Build the new registered top in tmpfs; retain compressed exact inputs/evidence."""
import argparse
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/m61'
TMP=Path('/tmp/spinor-m61')
MODELS={'host':('SpinorIsolated','standard','host'),
        'deep':('SpinorIsolatedDeep','deep','host'),
        'standalone':('SpinorIsolatedStandalone','standard','standalone'),
        'integer':('SpinorIsolatedInteger','integer-deep','standalone')}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def run(cmd,log,timeout=600):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w') as out:subprocess.run(list(map(str,cmd)),cwd=ROOT,stdout=out,stderr=out,check=True,timeout=timeout)


def save(path,folder):
    folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(path.name+'.gz');dest.write_bytes(gzip.compress(path.read_bytes(),mtime=0))
    return str(dest.relative_to(ROOT)),sha(dest)


def emit(model):
    top,preset,fcsr=MODELS[model];folder=TMP/model;folder.mkdir(parents=True,exist_ok=True)
    out=OUT/'rtl'/model
    run([ROOT/'mill','Vpu.runMain','vpu.GenerateIsolated','--out',folder,'--name',top,'--preset',preset,'--fcsr-owner',fcsr,'--format','both'],out/'elaborate.log')
    files=[folder/(top+'.sv'),folder/(top+'.fir'),folder/(top+'.json')]
    d=dict(status='PASS',model=model,top=top,preset=preset,fcsr_owner=fcsr,
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'build.mill',*sorted((ROOT/'src/main/scala').rglob('*.scala'))]},
           artifact_sha256=dict(save(p,out) for p in files),uncompressed_sha256={p.name:sha(p) for p in files})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS emit',model,flush=True)


def restore(model):
    folder=TMP/model;folder.mkdir(parents=True,exist_ok=True)
    source=OUT/'rtl'/model;d=json.loads((source/'results.json').read_text())
    for rel,h in d['source_sha256'].items():assert sha(ROOT/rel)==h,rel
    for rel,h in d['artifact_sha256'].items():
        p=ROOT/rel;assert sha(p)==h
        path=folder/p.stem;path.write_bytes(gzip.decompress(p.read_bytes()));assert sha(path)==d['uncompressed_sha256'][path.name]
    return folder,d


def gsim(model):
    folder,d=restore(model);top=d['top'];source=folder/(top+'.fir');text=source.read_text()
    normalized=folder/(top+'.gsim.fir')
    normalized.write_text(''.join(line if re.match(r'\s*smem\b',line) else re.sub(r'\bold\b','gsim_old',line) for line in text.splitlines(True)))
    out=OUT/'gsim'/model
    binary=ROOT/'tools/gsim-src/build/gsim/gsim'
    run([binary,'--threads=1','--dir='+str(folder),normalized],out/'generate.log')
    files=[normalized,folder/(top+'.h'),*sorted(folder.glob(top+'[0-9]*.cpp'))]
    result=dict(status='PASS',model=model,top=top,normalization='IDENTIFIER_ALPHA_RENAME_ONLY',
                source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__).resolve())},
                artifact_sha256={**dict(save(p,out) for p in files),str((OUT/'rtl'/model/'results.json').relative_to(ROOT)):sha(OUT/'rtl'/model/'results.json'),str(binary.relative_to(ROOT)):sha(binary)})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS gsim',model,flush=True)


def synth(model):
    folder,d=restore(model);top=d['top'];out=OUT/'synth'/model;out.mkdir(parents=True,exist_ok=True)
    script=folder/'synth.ys'
    script.write_text(f'''read_verilog -sv {folder}/{top}.sv
synth_xilinx -family xcup -top {top} -flatten -noiopad -noclkbuf -nosrl -nowidelut
tee -o {folder}/stat.json stat -json
check -assert
write_json {folder}/mapped.json
''')
    run([ROOT/'tools/oss-cad-suite/bin/yosys','-T','-s',script],out/'synth.log',timeout=1200)
    mapped=folder/'mapped.json';stat=json.loads((folder/'stat.json').read_text())['modules']['\\'+top]
    result=dict(status='PASS',model=model,top=top,family='xcup',placed=False,routed=False,
                mapped_cells=stat['num_cells_by_type'],source_sha256={'scripts/m61_build.py':sha(Path(__file__).resolve())},
                artifact_sha256={**dict(save(p,out) for p in [mapped,script,folder/'stat.json']),str((OUT/'rtl'/model/'results.json').relative_to(ROOT)):sha(OUT/'rtl'/model/'results.json')})
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS synth',model,result['mapped_cells'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['emit','gsim','synth']);p.add_argument('--model',choices=MODELS,default='host');a=p.parse_args()
    globals()[a.stage](a.model)
