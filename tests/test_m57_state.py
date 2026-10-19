#!/usr/bin/env python3
"""VTYPE bit-field and vector/FCSR CSR action audit through public DUT ports."""
import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from test_compiled_programs import ROOT, env

OUT = ROOT/'build/m57/state'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
M64 = (1 << 64)-1


def events():
    rows = []
    def add(raw, scalar=0, scalar2=0, avl=0, tag='configuration'):
        rows.append(dict(raw=raw, scalar=scalar, scalar2=scalar2, avl=avl, tag=tag))
    for typ in range(2048):
        for avl in (0, 1, 31, M64):
            add(typ << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=avl)
    for typ in range(1024):
        for avl in (0, 1, 31):
            add(3 << 30 | typ << 20 | avl << 15 | 7 << 12 | 3 << 7 | 0x57)
    for typ in [*range(256), *[1 << b for b in range(8, 64)]]:
        for avl in (0, 1, 31, M64):
            add(1 << 31 | 2 << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, scalar2=typ, avl=avl)
    # x0 AVL means maximum when rd != x0; rd=rs1=x0 retains VL only
    # with an unchanged VLMAX. Reserved changing-VLMAX forms stay separate.
    for s in range(4):
        typ = s << 3
        add(typ << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=1)
        add(typ << 20 | 7 << 12 | 3 << 7 | 0x57)
        add(typ << 20 | 7 << 12 | 0x57)
        add(typ << 20 | 1 << 15 | 7 << 12 | 0x57, avl=1)
    for address in (1, 2, 3, 8, 9, 10, 15, 0xc20, 0xc21, 0xc22, 0xb, 0xc, 0xd, 0xe):
        for action in (1, 2, 3, 5, 6, 7):
            for source in (0, 1, 31):
                for rd in (0, 3):
                    for pattern in (0, M64, 0xa59639ce17f082b4):
                        # Prime a legal SEW32 VL=3 and nonzero vstart. A CSR
                        # access must not acquire vector-instruction clearing.
                        add(0x10 << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=3, tag='prime')
                        add(8 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=7, tag='prime')
                        add(address << 20 | source << 15 | action << 12 | rd << 7 | 0x73,
                            scalar=pattern if source else 0, tag='csr')
    return rows


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = ROOT/'build/m55/reference/results.json'
    model = json.loads(model_path.read_text())
    assert model['status'] == 'PASS' and sha(ROOT/model['binary']) == model['binary_sha256']
    rows = events()
    text = ''.join(f'R {r} {0:032x}\n' for r in range(32))
    text += ''.join('I '+' '.join(f'{r[k]:x}' for k in ['raw', 'scalar', 'scalar2', 'avl'])+'\n' for r in rows)
    response = subprocess.run([ROOT/model['binary']], input=text, text=True, capture_output=True, cwd=ROOT, check=True, timeout=120)
    (OUT/'spike-input.txt.gz').write_bytes(gzip.compress(text.encode(), mtime=0))
    (OUT/'spike-output.txt.gz').write_bytes(gzip.compress(response.stdout.encode(), mtime=0))
    (OUT/'spike-stderr.log').write_text(response.stderr)
    zero = OUT/'zero-rf.hex'
    zero.write_text('0000000000000000\n'*64)
    fixture = ''.join(f'R {r} {0:032x}\n' for r in range(32))
    lines = response.stdout.splitlines()
    assert len(lines) == len(rows)
    illegal = 0
    for ident, (r, line) in enumerate(zip(rows, lines)):
        f = line.split()
        assert f[0] == 'S' and len(f) == 45 and int(f[1]) == ident
        bad, cause = int(f[2]), int(f[3])
        assert cause in (0, 2) and all(int(x, 16) == 0 for x in f[13:])
        if r['tag'] == 'configuration':
            assert bad == 0, 'unsupported vtype must set vill, not trap'
            assert int(f[8], 16) == 0, 'vset must clear vstart'
        values = [ident, r['raw'], r['scalar'], r['scalar2'], r['avl'], bad, cause, 0,
                  int(f[5], 16), int(f[4], 16), *[int(x, 16) for x in f[6:13]]]
        fixture += 'I '+' '.join(f'{v:x}' for v in values)+' '+str(zero.relative_to(ROOT))+' -\n'
        illegal += bad
    (OUT/'stimulus.txt.gz').write_bytes(gzip.compress(fixture.encode(), mtime=0))
    d = dict(status='PASS', commands=len(rows), configuration_cases=sum(r['tag']=='configuration' for r in rows),
             csr_cases=sum(r['tag']=='csr' for r in rows), prime_commands=sum(r['tag']=='prime' for r in rows),
             rejected=illegal, oracle='UNMODIFIED_UPSTREAM_SPIKE', oracle_binary=model['binary'], oracle_binary_sha256=model['binary_sha256'],
             source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [model_path, zero, OUT/'stimulus.txt.gz', *OUT.glob('spike-*')]})
    (OUT/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    return d


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--top', default='SpinorStandard', choices=['SpinorStandard', 'SpinorDeep'])
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    if a.prepare_only:
        print('PASS state oracle', prepare()['commands'])
        return
    # Immutable shared corpus is prepared once, before any parallel DUT runs.
    reference = json.loads((OUT/'results.json').read_text())
    assert reference['source_sha256'][str(Path(__file__).resolve().relative_to(ROOT))] == sha(Path(__file__))
    for rel, h in reference['artifact_sha256'].items():
        assert sha(ROOT/rel) == h, rel
    cache = ROOT/'build/m55/gsim/bin'/a.top
    build = json.loads((cache/'build.json').read_text())
    binary = cache/'run'
    assert sha(binary) == build['binary_sha256']
    for rel, h in build['inputs'].items():
        assert sha(ROOT/rel) == h, rel
    folder = OUT/a.top
    folder.mkdir(exist_ok=True)
    scratch = folder/'scratch-stimulus.txt'
    scratch.write_bytes(gzip.decompress((OUT/'stimulus.txt.gz').read_bytes()))
    try:
        with (folder/'run.log').open('w') as log:
            r = subprocess.run([binary, scratch], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=180)
        assert r.returncode == 0, (folder/'run.log').read_text()[-2000:]
        summary = next(l for l in (folder/'run.log').read_text().splitlines() if l.startswith('PASS direct GSIM'))
        assert f'commands={reference["commands"]} ' in summary and 'requests=0 responses=0' in summary
        negatives = {}
        for mode, diagnostic in [('wrong-token', 'completion token mismatch'), ('wrong-rf', 'RF mismatch'), ('wrong-csr', 'CSR mismatch')]:
            with (folder/(mode+'.log')).open('w') as log:
                r = subprocess.run([binary, scratch, mode], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=30)
            assert r.returncode == 1 and diagnostic in (folder/(mode+'.log')).read_text(), mode
            negatives[mode] = 'REJECTED'
    finally:
        scratch.unlink(missing_ok=True)
    d = dict(status='PASS', top=a.top, commands=reference['commands'], summary=summary, trace_replay=False,
             checked_registers_per_command=32, negative_controls=negatives,
             source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary, cache/'build.json', OUT/'results.json', *folder.glob('*.log')]})
    (folder/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS VTYPE/CSR audit', a.top, reference['commands'], 'commands', flush=True)


if __name__ == '__main__':
    main()
