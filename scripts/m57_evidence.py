"""Read-only version resolution for retained M50--M56 evidence and new audits."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
DOCS = {'README.md', 'CURRENT.md', '.gitattributes', 'docs/isa-coverage.md', 'docs/rvv-completion-plan.md'}
OLD_VERSIONED = {'src/main/scala/vpu/'+n for n in [
    'Protocol.scala', 'RamVector.scala', 'SpinorParams.scala', 'MemoryRamVector.scala',
    'VectorMemoryEngine.scala', 'VpuMonitor.scala', 'GenerateConfigured.scala',
    'IntegerLane.scala', 'FloatingPointConvertResize.scala']}
OLD_VERSIONED |= {'README.md', 'CURRENT.md', '.gitattributes', 'docs/cpu-spinor-contract.md'}


def resolve(rel, expected):
    p = ROOT/rel
    if p.is_file() and sha(p) == expected:
        return p
    if rel in DOCS:
        archived = ROOT/'archive/m56/source'/rel
        if archived.is_file() and sha(archived) == expected:
            return archived
    if rel in OLD_VERSIONED:
        for m in (53, 54, 55):
            archived = ROOT/f'archive/m{m}/source'/rel
            if archived.is_file() and sha(archived) == expected:
                return archived
    raise AssertionError(('unexpected retained evidence mutation', rel))


def check(d, historical=False):
    count = 0
    for group in ('source_sha256', 'artifact_sha256', 'sha256', 'input_sha256',
                  'netlist_sha256', 'external_source_sha256', 'external_tool_dependency_sha256'):
        for rel, expected in d.get(group, {}).items():
            if historical:
                resolve(rel, expected)
            else:
                assert sha(ROOT/rel) == expected, rel
            count += 1
    if 'binary' in d:
        assert sha(ROOT/d['binary']) == d['binary_sha256']
        count += 1
    return count


def baseline():
    locked = json.loads((ROOT/'archive/m56/baseline.json').read_text())
    assert locked['m56_check_only_passed'] and not locked['hardware_changed']
    assert sha(ROOT/'reports/m56/receipt.json') == locked['receipt_sha256']
    for rel, expected in locked['archive_sha256'].items():
        assert sha(ROOT/rel) == expected, rel
    prior = json.loads((ROOT/'reports/m56/receipt.json').read_text())
    bindings = check(prior, historical=True)
    expected_rtl = {rel: h for rel, h in prior['source_sha256'].items() if rel.endswith('.scala')}
    actual_rtl = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert actual_rtl == expected_rtl, 'M57 ISA audit must not alter hardware sources'
    historical_reports = {}
    for m in (53, 54, 55):
        archive = json.loads((ROOT/f'archive/m{m}/baseline.json').read_text())
        for rel, h in archive['archive_sha256'].items():
            assert sha(ROOT/rel) == h, rel
    for rel, h in json.loads((ROOT/'archive/m55/baseline.json').read_text())['reports'].items():
        assert sha(ROOT/rel) == h, rel
        historical_reports[rel] = check(json.loads((ROOT/rel).read_text()), historical=True)
    return dict(status='PASS', prior_commit=locked['commit'], hardware_sources_unchanged=len(actual_rtl),
                m56_checked_bindings=bindings, historical_checked_bindings=historical_reports)
