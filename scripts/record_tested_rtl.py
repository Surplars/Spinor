#!/usr/bin/env python3
"""Capture exact RTL inputs for a verification batch."""
import argparse
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--milestone',choices=['m3','m4','m5'],default='m3')
args=parser.parse_args()
files=sorted((root/'build/rtl').rglob('*.sv'))
assert files and 'SUCCESS' in (root/'tools/mill-generate.log').read_text()
receipt={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(root/f'tools/{args.milestone}-tested-rtl-sha256.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Recorded',len(files),'RTL inputs for',args.milestone,'verification')
