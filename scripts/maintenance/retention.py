"""Read original evidence from compressed receipts or pinned Git objects.

The manifest preserves original paths, sizes and SHA256 digests. A compact
receipt index is never mistaken for the original accepted receipt. Git history
is read locally; recovery does not fetch, reset, or overwrite the working tree.
"""
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT/'reports/retention/manifest.json'


@lru_cache(maxsize=1)
def manifest():
    data = json.loads(MANIFEST.read_text())
    assert data['schema_version'] == 1
    for rel, item in data['entries'].items():
        assert not Path(rel).is_absolute() and '..' not in Path(rel).parts, rel
        assert len(item['sha256']) == 64 and len(item['git_blob']) == 40, rel
        if item['storage'] == 'gzip':
            path = Path(item['compressed_path'])
            assert not path.is_absolute() and '..' not in path.parts, rel
        else:
            assert item['storage'] == 'git', rel
    return data


def original_bytes(rel):
    """Return exact pre-cleanup bytes, checking size and digest before use."""
    item = manifest()['entries'][rel]
    if item['storage'] == 'gzip':
        compressed = (ROOT/item['compressed_path']).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == item['compressed_sha256'], rel
        data = gzip.decompress(compressed)
    else:
        result = subprocess.run(['git','cat-file','blob',item['git_blob']],cwd=ROOT,
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError(f'{rel}: original Git object is unavailable. Use a full clone '
                               f'or fetch commit {manifest()["baseline_commit"]}.')
        data = result.stdout
    assert len(data) == item['bytes'], ('retained size differs',rel)
    assert hashlib.sha256(data).hexdigest() == item['sha256'], ('retained digest differs',rel)
    return data


@lru_cache(maxsize=None)
def verify_entry(rel):
    # Cache only successful verification, not hundreds of megabytes of netlists.
    original_bytes(rel)
    return True


def matches_original(rel, digest):
    item = manifest()['entries'].get(rel)
    return bool(item and item['sha256'] == digest and verify_entry(rel))


def read_receipt(rel):
    """Load full receipt fields even when the visible JSON is a compact index."""
    item = manifest()['entries'].get(rel)
    data = original_bytes(rel) if item and item['kind'] == 'compressed-receipt' else (ROOT/rel).read_bytes()
    return json.loads(data)


def check_layout():
    """Check small indexes and compressed copies without requiring Git history."""
    copies = set()
    entries = manifest()['entries']
    for rel, item in entries.items():
        if item['storage'] == 'gzip' and item['compressed_path'] not in copies:
            packed = (ROOT/item['compressed_path']).read_bytes()
            assert hashlib.sha256(packed).hexdigest() == item['compressed_sha256'], rel
            copies.add(item['compressed_path'])
        if item['kind'] == 'compressed-receipt':
            index = json.loads((ROOT/rel).read_text())
            assert index['format'] == 'spinor-compressed-receipt-index-v1', rel
            assert index['original_sha256'] == item['sha256'] and index['original_bytes'] == item['bytes'], rel
            assert index['full_receipt'] == Path(item['compressed_path']).name, rel
        elif item['kind'] != 'maintenance-input':
            assert not (ROOT/rel).exists(), ('expanded artifact was reintroduced',rel)
    return dict(entries=len(entries),compressed_receipts=len(copies))
