#!/usr/bin/env python3
"""Expand official NF fields and execute all 310 memory forms, including holes.

The 12 previously unexercised legal stride/NF forms get extra negative/zero
stride, masking and restart cases. Reference is unmodified upstream Spike;
the DUT is the public production TileLink/command interface, with full RF/RAM.
"""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from m57_isa_catalog import audited_catalog
from test_compiled_programs import ROOT, env
import test_spike_memory as memory

OUT = ROOT/'build/m57/memory-forms'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def forms():
    result = []
    for e in audited_catalog():
        if e['family'] != 'memory':
            continue
        fixed = bool(e['mask'] & (7 << 29))
        for nf in ([(e['match'] >> 29)+1] if fixed else range(1, 9)):
            result.append(dict(e, nf=nf, fixed_nf=fixed))
    assert len(result) == 310
    return result


def prior_samples():
    entries = [e for e in audited_catalog() if e['family'] == 'memory']
    counts = Counter()
    for label in ('memory-full', 'edges-full'):
        folder = ROOT/'build/m54/gsim/corpus'/label
        events = json.loads((folder/'inputs.json').read_text())
        states = json.loads((folder/'expected.json').read_text())
        for e in events:
            if e['kind'] != 'I' or states[e['id']]['cause']:
                continue
            raw = e['instruction']
            for r in entries:
                if raw & r['mask'] == r['match']:
                    counts[r['name'], (raw >> 29)+1] += 1
                    break
    return counts


def events():
    rows = []
    ident = 0
    def ins(raw, scalar=0, scalar2=0, avl=0, **meta):
        nonlocal ident
        rows.append(dict(kind='I', id=ident, instruction=raw, scalar=scalar, scalar2=scalar2 & memory.M64, avl=avl, **meta))
        ident += 1
    def case(e, stride_mode=1, vm=1, start=0, length=3):
        nf = e['nf']
        mode = e['match'] >> 26 & 3
        index_width = 1 << [0, 5, 6, 7].index(e['match'] >> 12 & 7)
        bits = 32 if mode in (1, 3) else index_width * 8
        s = (bits // 8).bit_length()-1
        step = nf * (bits // 8) * 2
        rows.extend([dict(kind='M', data=bytes((i*13+7)&255 for i in range(8192)).hex()), dict(kind='F', address=0, length=0)])
        for reg in range(32):
            data = sum(((reg*17+k*13+7)&255) << (8*k) for k in range(16))
            if reg == 0:
                data = int('a596'*8, 16)
            if mode in (1, 3) and reg >= 24:
                first = (reg-24)*16//index_width
                data = sum((((first+k)*step) % (1 << (index_width*8))) << (k*index_width*8) for k in range(16//index_width))
            rows.append(dict(kind='R', register=reg, data=data))
        ins((s << 3) << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=length, name='configuration')
        ins(8 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=start, name='vstart')
        fields = (nf-1) << 29 | vm << 25 | 1 << 15 | 8 << 7
        if mode in (1, 3):
            fields |= 24 << 20
        if mode == 2:
            fields |= 2 << 20
        raw = e['match'] | (fields & ~e['mask'])
        ins(raw, memory.BASE+2048, step*stride_mode, name=e['name'], nf=nf, target=True, initial_vstart=start, sew=bits, vm=vm, stride_mode=stride_mode)
    entries = forms()
    for e in entries:
        case(e)
    holes = [e for e in entries if e['name'] in ('vlse16_v', 'vlse64_v', 'vsse16_v', 'vsse64_v') and e['nf'] in (5, 6, 7)]
    assert len(holes) == 12
    for e in holes:
        for stride in (-1, 0, 1):
            for vm, start, length in [(0, 0, 0), (0, 0, 3), (1, 1, 3)]:
                case(e, stride, vm, start, length)
    return rows


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = ROOT/'build/spike-memory-model/results.json'
    model = json.loads(model_path.read_text())
    assert model['status'] == 'PASS' and sha(ROOT/model['binary']) == model['binary_sha256']
    ev = events()
    states = memory.reference(ev, OUT, model)
    lines = []
    success = Counter()
    for e in ev:
        if e['kind'] == 'R':
            lines.append(f'R {e["register"]} {e["data"]:032x}')
        elif e['kind'] == 'M':
            lines.append('M '+e['data'])
        elif e['kind'] == 'F':
            lines.append(f'F {e["address"]:x} {e["length"]:x}')
        else:
            s = states[e['id']]
            assert s['cause'] == 0, ('expected legal expanded form', e, s)
            if e.get('target'):
                success[e['name'], e['nf']] += 1
            values = [e[k] for k in ('id', 'instruction', 'scalar', 'scalar2', 'avl')] + [s[k] for k in ('illegal', 'cause', 'tval', 'writes', 'scalar', 'vl', 'vtype', 'vstart', 'vxrm', 'vxsat', 'frm', 'fflags')]
            lines.append('I '+' '.join(f'{v:x}' for v in values)+' '+s['rf']+' '+s['ram'])
    prior = prior_samples()
    table = []
    for e in forms():
        key = e['name'], e['nf']
        assert success[key] > 0, key
        table.append(dict(name=e['name'], nf=e['nf'], prior_successful_samples=prior[key], new_successful_samples=success[key]))
    missing = [r for r in table if not r['prior_successful_samples']]
    assert len(missing) == 12, missing
    with (OUT/'coverage.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(table)
    (OUT/'stimulus.txt.gz').write_bytes(gzip.compress(('\n'.join(lines)+'\n').encode(), mtime=0))
    for name in ('spike-input.txt', 'spike-output.txt'):
        p = OUT/name
        p.with_suffix(p.suffix+'.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0))
        p.unlink()  # New transient raw reference transport, retained losslessly as gzip.
    artifacts = [model_path, OUT/'stimulus.txt.gz', OUT/'coverage.csv', *OUT.glob('spike-*'), *sorted((OUT/'gold').glob('*.hex')),
                 *[ROOT/'build/m54/gsim/corpus'/label/name for label in ['memory-full', 'edges-full'] for name in ['inputs.json', 'expected.json', 'results.json']]]
    d = dict(status='PASS', commands=len(states), scenarios=sum(e.get('target', False) for e in ev), expanded_memory_forms=len(table),
             previous_forms_with_success=len(table)-len(missing), previous_unsampled_forms=missing, negative_stride_scenarios=36,
             reference='UNMODIFIED_UPSTREAM_SPIKE', model_binary=model['binary'], model_binary_sha256=model['binary_sha256'],
             source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(), ROOT/'tests/m57_isa_catalog.py', ROOT/'tests/test_spike_memory.py']},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (OUT/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    return d


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--top', default='SpinorStandard', choices=['SpinorStandard', 'SpinorDeep'])
    a = p.parse_args()
    if a.prepare_only:
        print('PASS expanded memory oracle', prepare()['commands'])
        return
    reference = json.loads((OUT/'results.json').read_text())
    for group in ('source_sha256', 'artifact_sha256'):
        for rel, h in reference[group].items():
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
        assert f'commands={reference["commands"]} ' in summary
        negatives = {}
        for mode, diagnostic in [('wrong-token', 'completion token mismatch'), ('wrong-rf', 'RF mismatch'), ('wrong-csr', 'CSR mismatch'), ('corrupt-load', 'RF mismatch'), ('wrong-ram', 'RAM mismatch')]:
            with (folder/(mode+'.log')).open('w') as log:
                r = subprocess.run([binary, scratch, mode], cwd=ROOT, env=env(), stdout=log, stderr=log, timeout=30)
            assert r.returncode == 1 and diagnostic in (folder/(mode+'.log')).read_text(), mode
            negatives[mode] = 'REJECTED'
    finally:
        scratch.unlink(missing_ok=True)
    d = dict(status='PASS', top=a.top, commands=reference['commands'], scenarios=reference['scenarios'], summary=summary, trace_replay=False,
             checked_registers_per_command=32, checked_ram_bytes_per_command=8192, negative_controls=negatives,
             source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [binary, cache/'build.json', OUT/'results.json', *folder.glob('*.log')]})
    (folder/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS all 310 memory forms', a.top, reference['commands'], 'commands', flush=True)


if __name__ == '__main__':
    main()
