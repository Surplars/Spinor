#!/usr/bin/env python3
"""Check current documentation and resolve exact pre-edit document evidence.

No old receipt is rewritten. Only the eight explicitly frozen text inputs can
resolve through docs-m60; hardware, reference programs and artifacts stay strict.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
from m60_evidence import resolve as historical_resolve

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    'README.md', 'CURRENT.md', 'docs/README.md', 'docs/integration.md',
    'docs/repository.md', 'docs/cpu-spinor-contract.md', 'docs/tilelink.md',
    'docs/monitor-soc.md', 'docs/architecture.md', 'docs/validation.md',
]
FROZEN = {
    'README.md', 'CURRENT.md', '.gitattributes', 'docs/repository.md',
    'docs/cpu-spinor-contract.md', 'docs/tilelink.md', 'docs/monitor-soc.md', 'docs/architecture.md',
}
GROUPS = ('source_sha256', 'artifact_sha256', 'sha256', 'input_sha256', 'netlist_sha256',
          'external_source_sha256', 'external_tool_dependency_sha256')
CACHE = {}


def sha(path):
    path = path.resolve()
    if path not in CACHE:
        with path.open('rb') as stream:
            CACHE[path] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return CACHE[path]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', action='store_true', help='also requires retained M50--M60 build/tools artifacts')
    args = parser.parse_args()
    locked = json.loads((ROOT/'archive/docs-m60/baseline.json').read_text())
    assert locked['baseline_commit'] == '0790a6e12b2102978a3c821055aed14336b30929'
    assert locked['m60_check_only_passed_before_edit'] and not locked['hardware_changed']
    assert set(locked['documents']) == FROZEN
    prior = ROOT/locked['baseline_receipt']
    assert sha(prior) == locked['baseline_receipt_sha256'], 'M60 receipt changed'
    for rel, item in locked['documents'].items():
        assert item['archived'] == 'archive/docs-m60/source/' + rel
        assert sha(ROOT/item['archived']) == item['sha256'], rel
    receipt = json.loads(prior.read_text())
    expected = {rel:h for rel,h in receipt['source_sha256'].items() if rel.endswith('.scala')}
    actual = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert actual == expected and len(actual) == 54, 'documentation update must not change RTL'
    links = 0
    for rel in DOCUMENTS:
        text = (ROOT/rel).read_text()
        for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
            target = target.strip().strip('<>')
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path: continue
            dest = ((ROOT/rel).parent / unquote(url.path)).resolve()
            assert dest.is_relative_to(ROOT) and dest.exists(), (rel, target)
            links += 1
    assert 'Valence SoC / Orbital CPU / Spinor VPU' not in (ROOT/'README.md').read_text()
    print(f'PASS documentation: {len(DOCUMENTS)} pages, {links} local links, 8 exact snapshots, 54 unchanged Scala sources', flush=True)
    if not args.evidence: return

    def resolve(rel, h):
        path = ROOT/rel
        if path.is_file() and sha(path) == h: return path
        item = locked['documents'].get(rel)
        if item and item['sha256'] == h: return ROOT/item['archived']
        return historical_resolve(rel, h)

    count = snapshots = 0
    for milestone in range(50, 61):
        path = ROOT/f'reports/m{milestone}/receipt.json'
        data = json.loads(path.read_text()); assert data['status'] == 'PASS', str(path)
        for group in GROUPS:
            for rel,h in data.get(group, {}).items():
                resolved = resolve(rel, h)
                assert sha(resolved) == h, (path.name, rel)
                count += 1; snapshots += str(resolved).startswith(str(ROOT/'archive/docs-m60/source'))
        if 'binary' in data:
            assert sha(ROOT/data['binary']) == data['binary_sha256']; count += 1
    print(f'PASS retained M50--M60 evidence: {count} exact bindings, {snapshots} explicit document snapshot resolutions; no simulation rerun', flush=True)


if __name__ == '__main__': main()
