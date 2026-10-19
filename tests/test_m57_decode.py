#!/usr/bin/env python3
"""Raw OP-V decode survey at VL=0, against unmodified Spike and real GSIM DUT.

This checks decode/state boundaries, not numerical arithmetic. Fixed vector
operands are disjoint. Selector fields and scalar/immediate indexes are swept;
ordinary binary vector indexes are held at 24 to avoid reserved mixed-EEW alias
differences with the reference. Full RF is still checked after every command.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from test_compiled_programs import ROOT, env

OUT = ROOT/'build/m57/decode'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def events(sew):
    # All RF values start at zero and remain zero with VL=0; scalar extraction
    # is still checked (including FP NaN boxing), even at VL=0.
    rows = [dict(raw=(sew << 3) << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57,
                 tag='configuration')]
    seen = set()
    for form in range(7):
        for f6 in range(64):
            unary = (form == 2 and f6 in (0x10, 0x12, 0x14)) or (form == 1 and f6 in (0x10, 0x12, 0x13))
            operands = range(32) if form in (3, 4, 5, 6) or unary else [24]
            for vm in range(2):
                for operand in operands:
                    raw = f6 << 26 | vm << 25 | 16 << 20 | operand << 15 | form << 12 | 8 << 7 | 0x57
                    assert raw not in seen
                    seen.add(raw)
                    rows.append(dict(raw=raw, tag='raw-selector'))
    # Zero vs2 is required by scalar insertions and vm=1 broadcasts. Keep
    # vm=0 merge vs2=v0 aliases in the separate normative reserved-policy suite.
    for form in (4, 5, 6):
        for f6 in (0x10, 0x17):
            if form == 4 and f6 == 0x10:
                continue  # This is vadc, not scalar insertion; vs2=v0 is mixed EEW.
            for vm in ((1,) if f6 == 0x17 else (0, 1)):
                for operand in range(32):
                    raw = f6 << 26 | vm << 25 | operand << 15 | form << 12 | 8 << 7 | 0x57
                    assert raw not in seen
                    seen.add(raw)
                    rows.append(dict(raw=raw, tag='zero-vs2-transfer'))
    return rows


def corpus(sew):
    out = OUT/f'sew{8 << sew}'
    out.mkdir(parents=True, exist_ok=True)
    model_path = ROOT/'build/m55/reference/results.json'
    model = json.loads(model_path.read_text())
    assert model['status'] == 'PASS' and sha(ROOT/model['binary']) == model['binary_sha256']
    rows = events(sew)
    text = ''.join(f'R {r} {0:032x}\n' for r in range(32))
    text += ''.join(f'I {r["raw"]:x} 0 0 0\n' for r in rows)
    response = subprocess.run([ROOT/model['binary']], input=text, text=True, capture_output=True, cwd=ROOT, check=True, timeout=120)
    (out/'spike-stderr.log').write_text(response.stderr)
    (out/'spike-input.txt.gz').write_bytes(gzip.compress(text.encode(), mtime=0))
    (out/'spike-output.txt.gz').write_bytes(gzip.compress(response.stdout.encode(), mtime=0))
    states = []
    for line in response.stdout.splitlines():
        f = line.split()
        assert f[0] == 'S' and len(f) == 45 and int(f[1]) == len(states)
        assert all(int(x, 16) == 0 for x in f[13:]), ('VL0 modified RF', f[:13])
        states.append([int(f[2]), int(f[3]), int(f[4], 16), int(f[5], 16), *[int(x, 16) for x in f[6:13]]])
    assert len(states) == len(rows)
    zero = out/'zero-rf.hex'
    zero.write_text('0000000000000000\n' * 64)
    fixture = ''.join(f'R {r} {0:032x}\n' for r in range(32))
    legal = 0
    for ident, (r, s) in enumerate(zip(rows, states)):
        illegal, cause, scalar, writes, vl, typ, start, vxrm, sat, frm, flags = s
        assert cause in (0, 2) and vl == start == vxrm == sat == frm == flags == 0
        values = [ident, r['raw'], 0, 0, 0, illegal, cause, 0, writes, scalar, vl, typ, start, vxrm, sat, frm, flags]
        fixture += 'I ' + ' '.join(f'{x:x}' for x in values) + ' ' + str(zero.relative_to(ROOT)) + ' -\n'
        legal += not illegal
    target = out/'stimulus.txt.gz'
    target.write_bytes(gzip.compress(fixture.encode(), mtime=0))
    d = dict(status='PASS', sew=8 << sew, commands=len(rows), legal=legal, rejected=len(rows)-legal,
             oracle='UNMODIFIED_UPSTREAM_SPIKE', oracle_binary=model['binary'], oracle_binary_sha256=model['binary_sha256'],
             source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [model_path, target, zero, *out.glob('spike-*')]})
    (out/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    return out, d


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--top', default='SpinorStandard', choices=['SpinorStandard', 'SpinorDeep'])
    p.add_argument('--sew', type=int, choices=[8, 16, 32, 64], default=32)
    a = p.parse_args()
    out, reference = corpus((a.sew // 8).bit_length()-1)
    cache = ROOT/'build/m55/gsim/bin'/a.top
    build = json.loads((cache/'build.json').read_text())
    binary = cache/'run'
    assert sha(binary) == build['binary_sha256']
    for rel, h in build['inputs'].items():
        assert sha(ROOT/rel) == h, rel
    # Exact current standalone RTL identity is bound by M56 and rechecked here.
    identity = json.loads((ROOT/'build/m56/default-identity.json').read_text())
    item = next(r for r in identity['tops'] if r['top'] == a.top)
    assert sha(ROOT/item['after']) == item['sha256']
    assert gzip.decompress((ROOT/item['archive']).read_bytes()) == (ROOT/item['after']).read_bytes()
    folder = out/a.top
    folder.mkdir(exist_ok=True)
    scratch = folder/'scratch-stimulus.txt'
    scratch.write_bytes(gzip.decompress((out/'stimulus.txt.gz').read_bytes()))
    try:
        with (folder/'run.log').open('w') as log:
            result = subprocess.run([binary, scratch], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=180)
        assert result.returncode == 0, (folder/'run.log').read_text()[-2000:]
        summary = next(l for l in (folder/'run.log').read_text().splitlines() if l.startswith('PASS direct GSIM'))
        assert f'commands={reference["commands"]} ' in summary and 'requests=0 responses=0' in summary
        negatives = {}
        for mode, diagnostic in [('wrong-token', 'completion token mismatch'), ('wrong-rf', 'RF mismatch'), ('wrong-csr', 'CSR mismatch')]:
            with (folder/(mode+'.log')).open('w') as log:
                r = subprocess.run([binary, scratch, mode], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=30)
            assert r.returncode == 1 and diagnostic in (folder/(mode+'.log')).read_text(), mode
            negatives[mode] = 'REJECTED'
    finally:
        scratch.unlink(missing_ok=True)  # Only this new, explicitly transient copy.
    d = dict(status='PASS', top=a.top, summary=summary, sew=a.sew, commands=reference['commands'],
             legal=reference['legal'], rejected=reference['rejected'], numerical_arithmetic=False, trace_replay=False,
             checked_registers_per_command=32, negative_controls=negatives,
             source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary, cache/'build.json', out/'results.json', ROOT/'build/m56/default-identity.json', *folder.glob('*.log')]})
    (folder/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS raw OP-V survey', a.top, a.sew, reference['commands'], 'commands', flush=True)


if __name__ == '__main__':
    main()
