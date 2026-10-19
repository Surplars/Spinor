"""Independently check prestart, special scalar/whole-move rules and rejection."""
from collections import Counter
import gzip
import json
import sys
from m60_evidence import ROOT, sha, check
sys.path.insert(0, str(ROOT/'tests'))
from test_m60_restart import ENTRIES, cases, strategy, WHOLE, SCALAR_READ, SCALAR_WRITE, MASK_LOGIC


def predicate(c, r):
    old = sum(x << (128*k) for k,x in enumerate(c['registers']))
    new = sum(x << (128*k) for k,x in enumerate(r['registers']))
    if r['illegal']:
        assert old == new, 'rejected RF changed'
        assert r['start'] == c['start'], 'rejected vstart changed'
        assert r['flags'] == c['flags'] and r['sat'] == c['vcsr'] & 1, 'rejected flags changed'
        return Counter(rejected_preserved=1)
    assert r['start'] == 0, 'success vstart not cleared'
    count = Counter()
    kind = c['strategy']; base = c['vd'] * 128
    if kind == 'scalar-read-exception':
        width = c['sew']; value = c['registers'][c['vs2']] & ((1 << width)-1)
        if width < 64 and c['name'] == 'vmv_x_s' and value >> (width-1): value |= ((1 << 64)-1) ^ ((1 << width)-1)
        if width == 32 and c['name'] == 'vfmv_f_s': value |= 0xffffffff00000000
        assert r['writes'] == 1 and r['value'] == value, 'scalar read exception lost result'
        assert old == new, 'scalar read RF changed'
        if c['vl'] == 0: count['scalar_read_vl0'] += 1
    elif kind == 'scalar-write-exception':
        value = c['scalar'] & ((1 << c['sew'])-1)
        if c['name'] == 'vfmv_s_f' and c['sew'] == 32 and c['scalar'] >> 32 != 0xffffffff: value = 0x7fc00000
        bits = ((1 << c['sew'])-1) << base
        if c['start'] < c['vl']:
            assert new == (old & ~bits) | (value << base), 'scalar insert exception lost element zero'
            if c['start']: count['scalar_insert_nonzero'] += 1
        else: assert old == new, 'scalar insert no-op changed RF'
    elif kind == 'whole-evl':
        extent = 128 * WHOLE[c['name']]; first = min(c['start']*c['sew'], extent)
        span = ((1 << extent)-1) << base
        active = (((1 << extent)-1) ^ ((1 << first)-1)) << base
        source = sum(c['registers'][c['vs2']+i] << (128*i) for i in range(WHOLE[c['name']])) << base
        assert new == (old & ~active) | (source & active), 'whole EVL copy mismatch'
        assert (old ^ new) & ~span == 0, 'whole non-destination changed'
        if c['vl'] == 0 and old != new: count['whole_vl0_visible_effect'] += 1
    elif kind in ('execution-mask', 'flagless-prefix'):
        mask_result = c['name'].startswith(('vmseq_', 'vmsne_', 'vmslt', 'vmsle', 'vmsgt', 'vmf', 'vmadc_', 'vmsbc_')) or c['name'] in MASK_LOGIC
        width = 1 if mask_result else c['sew'] * (2 if c['name'].startswith(('vw', 'vfw')) else 1)
        count_regs = 1 if mask_result else max(1, (1 << c['lmul']) * (width // c['sew'])) if c['lmul'] < 4 else 1
        extent = count_regs*128
        bits = min(c['start']*width, extent)
        protected = ((1 << bits)-1) << base
        assert (old ^ new) & protected == 0, 'prestart changed'
        count['prestart_elements'] += bits // width
        if c['start'] >= c['vl']: assert old == new, 'ordinary no-op changed RF'
    return count


def main():
    count = Counter(); coverage = {}; artifacts = {}; negatives = set()
    for sew in (8, 16, 32, 64):
        folder = ROOT/f'build/m60/corpus/sew{sew}'
        manifest = folder/'results.json'; d = json.loads(manifest.read_text()); check(d)
        artifacts[str(manifest.relative_to(ROOT))] = sha(manifest)
        for name, values in d['coverage'].items(): coverage.setdefault(name, Counter()).update(values)
        with gzip.open(folder/'stimulus.txt.gz', 'rt') as stream:
            for c in cases(sew):
                for _ in range(32): assert next(stream).startswith('R ')
                for _ in range(5):
                    words = next(stream).split(); command = next(stream).split()
                regs = [int(words[1+2*r], 16) | int(words[2+2*r], 16) << 64 for r in range(32)]
                r = dict(registers=regs, illegal=int(command[6], 16), start=int(command[13], 16),
                         flags=int(command[17], 16), sat=int(command[15], 16), writes=int(command[9], 16), value=int(command[10], 16))
                count.update(predicate(c,r)); count['cases'] += 1
                mode = None; bad = None
                if r['illegal'] and c['start'] and 'reject-start' not in negatives:
                    mode = 'reject-start'; bad = dict(r, start=0)
                elif c['strategy'] == 'scalar-read-exception' and c['vl'] == 0 and not r['illegal'] and 'scalar-read-vl0' not in negatives:
                    mode = 'scalar-read-vl0'; bad = dict(r, writes=0)
                elif c['strategy'] == 'scalar-write-exception' and c['start'] and regs != c['registers'] and 'scalar-insert' not in negatives:
                    mode = 'scalar-insert'; bad = dict(r, registers=c['registers'])
                elif c['strategy'] == 'whole-evl' and c['vl'] == 0 and regs != c['registers'] and 'whole-vl0' not in negatives:
                    mode = 'whole-vl0'; bad = dict(r, registers=c['registers'])
                elif c['strategy'] == 'execution-mask' and c['start'] and not r['illegal'] and 'prestart' not in negatives:
                    mode = 'prestart'; broken = list(regs); broken[c['vd']] ^= 1; bad = dict(r, registers=broken)
                if bad:
                    try: predicate(c,bad)
                    except AssertionError: negatives.add(mode)
                    else: raise AssertionError(('predicate accepted negative control', mode))
            assert not stream.read()
    assert len(coverage) == 330 and all(v['legal'] > 0 for v in coverage.values())
    assert sum(v['nonzero_visible_effect'] > 0 for v in coverage.values()) == 307
    assert negatives == {'reject-start', 'scalar-read-vl0', 'scalar-insert', 'whole-vl0', 'prestart'}
    spec = ROOT/'docs/references/m57-v-spec-maintained.adoc'; lines = spec.read_text().splitlines()
    clauses = []
    for ident, lo, hi in [('integer-scalar-exceptions', 4476, 4496), ('fp-scalar-exceptions', 4507, 4521), ('whole-evl', 4840, 4856)]:
        clauses.append(dict(id=ident, first_line=lo, last_line=hi, quote='\n'.join(lines[lo-1:hi]), source=str(spec.relative_to(ROOT)), scope='BOUNDED_CURRENT_MATRIX'))
    classification = [dict(name=e['name'], strategy=strategy(e), **coverage[e['name']]) for e in ENTRIES]
    out = ROOT/'build/m60/clauses'; out.mkdir(parents=True, exist_ok=True)
    result = dict(status='PASS', counts=dict(count), classification=classification, clauses=clauses,
                  negative_controls={name:'REJECTED' for name in sorted(negatives)},
                  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'scripts/m60_clauses.py', ROOT/'tests/test_m60_restart.py']},
                  artifact_sha256={**artifacts, str(spec.relative_to(ROOT)):sha(spec)})
    (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS M60 clauses', dict(count), flush=True)


if __name__ == '__main__': main()
