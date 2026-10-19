"""Strict independent parser for the frozen upstream opcode data (not RTL)."""
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse(text, source):
    entries = []
    names = set()
    for number, line in enumerate(text.splitlines(), 1):
        words = line.split('#', 1)[0].split()
        if not words:
            continue
        name = words[0].replace('.', '_')
        assert not name.startswith('$'), ('unhandled upstream directive', source, number)
        assert name not in names, ('duplicate name', name)
        names.add(name)
        match = mask = 0
        for token in words[1:]:
            if '=' not in token:
                assert re.fullmatch(r'[a-z][a-z0-9_]*', token), token
                continue
            field, value = token.split('=')
            bounds = field.split('..')
            assert len(bounds) in (1, 2) and all(x.isdecimal() for x in bounds), token
            hi, lo = int(bounds[0]), int(bounds[-1])
            assert 0 <= lo <= hi < 32, token
            value = int(value, 0)
            assert 0 <= value < 1 << (hi - lo + 1), token
            bits = ((1 << (hi - lo + 1)) - 1) << lo
            assert not mask & bits, ('overlapping encoding fields', token)
            mask |= bits
            match |= value << lo
        assert mask & 0x7f == 0x7f and not match & ~mask, name
        entries.append(dict(name=name, match=match, mask=mask, source=source, line=number))
    return entries


def catalog():
    refs = json.loads((ROOT / 'docs/references/m57-sources.json').read_text())
    for r in refs['sources']:
        assert hashlib.sha256((ROOT / r['file']).read_bytes()).hexdigest() == r['sha256'], r['file']
    base = parse((ROOT/'docs/references/m57-rv-v').read_text(), 'docs/references/m57-rv-v')
    bb = parse((ROOT/'docs/references/m57-rv-zvbb').read_text(), 'docs/references/m57-rv-zvbb')
    assert len(base) == 375 and len(bb) == 16
    for row in base:
        row['extension'] = 'V'
    for row in bb:
        row['extension'] = 'Zvbb'
    return base + bb


def compare(entries, coverage):
    actual = {r['name']: r for r in coverage}
    assert len(actual) == len(coverage), 'duplicate coverage name'
    expected = {e['name'] for e in entries}
    assert set(actual) == expected, dict(missing=sorted(expected-set(actual)), unexpected=sorted(set(actual)-expected))
    rows = []
    for e in entries:
        r = actual[e['name']]
        assert int(r['match'], 16) == e['match'] and int(r['mask'], 16) == e['mask'], e['name']
        assert int(r['successful_direct_samples']) > 0, e['name']
        rows.append(dict(e, family=r['family'], successful_direct_samples=int(r['successful_direct_samples'])))
    return rows


def audited_catalog():
    with (ROOT/'reports/m55/canonical-coverage.csv').open() as f:
        return compare(catalog(), list(csv.DictReader(f)))


def negative_controls():
    entries = catalog()
    with (ROOT/'reports/m55/canonical-coverage.csv').open() as f:
        original = list(csv.DictReader(f))
    for mode in ('missing', 'encoding', 'mask', 'no-success', 'duplicate', 'unexpected'):
        rows = [dict(r) for r in original]
        if mode == 'missing':
            rows.pop()
        elif mode in ('encoding', 'mask'):
            key = 'match' if mode == 'encoding' else 'mask'
            rows[0][key] = hex(int(rows[0][key], 16) ^ (1 << 26))
        elif mode == 'no-success':
            rows[0]['successful_direct_samples'] = '0'
        elif mode == 'duplicate':
            rows.append(dict(rows[0]))
        else:
            rows.append(dict(rows[0], name='invented_instruction'))
        try:
            compare(entries, rows)
        except AssertionError:
            continue
        raise AssertionError(('catalog checker missed corruption', mode))
    return 6


if __name__ == '__main__':
    rows = audited_catalog()
    print('PASS independent opcode catalog', len(rows), 'encodings;', negative_controls(), 'corruptions rejected')
