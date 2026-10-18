#!/usr/bin/env python3
"""Link a RAM transport to the same unmodified pinned Spike as M50."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/spike-memory-model'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    base=json.loads((ROOT/'build/spike-model/results.json').read_text())
    assert base['status']=='PASS' and not base['semantics_modified']
    for key in ['sha256','model_source_sha256','model_libraries_sha256']:
        for rel,h in base[key].items():assert sha(ROOT/rel)==h,rel
    assert sha(ROOT/base['binary'])==base['binary_sha256']
    OUT.mkdir(parents=True,exist_ok=True)
    adapter=ROOT/'tests/spike_memory_adapter.cc';binary=ROOT/'tools/spike/spinor-spike-memory'
    command=[str(adapter) if arg==str(ROOT/'tests/spike_adapter.cc') else str(binary) if arg==str(ROOT/base['binary']) else arg for arg in base['link_command']]
    with (OUT/'link.log').open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=log,check=True)
    lock=json.loads((ROOT/'third_party/spike-reference.json').read_text());src=ROOT/lock['source']['source_dir']
    make=(src/'riscv/riscv.mk.in').read_text();encoding=(src/'riscv/encoding.h').read_text()
    block=re.search(r'riscv_insn_ext_v_ldst\s*=\s*\\\n(.*?)(?=\n\w+\s*[:?+]?=)',make,re.S)
    names=re.findall(r'^\s*(\w+)\s*\\?$',block[1],re.M)
    catalog=[dict(name=n,match=int(re.search(r'^#define MATCH_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16),mask=int(re.search(r'^#define MASK_'+n.upper()+r' (0x[0-9a-f]+)',encoding,re.M)[1],16)) for n in names]
    assert len(catalog)==58
    target=OUT/'catalog.json';target.write_text(json.dumps(catalog,indent=2)+'\n')
    files=[Path(__file__).resolve(),adapter,ROOT/'build/spike-model/results.json',ROOT/'third_party/spike-reference.json',target]
    result=dict(status='PASS',revision=base['revision'],semantics_modified=False,binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),
                transport_only=True,ram_base='0x80010000',ram_bytes=8192,faults='CALLBACK_ACCESS_FAULT_RANGE',link_command=command,
                sha256={str(p.relative_to(ROOT)):sha(p) for p in files})
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS Spike RAM adapter',len(catalog),'canonical memory encodings',flush=True)
if __name__=='__main__':main()
