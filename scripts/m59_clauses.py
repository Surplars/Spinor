"""Literal geometry anchors plus bit-preservation checks on independent results."""
from collections import Counter
import gzip
import json
import sys
from m59_evidence import ROOT, sha, check
sys.path.insert(0, str(ROOT / 'tests'))
from m59_arch import Model, cases, groups, overlaps, reasons


def preservation(c, result):
    old = sum(v << (128*r) for r, v in enumerate(c['registers']))
    new = sum(v << (128*r) for r, v in enumerate(result['registers']))
    if result['illegal']:
        assert new == old, 'illegal RF changed'
        assert result['vstart'] == c['start'], 'illegal vstart changed'
        assert result['fflags'] == c['flags'] and result['vxsat'] == c['vcsr'] & 1, 'illegal flags changed'
        return Counter(rejected_preserved=1)
    dest, _ = groups(c)
    width = dest['width']
    region = ((1 << (128*dest['count'])) - 1) << (128*dest['base'])
    assert (new ^ old) & ~region == 0, 'non-destination RF changed'
    count = Counter()
    for i in range(128*dest['count']//width):
        kind = 'prestart' if i < c['start'] else 'tail' if i >= c['vl'] else 'inactive' if not c['vm'] and not (c['registers'][0] >> i & 1) else None
        if kind:
            bits = ((1 << width) - 1) << (128*dest['base'] + i*width)
            assert (new ^ old) & bits == 0, kind + ' changed'
            count[kind + '_elements'] += 1
    assert result['vstart'] == 0, 'success did not clear vstart'
    if c['start'] >= c['vl']:
        assert new == old, 'no-op RF changed'
        assert result['fflags'] == c['flags'] and result['vxsat'] == c['vcsr'] & 1, 'no-op flags changed'
        count['no_op'] += 1
    return count


def main():
    # Expected legal/illegal decisions below are explicit examples, not derived
    # from the interval predicate or from DUT behavior.
    anchors = [
        ('wide-high', 'vwaddu_vv', 8, 0, 8, 9, 24, 1, True),
        ('wide-low', 'vwaddu_vv', 8, 0, 8, 8, 24, 1, False),
        ('fraction-wide-alias', 'vwaddu_vv', 8, 7, 8, 8, 24, 1, False),
        ('fraction-wide-disjoint', 'vwaddu_vv', 8, 7, 8, 16, 24, 1, True),
        ('narrow-low', 'vnsrl_wv', 8, 0, 8, 8, 24, 1, True),
        ('narrow-high', 'vnsrl_wv', 8, 0, 9, 8, 24, 1, False),
        ('narrow-source-eew', 'vnsrl_wv', 8, 0, 16, 8, 8, 1, False),
        ('mac-old-dest-source-eew', 'vwmaccu_vv', 8, 0, 8, 9, 24, 1, False),
        ('extend-high', 'vzext_vf4', 32, 3, 8, 14, 24, 1, True),
        ('extend-low', 'vzext_vf4', 32, 3, 8, 8, 24, 1, False),
        ('extend-middle', 'vzext_vf4', 32, 3, 8, 12, 24, 1, False),
        ('mask-low', 'vmseq_vv', 8, 1, 8, 8, 24, 1, True),
        ('mask-high', 'vmseq_vv', 8, 1, 9, 8, 24, 1, False),
        ('gather-dest-index', 'vrgather_vv', 8, 0, 8, 16, 8, 1, False),
        ('gather-source-alias', 'vrgather_vv', 8, 0, 8, 16, 16, 1, True),
        ('gather-index-eew', 'vrgatherei16_vv', 8, 0, 8, 16, 16, 1, False),
        ('gather-index-same-eew', 'vrgatherei16_vv', 16, 0, 8, 16, 16, 1, True),
        ('slide-up-alias', 'vslideup_vx', 8, 0, 8, 8, 24, 1, False),
        ('slide-down-alias', 'vslidedown_vx', 8, 0, 8, 8, 24, 1, True),
        ('mask-source-eew', 'vadd_vv', 8, 0, 8, 0, 24, 0, False),
        ('mask-destination', 'vadd_vv', 8, 0, 0, 16, 24, 0, False),
        ('unaligned', 'vadd_vv', 8, 1, 9, 16, 24, 1, False),
        ('range', 'vadd_vv', 8, 3, 31, 16, 24, 1, False),
    ]
    anchor_rows = []
    for ident, name, sew, lmul, vd, vs2, vs1, vm, legal in anchors:
        c = dict(name=name, sew=sew, lmul=lmul, vd=vd, vs2=vs2, vs1=vs1, vm=vm)
        bad = reasons(c)
        assert (not bad) == legal, (ident, bad)
        anchor_rows.append(dict(id=ident, case=c, legal=legal, reasons=bad))
    count = Counter(); coverage = {}; inputs = []; negatives = set()
    model = Model()
    for sew in (8, 16, 32, 64):
        path = ROOT / f'build/m59/corpus/sew{sew}/results.json'
        d = json.loads(path.read_text()); check(d); inputs.append(path)
        # Re-read the emitted full-RF expectation, not just a second model run.
        with gzip.open(path.parent / 'stimulus.txt.gz', 'rt') as stream:
            for c in cases(sew):
                for _ in range(32): assert next(stream).startswith('R ')
                for _ in range(5):
                    words = next(stream).split(); command = next(stream).split()
                regs = [int(words[1+2*r], 16) | int(words[2+2*r], 16) << 64 for r in range(32)]
                result = dict(registers=regs, illegal=int(command[6], 16), vstart=int(command[13], 16),
                              fflags=int(command[17], 16), vxsat=int(command[15], 16))
                expected = model.execute(c)
                assert result == {k: expected[k] for k in result}, 'corpus/model disagreement'
                count.update(preservation(c, result))
                count['cases'] += 1
                if result['illegal']: continue
                count['legal'] += 1
                coverage.setdefault(c['name'], Counter())['legal'] += 1
                if result['fflags'] != c['flags']: count['flags_changed_targets'] += 1
                if result['vxsat'] != c['vcsr'] & 1: count['saturation_changed_targets'] += 1
                if c['start'] > 0:
                    count['nonzero_start_legal'] += 1
                    if c['start'] < c['vl']:
                        coverage[c['name']]['resume_with_work'] += 1
                        count['resume_with_work'] += 1
                        if c['vm'] or any(c['registers'][0] >> i & 1 for i in range(c['start'], c['vl'])):
                            count['resume_active_targets'] += 1
                            coverage[c['name']]['resume_active_targets'] += 1
                        else:
                            count['resume_all_masked_targets'] += 1
                dest, src = groups(c)
                for source in src:
                    if overlaps(dest, source):
                        kind = 'same' if dest['width'] == source['width'] else 'narrow-low' if dest['width'] < source['width'] else 'wide-high'
                        count['legal_overlap_' + kind] += 1
                        if 0 < c['start'] < c['vl']:
                            count['resume_overlap_' + kind] += 1
                if c['start'] > 0 and c['vl'] > c['start'] and 'prestart' not in negatives:
                    bad = dict(result, registers=list(regs)); bad['registers'][c['vd']] ^= 1
                    try: preservation(c, bad)
                    except AssertionError as e:
                        assert 'prestart changed' in str(e); negatives.add('prestart')
                    else: raise AssertionError('prestart corruption accepted')
                if c['start'] >= c['vl'] and 'no-op-flags' not in negatives:
                    bad = dict(result, fflags=result['fflags'] ^ 1)
                    try: preservation(c, bad)
                    except AssertionError as e:
                        assert 'no-op flags changed' in str(e); negatives.add('no-op-flags')
                    else: raise AssertionError('no-op flag corruption accepted')
            assert not stream.read(), 'extra corpus events'
    assert len(coverage) == 26 and all(v['resume_active_targets'] > 0 for v in coverage.values())
    assert negatives == {'prestart', 'no-op-flags'}
    spec = ROOT / 'docs/references/m57-v-spec-maintained.adoc'
    lines = spec.read_text().splitlines()
    clauses = []
    for ident, lo, hi in [('source-eew', 977, 983), ('destination-overlap', 990, 1008), ('vstart-state', 547, 556)]:
        clauses.append(dict(id=ident, source=str(spec.relative_to(ROOT)), first_line=lo, last_line=hi,
                            quote='\n'.join(lines[lo-1:hi]), scope='BOUNDED_26_OPERATION_MATRIX_NOT_FULL_RVV_CLOSURE'))
    out = ROOT / 'build/m59/clauses'; out.mkdir(parents=True, exist_ok=True)
    d = dict(status='PASS', counts=dict(count), coverage=coverage, anchors=anchor_rows, clauses=clauses,
             negative_controls={k: 'REJECTED' for k in sorted(negatives)},
             source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [ROOT / 'scripts/m59_clauses.py', ROOT / 'tests/m59_arch.py']},
             artifact_sha256={str(p.relative_to(ROOT)): sha(p) for p in [*inputs, spec]})
    (out / 'results.json').write_text(json.dumps(d, indent=2) + '\n')
    print('PASS M59 clauses', dict(count), flush=True)


if __name__ == '__main__': main()
