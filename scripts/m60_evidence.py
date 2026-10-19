"""Current M60 bindings and exact read-only prior-version resolution."""
import json
from m59_evidence import ROOT, sha, VERSIONED, resolve as older, baseline as prior_baseline
from m58_evidence import check as current_check


def resolve(rel, expected):
    p = ROOT / rel
    if p.is_file() and sha(p) == expected: return p
    if rel in VERSIONED:
        p = ROOT / 'archive/m59/source' / rel
        if p.is_file() and sha(p) == expected: return p
    return older(rel, expected)


def check(d, historical=False):
    if not historical: return current_check(d)
    count = 0
    for group in ('source_sha256', 'artifact_sha256'):
        for rel, expected in d.get(group, {}).items():
            resolve(rel, expected); count += 1
    return count


def baseline():
    locked = json.loads((ROOT/'archive/m59/baseline.json').read_text())
    assert locked['m59_check_only_passed'] and not locked['hardware_changed']
    assert sha(ROOT/'reports/m59/receipt.json') == locked['receipt_sha256']
    for rel, expected in locked['archive_sha256'].items(): assert sha(ROOT/rel) == expected, rel
    previous = json.loads((ROOT/'reports/m59/receipt.json').read_text())
    bindings = check(previous, historical=True)
    expected = {rel:h for rel,h in previous['source_sha256'].items() if rel.endswith('.scala')}
    actual = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert actual == expected, 'M60 does not change hardware'
    return dict(status='PASS', prior_commit=locked['commit'], hardware_sources_unchanged=len(actual),
                m59_checked_bindings=bindings, retained_baseline=prior_baseline())
