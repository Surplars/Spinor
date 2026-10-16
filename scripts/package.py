#!/usr/bin/env python3
"""Small, inspectable handoff archive. No tools, caches, credentials or Valence clone."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--milestone',choices=['m1','m2','m3','m4','m5','m6','m7','m8','m9','m10','m11','m12','m13','m14','m15','m16','m17','m18','m19','m20','m21','m22','m23','m24','m25'],default='m1')
args=parser.parse_args()
receipt=root/(f'reports/{args.milestone}/receipt.json' if args.milestone!='m1' else 'reports/receipt.json')
if not receipt.exists():raise SystemExit('Run the corresponding make verify target first')
evidence=json.loads(receipt.read_text())
for rel,expected in evidence['source_sha256'].items():
    path=root/rel
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit(f'Source changed since {receipt.relative_to(root)}: {rel}; regenerate its report before packaging')
project='lishi-vpu' if args.milestone in ['m7','m8','m9','m10','m11','m12','m13','m14','m15','m16','m17'] else 'zu15-vpu'
if args.milestone in ['m18','m19','m20','m21','m22','m23','m24','m25']:project='spinor-vpu'
target=root/f'{project}-{args.milestone}.zip'
files=[root/n for n in ['build.mill','.mill-version','.mill-jvm-opts','.gitignore','mill','Makefile','tools.lock.json','README.md']]
folders=['src','scripts','tests','docs','third_party','reports/m3','build/rtl','archive/m1/reports','archive/m2/reports'] if args.milestone=='m3' else ['src','scripts','tests','docs','reports/m2','build/rtl','archive/m1/reports'] if args.milestone=='m2' else ['src','scripts','tests','docs','reports','build/rtl']
if args.milestone=='m4':
    folders=['src','scripts','tests','docs','third_party','reports/m4','build/rtl',
             'archive/m1/reports','archive/m2/reports','archive/m3/reports']
if args.milestone=='m5':
    folders=['src','scripts','tests','docs','third_party','reports/m5','build/rtl',
             'archive/m1/reports','archive/m2/reports','archive/m3/reports','archive/m4/reports']
if args.milestone=='m6':
    folders=['src','scripts','tests','docs','third_party','reports/m6','reports/cloud-m5','build/rtl',
             'archive/m1/reports','archive/m2/reports','archive/m3/reports','archive/m4/reports','archive/m5/reports']
if args.milestone=='m7':
    folders=['src','scripts','tests','docs','third_party','reports/m7','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,7)]]
if args.milestone=='m8':
    folders=['src','scripts','tests','docs','third_party','reports/m8','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,8)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv']
if args.milestone=='m9':
    folders=['src','scripts','tests','docs','third_party','reports/m9','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,9)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv']
if args.milestone=='m10':
    folders=['src','scripts','tests','docs','third_party','reports/m10','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,10)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv']
if args.milestone=='m11':
    folders=['src','scripts','tests','docs','third_party','reports/m11','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,11)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv']
if args.milestone=='m12':
    folders=['src','scripts','tests','docs','third_party','reports/m12','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,12)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv']
if args.milestone=='m13':
    folders=['src','scripts','tests','docs','third_party','reports/m13','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,13)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv',root/'archive/m12/synth-LishiVpuMemory/mapped.json',root/'build/synth/LishiVpuMemory/mapped.json']
if args.milestone=='m14':
    folders=['src','scripts','tests','docs','third_party','reports/m14','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,14)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv',root/'archive/m13/synth-LishiVpuMemory/mapped.json',root/'build/synth/LishiVpuMemory/mapped.json']
if args.milestone=='m15':
    folders=['src','scripts','tests','docs','third_party','reports/m15','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,15)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv',root/'archive/m14/synth-LishiVpuMemory/mapped.json',root/'build/synth/LishiVpuMemory/mapped.json']
if args.milestone=='m16':
    folders=['src','scripts','tests','docs','third_party','reports/m16','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,16)]]
    files += [root/'archive/m7/rtl/RamVectorFp.sv',root/'archive/m15/synth-LishiVpuMemory/mapped.json',root/'build/synth/LishiVpuMemory/mapped.json']
if args.milestone=='m17':
    folders=['src','scripts','tests','docs','third_party','reports/m17','reports/m16','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,17)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m18':
    folders=['src','scripts','tests','docs','software','third_party','reports/m18','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,18)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m19':
    folders=['src','scripts','tests','docs','software','third_party','reports/m19','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,19)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m20':
    folders=['src','scripts','tests','docs','software','third_party','reports/m20','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,20)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m21':
    folders=['src','scripts','tests','docs','software','third_party','reports/m21','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,21)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m22':
    folders=['src','scripts','tests','docs','software','third_party','reports/m22','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,22)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m23':
    folders=['src','scripts','tests','docs','software','third_party','reports/m23','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,23)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m24':
    folders=['src','scripts','tests','docs','software','third_party','reports/m24','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,24)]]
    files += [root/p for p in evidence['artifact_sha256']]
if args.milestone=='m25':
    folders=['src','scripts','tests','docs','software','third_party','reports/m25','reports/cloud-m5','build/rtl',
             *[f'archive/m{i}/reports' for i in range(1,25)]]
    files += [root/p for p in evidence['artifact_sha256']]
files += [p for name in folders
          for p in (root/name).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
for path in files:
    rel=str(path.relative_to(root))
    expected=evidence['artifact_sha256'].get(rel)
    if expected and hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit(f'Artifact changed since report: {rel}; regenerate its report before packaging')
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(set(files)):archive.write(p,project+'/'+str(p.relative_to(root)))
checksum=hashlib.sha256(target.read_bytes()).hexdigest()
target.with_suffix('.zip.sha256').write_text(f'{checksum}  {target.name}\n')
print(target, target.stat().st_size,'bytes',checksum)
