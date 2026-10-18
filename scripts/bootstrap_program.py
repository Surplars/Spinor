#!/usr/bin/env python3
"""Unpack SHA-pinned LLVM 19 locally. No system installation or HOME changes."""
import hashlib
import json
import platform
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tools/llvm-program'


def main():
    assert platform.system() == 'Linux' and platform.machine() == 'x86_64'
    OUT.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / 'software/programs/toolchain.lock.json').read_text())
    for spec in lock.values():
        path = OUT / spec['file']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            with urllib.request.urlopen(spec['url'], timeout=60) as response:
                raw = response.read()
            assert hashlib.sha256(raw).hexdigest() == spec['sha256'], spec['file']
            path.write_bytes(raw)
        subprocess.run(['dpkg-deb', '-x', str(path), str(OUT)], check=True)
    print('Pinned LLVM 19.1.7 compiler, headers, linker and LLVM libraries ready')


if __name__ == '__main__':
    main()
