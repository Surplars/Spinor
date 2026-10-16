#!/usr/bin/env python3
"""Install pinned engineering tools in this workspace, without root or Docker."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
LOCK=json.loads((ROOT/'tools.lock.json').read_text())

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def fetch(item):
    name,spec=item;path=TOOLS/name
    if not path.exists():
        temporary=path.with_suffix(path.suffix+'.partial')
        print('Downloading',name,flush=True)
        with urllib.request.urlopen(spec['url'],timeout=120) as src,temporary.open('wb') as dst:
            while chunk:=src.read(1024*1024):dst.write(chunk)
        if digest(temporary)!=spec['sha256']:raise RuntimeError('Checksum mismatch: '+name)
        temporary.rename(path)
    if digest(path)!=spec['sha256']:raise RuntimeError('Checksum mismatch: '+name)
    return path

def main():
    TOOLS.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(fetch,LOCK['artifacts'].items()))
    receipt=TOOLS/'oss-cad-suite/.zu15-install-receipt'
    wanted=LOCK['artifacts']['oss-cad-suite.tgz']['sha256']
    if not receipt.exists() or receipt.read_text().strip()!=wanted:
        with tarfile.open(TOOLS/'oss-cad-suite.tgz') as archive:
            # Valence does not use Verilator. No such backend is installed here.
            members=[m for m in archive.getmembers() if 'verilator' not in m.name.lower()]
            archive.extractall(TOOLS,members=members,filter='data')
        receipt.write_text(wanted+'\n')
    print('Pinned Mill and OSS CAD Suite ready. Java 21 and Python 3.12+ are prerequisites.')

if __name__=='__main__':main()
