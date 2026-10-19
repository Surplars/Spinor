#!/usr/bin/env python3
"""Independent reserved mixed-EEW carry-source policy; never a Spike comparison."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from m57_isa_catalog import catalog
from test_compiled_programs import ROOT, env

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--top', default='SpinorStandard', choices=['SpinorStandard', 'SpinorDeep'])
    a = p.parse_args()
    folder = ROOT/'build/m57/reserved'/a.top
    folder.mkdir(parents=True, exist_ok=True)
    spec = ROOT/'docs/references/m57-v-spec-maintained.adoc'
    text = ' '.join(spec.read_text().split())
    assert 'more than one EEW' in text and 'EEW=1' in text
    entries = [e for e in catalog() if e['name'].startswith(('vadc_', 'vmadc_', 'vsbc_', 'vmsbc_')) and e['name'].endswith(('_vvm', '_vxm', '_vim'))]
    assert len(entries) == 10
    regs = [int.from_bytes(bytes((17*r+13*k+7)&255 for k in range(16)), 'little') for r in range(32)]
    rf = folder/'unchanged-rf.hex'
    rf.write_text(''.join(f'{r>>(64*k)&((1<<64)-1):016x}\n' for r in regs for k in range(2)))
    lines = [f'R {r} {value:032x}' for r, value in enumerate(regs)]
    ident = cases = 0
    vl = start = vxrm = sat = frm = flags = 0
    typ = 1 << 63
    def command(raw, scalar=0, avl=0, bad=0, writes=0, result=0):
        nonlocal ident
        values = [ident, raw, scalar, 0, avl, bad, 2 if bad else 0, 0, writes, result, vl, typ, start, vxrm, sat, frm, flags]
        lines.append('I '+' '.join(f'{v:x}' for v in values)+' '+str(rf.relative_to(ROOT))+' -')
        ident += 1
    for address, value, key in [(9, 1, 'sat'), (10, 2, 'vxrm'), (1, 21, 'flags'), (2, 3, 'frm')]:
        if key == 'sat': sat = value
        elif key == 'vxrm': vxrm = value
        elif key == 'flags': flags = value
        else: frm = value
        command(address << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=value, writes=1)
    for s in range(4):
        for length in (0, 2):
            for restart in (0, 1, 127):
                for e in entries:
                    aliases = [(0, 24)]
                    if e['name'].endswith('_vvm'):
                        aliases.append((16, 0))
                    for src, operand in aliases:
                        typ, vl, start = s << 3, length, 0
                        command(typ << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=length, writes=1, result=length)
                        start = restart
                        command(8 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=restart, writes=1)
                        raw = e['match'] | ((src << 20 | operand << 15 | 8 << 7) & ~e['mask'])
                        command(raw, scalar=1, bad=1)
                        cases += 1
    fixture = folder/'stimulus.txt'
    fixture.write_text('\n'.join(lines)+'\n')
    cache = ROOT/'build/m55/gsim/bin'/a.top
    build = json.loads((cache/'build.json').read_text())
    binary = cache/'run'
    assert sha(binary) == build['binary_sha256']
    for rel, h in build['inputs'].items():
        assert sha(ROOT/rel) == h, rel
    with (folder/'run.log').open('w') as log:
        r = subprocess.run([binary, fixture], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=120)
    assert r.returncode == 0, (folder/'run.log').read_text()[-1800:]
    summary = next(l for l in (folder/'run.log').read_text().splitlines() if l.startswith('PASS direct GSIM'))
    assert f'commands={ident} ' in summary and 'requests=0 responses=0' in summary
    negatives = {}
    for mode, diagnostic in [('wrong-token', 'completion token mismatch'), ('wrong-rf', 'RF mismatch'), ('wrong-csr', 'CSR mismatch')]:
        with (folder/(mode+'.log')).open('w') as log:
            r = subprocess.run([binary, fixture, mode], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=30)
        assert r.returncode == 1 and diagnostic in (folder/(mode+'.log')).read_text(), mode
        negatives[mode] = 'REJECTED'
    d = dict(status='PASS', top=a.top, commands=ident, reserved_cases=cases, encodings=len(entries), summary=summary,
             oracle='NORMATIVE_RESERVED_REJECTION_POLICY_NOT_SPIKE', negative_controls=negatives,
             source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(), ROOT/'tests/m57_isa_catalog.py', spec]},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary, cache/'build.json', fixture, rf, *folder.glob('*.log')]})
    (folder/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS reserved carry-source policy', a.top, cases, 'cases', flush=True)


if __name__ == '__main__':
    main()
