"""Source layout, comment-only equivalence, and exact historical input lookup.

The layout baseline is a small compressed snapshot, not another compiled source
tree. Historical receipts retain their original paths and hashes.
"""
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / 'scripts/maintenance/source-layout.json'
LOCK = ROOT / 'archive/m61/layout-baseline.json'


@lru_cache(maxsize=None)
def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@lru_cache(maxsize=1)
def baseline():
    lock = json.loads(LOCK.read_text())
    assert sha(ROOT / lock['receipt']) == lock['receipt_sha256'], 'M61 receipt changed'
    assert sha(ROOT / lock['archive']) == lock['archive_sha256'], 'layout baseline changed'
    with ZipFile(ROOT / lock['archive']) as archive:
        assert set(archive.namelist()) == set(lock['member_sha256'])
        files = {name: archive.read(name) for name in archive.namelist()}
    for name, data in files.items():
        assert hashlib.sha256(data).hexdigest() == lock['member_sha256'][name], name
    return lock, files


def scan_scala(source):
    """Return literal-preserving tokens and comment spans, with source offsets.

    Strings, character literals, backtick identifiers and nested block comments
    must be distinguished: removing // inside an assertion string would hide a
    functional edit. This lexical check is supplemented by actual RTL emission.
    """
    tokens, comments = [], []
    i, n = 0, len(source)
    operators = '!#%&*+-/:<=>?@\\^|~'
    while i < n:
        start = i
        if source[i].isspace():
            i += 1
            continue
        if source.startswith('//', i):
            end = source.find('\n', i)
            i = n if end < 0 else end
            comments.append((start, i))
            continue
        if source.startswith('/*', i):
            depth, i = 1, i + 2
            while i < n and depth:
                if source.startswith('/*', i): depth, i = depth + 1, i + 2
                elif source.startswith('*/', i): depth, i = depth - 1, i + 2
                else: i += 1
            assert depth == 0, 'unterminated Scala comment'
            comments.append((start, i))
            continue
        if source.startswith('"""', i):
            end = source.find('"""', i + 3)
            assert end >= 0, 'unterminated triple-quoted string'
            i = end + 3
        elif source[i] in ('"', '`'):
            quote, i = source[i], i + 1
            while i < n and source[i] != quote:
                i += 2 if source[i] == '\\' and quote == '"' else 1
            assert i < n, 'unterminated Scala literal'
            i += 1
        elif source[i] == "'" and (m := re.match(r"'(?:\\.|[^'\\\n])'", source[i:])):
            i += len(m[0])
        elif source[i].isalnum() or source[i] in '_$':
            i += 1
            while i < n and (source[i].isalnum() or source[i] in '_$'): i += 1
        elif source[i] in operators:
            i += 1
            while i < n and source[i] in operators and not source.startswith(('//', '/*'), i): i += 1
        else:
            i += 1
        tokens.append((source[start:i], start, i))
    return tokens, comments


def code_tokens(source):
    return [token for token, _, _ in scan_scala(source)[0]]


def top_level_declarations(tokens):
    """Yield (name, prefix offset, keyword offset) for class/object/trait headers.

    Only scanned tokens participate: declaration-like text in comments or
    literals is never a header. Annotations and access qualifiers belong to the
    header, so its ScalaDoc must precede those prefixes rather than the keyword.
    Nested implementation classes are outside this top-level contract check.
    """
    values = [token for token, _, _ in tokens]
    opening = {'(': ')', '[': ']', '{': '}'}
    modifiers = {'abstract', 'case', 'final', 'implicit', 'inline', 'open',
                 'override', 'private', 'protected', 'sealed', 'transparent'}

    def identifier(value):
        return (value.startswith('`') or
                bool(value) and (value[0].isalpha() or value[0] in '_$'))

    def group_end(index):
        # Annotation arguments can themselves contain blocks and local classes.
        # Consume their balanced delimiters as one prefix, without interpreting
        # argument contents as declarations or as the header's documentation.
        expected = [opening[values[index]]]
        index += 1
        while index < len(values) and expected:
            value = values[index]
            if value in opening: expected.append(opening[value])
            elif value in opening.values():
                if value != expected.pop(): return len(values)
            index += 1
        return index

    def header_keyword(index):
        while index < len(values):
            value = values[index]
            if value in modifiers:
                index += 1
                if value in ('private', 'protected') and index < len(values) and values[index] == '[':
                    index = group_end(index)
            elif value == '@':
                index += 1
                if index >= len(values) or not identifier(values[index]): return None
                index += 1
                while index + 1 < len(values) and values[index] == '.' and identifier(values[index + 1]):
                    index += 2
                while index < len(values) and values[index] in ('[', '('):
                    index = group_end(index)
            else:
                return index if value in ('class', 'object', 'trait') else None
        return None

    index, nesting = 0, []
    while index < len(values):
        if not nesting:
            keyword = header_keyword(index)
            if keyword is not None and keyword + 1 < len(values) and identifier(values[keyword + 1]):
                yield values[keyword + 1], tokens[index][1], tokens[keyword][1]
                index = keyword + 2
                continue
        value = values[index]
        if value in opening: nesting.append(opening[value])
        elif value in opening.values() and nesting and value == nesting[-1]: nesting.pop()
        index += 1


def comment_issues(source, max_gap=40):
    """Check review conventions, not a claim that comment quality is provable."""
    tokens, comments = scan_scala(source)
    starts = [0, *[m.end() for m in re.finditer('\n', source)]]
    line = lambda offset: bisect_right(starts, offset)
    commented = {number for a, b in comments for number in range(line(a), line(max(a, b - 1)) + 1)}
    substantive = {line(a) for token, a, _ in tokens if token not in ('{', '}', '(', ')', ';')}
    worst = run = 0
    for number in range(1, len(starts) + 1):
        if number in commented: run = 0
        elif number in substantive: run += 1; worst = max(worst, run)
    issues = []
    if worst > max_gap: issues.append(f'{worst} substantive lines without a comment (limit {max_gap})')
    comment_ends = [end for _, end in comments]
    for name, prefix, keyword in top_level_declarations(tokens):
        previous = bisect_right(comment_ends, prefix) - 1
        documented = False
        if previous >= 0:
            start, end = comments[previous]
            documented = source.startswith('/**', start) and not source[end:prefix].strip()
        if not documented:
            issues.append(f'{name} at line {line(keyword)} needs declaration ScalaDoc')
    return worst, issues


def check_sources(verify_equivalence=False):
    layout = json.loads(LAYOUT.read_text())
    mapping = layout['moved_sources']
    if verify_equivalence:
        lock, old = baseline()
        receipt = json.loads((ROOT / lock['receipt']).read_text())
        expected = {rel: digest for rel, digest in receipt['source_sha256'].items() if rel.endswith('.scala')}
        assert set(mapping) == set(expected) and len(mapping) == 56
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'src/main/scala').rglob('*.scala')}
    assert actual == set(mapping.values()), 'unmapped or missing Scala sources'
    gaps, changes = {}, []
    for previous, current in mapping.items():
        revised = (ROOT / current).read_text()
        if verify_equivalence:
            assert hashlib.sha256(old[previous]).hexdigest() == expected[previous], previous
            original = old[previous].decode()
            assert code_tokens(original) == code_tokens(revised), ('Scala code tokens changed', current)
            if original != revised: changes.append(current)
        worst, problems = comment_issues(revised)
        assert not problems, (current, problems)
        gaps[current] = worst
    return dict(sources=len(mapping),commented_sources=len(changes) if verify_equivalence else None,
                max_uncommented_code_lines=max(gaps.values()),per_file_max_uncommented_lines=gaps,
                scala_code_tokens_unchanged=True if verify_equivalence else None)


def check_evidence_binding(rel, digest):
    """Resolve an exact old input; never substitute today's changed contents."""
    path = ROOT / rel
    if path.is_file() and sha(path) == digest: return 'current'
    lock, old = baseline()
    if lock['member_sha256'].get(rel) == digest:
        assert hashlib.sha256(old[rel]).hexdigest() == digest
        return 'layout-snapshot'
    from maintenance.retention import matches_original
    if matches_original(rel, digest): return 'retained-original'
    for folder in ('archive/docs-m60/source', 'archive/m60/source'):
        candidate = ROOT / folder / rel
        if candidate.is_file() and sha(candidate) == digest: return folder
    from m60_evidence import resolve
    assert sha(resolve(rel, digest)) == digest, rel
    return 'historical-snapshot'
