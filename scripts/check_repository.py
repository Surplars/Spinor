#!/usr/bin/env python3
"""Check the current source organization without overwriting milestone evidence."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
from maintenance.layout import ROOT, LAYOUT, LOCK, sha, baseline, check_sources, check_evidence_binding
from maintenance.retention import read_receipt, check_layout as check_retention_layout

DOCUMENTS = ['README.md','CURRENT.md','src/README.md','scripts/README.md','tests/README.md',
             'docs/README.md','docs/repository.md','docs/development.md','docs/integration.md',
             'docs/cpu-spinor-contract.md','docs/tilelink.md','docs/monitor-soc.md','docs/architecture.md',
             'docs/validation.md','docs/m61-isolation.md','docs/artifacts.md','reports/README.md',
             'archive/README.md','reports/retention/evaluation.md']
HASH_GROUPS = ('source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256',
               'external_source_sha256','external_tool_dependency_sha256')


def maintenance_inputs():
    """Inputs to this maintenance check, including migrated helper programs."""
    paths = [*sorted((ROOT/'src').rglob('*.scala')), *[ROOT/p for p in DOCUMENTS],
             *[ROOT/p for p in ('Makefile','scripts/legacy.mk','build.mill','mill',
                               '.mill-version','.mill-jvm-opts','tools.lock.json',
                               'scripts/check_repository.py','scripts/check_docs.py',
                               'scripts/maintenance/layout.py','tests/test_repository_checks.py',
                               'scripts/maintenance/retention.py','scripts/retained_artifacts.py',
                               'tests/test_retention.py','reports/retention/manifest.json')], LAYOUT]
    lock, _ = baseline()
    paths += [ROOT/p for p in lock['member_sha256']
              if p.startswith(('scripts/','tests/')) and (ROOT/p).is_file()]
    return sorted(set(paths))


def input_snapshot():
    """Read uncached hashes so edits during elaboration cannot be misattributed."""
    lock, _ = baseline()
    paths = [*maintenance_inputs(), LOCK, ROOT/lock['archive'], ROOT/lock['receipt']]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def check_utility_migration():
    """Only path literals and source-directory recursion may change in helpers.

    Comparing Python ASTs preserves reference numbers, checks and command logic;
    historical programs are inspected without running or replacing their output.
    """
    _, old = baseline()
    mapping = json.loads(LAYOUT.read_text())['moved_sources']
    counts = dict(files=0,path_literals=0,recursive_globs=0)

    class MigratePaths(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str) and node.value in mapping:
                node.value = mapping[node.value]
                counts['path_literals'] += 1
            return node

        def visit_Call(self,node):
            self.generic_visit(node)
            if (isinstance(node.func,ast.Attribute) and node.func.attr=='glob'
                and isinstance(node.func.value,ast.BinOp)
                and isinstance(node.func.value.op,ast.Div)
                and isinstance(node.func.value.right,ast.Constant)
                and node.func.value.right.value=='src/main/scala/vpu'
                and len(node.args)==1 and isinstance(node.args[0],ast.Constant)
                and node.args[0].value in ('*.scala','Staged*.scala')):
                node.func.attr = 'rglob'
                counts['recursive_globs'] += 1
            return node

    for rel, data in old.items():
        if not rel.startswith(('scripts/','tests/')) or not rel.endswith('.py') or rel=='scripts/check_docs.py':
            continue
        expected = MigratePaths().visit(ast.parse(data))
        actual = ast.parse((ROOT/rel).read_text())
        assert ast.dump(expected)==ast.dump(actual), ('unexpected utility logic change',rel)
        counts['files'] += 1
    print('PASS utility path migration:',counts,flush=True)
    return counts


def check_links():
    links = 0
    for rel in DOCUMENTS:
        for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', (ROOT/rel).read_text()):
            url = urlsplit(target.strip().strip('<>'))
            if url.scheme or url.netloc or not url.path: continue
            dest = ((ROOT/rel).parent / unquote(url.path)).resolve()
            assert dest.is_relative_to(ROOT) and dest.exists(), (rel, target)
            links += 1
    return dict(pages=len(DOCUMENTS),local_links=links)


def audit_evidence():
    counts = {}
    for milestone in range(50, 62):
        data = read_receipt(f'reports/m{milestone}/receipt.json')
        assert data['status'] == 'PASS', milestone
        for group in HASH_GROUPS:
            for rel, digest in data.get(group, {}).items():
                origin = check_evidence_binding(rel, digest)
                counts[origin] = counts.get(origin, 0) + 1
        if 'binary' in data:
            check_evidence_binding(data['binary'], data['binary_sha256'])
            counts['binary'] = counts.get('binary', 0) + 1
    print('PASS retained M50-M61 evidence:', sum(counts.values()), 'exact bindings', flush=True)
    return counts


def check_rtl():
    """Compare complete emitted SV, including the module hierarchy, to M61.

    The eight outputs use a new /tmp location; accepted build/m61 artifacts are
    read-only. Comment/path edits do not warrant relabeling old simulation runs.
    """
    receipt = json.loads((ROOT/'reports/m61/receipt.json').read_text())
    models = {'host':('standard','host','SpinorHost','SpinorIsolated'),
              'deep':('deep','host','SpinorHostDeep','SpinorIsolatedDeep'),
              'standalone':('standard','standalone','SpinorStandard','SpinorIsolatedStandalone'),
              'integer':('integer-deep','standalone','SpinorIntegerDeep','SpinorIsolatedInteger')}
    result = {}
    for model, (preset, fcsr, direct, isolated) in models.items():
        for kind, top, entry in (('direct',direct,'GenerateConfigured'),('isolated',isolated,'GenerateIsolated')):
            rel = (f'build/m61/legacy/{model}/{top}.sv.gz' if kind=='direct' else f'build/m61/rtl/{model}/{top}.sv.gz')
            assert sha(ROOT/rel) == receipt['artifact_sha256'][rel], rel
            reference = gzip.decompress((ROOT/rel).read_bytes())
            folder = Path('/tmp/spinor-source-layout')/kind/model
            folder.mkdir(parents=True, exist_ok=True)
            with (folder/'generate.log').open('w') as log:
                subprocess.run([ROOT/'mill','Vpu.runMain',f'vpu.{entry}','--out',folder,'--name',top,
                                '--preset',preset,'--fcsr-owner',fcsr],cwd=ROOT,stdout=log,stderr=log,check=True,timeout=300)
            assert (folder/(top+'.sv')).read_bytes() == reference, ('RTL differs from M61', top)
            result[top] = dict(byte_identical=True,sv_sha256=hashlib.sha256(reference).hexdigest(),reference=rel)
            print('PASS byte-identical RTL:',top,flush=True)
    return result


def record(result):
    assert result.get('rtl') and result.get('historical_evidence'), '--record requires --rtl --evidence'
    folder = ROOT/'reports/repository-layout';folder.mkdir(exist_ok=True)
    source_paths = maintenance_inputs()
    lock, _ = baseline()
    text = f'''# Repository layout and comment maintenance

Hardware baseline: M61, commit `{lock['baseline_commit']}`.

All {result['source']['sources']} Scala files are grouped by responsibility. Their Scala code tokens
are unchanged; edits are comments, whitespace, and source locations. Public `vpu.*`
class names and Mill generation commands remain available. Every top-level declaration
has ScalaDoc; the maximum uncommented substantive-code span is {result['source']['max_uncommented_code_lines']} lines.
This is a maintenance convention, not a measure of functional correctness.

Eight complete generated SystemVerilog tops match the accepted M61 outputs byte for byte:
direct and isolated standard host, Deep host, standard standalone, and integer-deep.
The organization therefore adds no RTL change to those configurations. The existing
M61 numerical and conditional timing evidence keeps its original scope; this cleanup
does not claim a new simulation campaign or a new device timing result.

Retained M50–M61 receipts: {sum(result['historical_evidence'].values()):,} exact input/artifact bindings checked.
Original paths and hashes resolve through existing archives or the compressed M61
layout snapshot. Historical receipts and build artifacts were not rewritten.

The root Makefile now defaults to help. Historical recipes are explicit in
`scripts/legacy.mk`. Current helper paths and recursive source/notice discovery were
migrated. Python AST comparison of {result['utility_migration']['files']} migrated helpers confirms
only {result['utility_migration']['path_literals']} source path literals and {result['utility_migration']['recursive_globs']} recursive source searches changed.
All maintenance input hashes were re-read after verification to reject concurrent edits.
See [source map](../../src/README.md), [development conventions](../../docs/development.md),
and [verification instructions](../../docs/validation.md).

```sh
make check
make check-rtl       # requires retained M61 reference SV and Mill tools
make audit-evidence # requires retained historical tools/build artifacts
```
'''
    (folder/'evaluation.md').write_text(text)
    source_paths.append(folder/'evaluation.md')
    artifacts = [LOCK,ROOT/lock['archive'],ROOT/lock['receipt'],
                 *[ROOT/item['reference'] for item in result['rtl'].values()]]
    result.update(status='PASS',hardware_changed=False,
                  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source_paths},
                  artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
    (folder/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl',action='store_true',help='emit eight tops into /tmp and compare with retained M61 SV')
    parser.add_argument('--evidence',action='store_true',help='audit retained M50-M61 receipt inputs; needs build/tools')
    parser.add_argument('--record',action='store_true',help='write the maintenance receipt after both complete checks')
    args = parser.parse_args()
    if args.record and not (args.rtl and args.evidence): parser.error('--record requires --rtl --evidence')
    before = input_snapshot() if args.rtl or args.evidence else None
    result = dict(source=check_sources(verify_equivalence=args.rtl),documentation=check_links())
    result['retention'] = check_retention_layout()
    print('PASS source layout/comments and documentation:',result['source']['sources'],'Scala sources;',
          result['documentation']['local_links'],'local links',flush=True)
    if args.rtl:
        result['utility_migration'] = check_utility_migration()
        result['rtl'] = check_rtl()
    if args.evidence: result['historical_evidence'] = audit_evidence()
    if before is not None:
        assert input_snapshot()==before, 'maintenance inputs changed during verification; rerun'
        result['inputs_stable_during_verification'] = True
    if args.record: record(result)


if __name__ == '__main__': main()
