"""Current M58 evidence and strict version resolution for unchanged prior RTL."""
import json
from m57_evidence import ROOT,sha,resolve as older,baseline as m56_baseline

VERSIONED={'.gitattributes','README.md','CURRENT.md','docs/isa-coverage.md','docs/rvv-completion-plan.md'}


def resolve(rel,h):
    p=ROOT/rel
    if p.is_file() and sha(p)==h:return p
    if rel in VERSIONED:
        p=ROOT/'archive/m57/source'/rel
        if p.is_file() and sha(p)==h:return p
    return older(rel,h)


def check(d,historical=False):
    count=0
    for group in ('source_sha256','artifact_sha256','sha256','input_sha256','netlist_sha256','external_source_sha256','external_tool_dependency_sha256'):
        for rel,h in d.get(group,{}).items():
            if historical:resolve(rel,h)
            else:assert sha(ROOT/rel)==h,rel
            count+=1
    if 'binary' in d:assert sha(ROOT/d['binary'])==d['binary_sha256'];count+=1
    return count


def baseline():
    locked=json.loads((ROOT/'archive/m57/baseline.json').read_text())
    assert locked['m57_check_only_passed'] and not locked['hardware_changed']
    assert sha(ROOT/'reports/m57/receipt.json')==locked['receipt_sha256']
    for rel,h in locked['archive_sha256'].items():assert sha(ROOT/rel)==h,rel
    prior=json.loads((ROOT/'reports/m57/receipt.json').read_text());bindings=check(prior,historical=True)
    expected={rel:h for rel,h in prior['source_sha256'].items() if rel.endswith('.scala')}
    actual={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'src/main/scala').rglob('*.scala')}
    assert actual==expected,'M58 does not change hardware'
    return dict(status='PASS',prior_commit=locked['commit'],m57_checked_bindings=bindings,
                hardware_sources_unchanged=len(actual),m56_and_historical=m56_baseline())
