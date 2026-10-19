#!/usr/bin/env python3
"""All-encoding restart test with explicitly bounded reference transformations.

Spike itself still runs at vstart=0. A prefix execution mask is equivalent only
for the classified ordinary maskable instructions. It is never applied to v0
data operands, reductions, whole moves or scalar transfers.
"""
import argparse
from collections import Counter
import gzip
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from m58_stream import ROOT, sha, run_fixture
from m57_isa_catalog import catalog
from m59_arch import Model, DESCRIPTORS

OUT = ROOT / 'build/m60'
M64 = (1 << 64) - 1
M128 = (1 << 128) - 1
REJECT = {
    'vredsum_vs', 'vredand_vs', 'vredor_vs', 'vredxor_vs', 'vredminu_vs', 'vredmin_vs', 'vredmaxu_vs', 'vredmax_vs',
    'vwredsumu_vs', 'vwredsum_vs', 'vfredusum_vs', 'vfredosum_vs', 'vfredmin_vs', 'vfredmax_vs',
    'vfwredusum_vs', 'vfwredosum_vs', 'vcpop_m', 'vfirst_m', 'vmsbf_m', 'vmsof_m', 'vmsif_m', 'viota_m', 'vcompress_vm',
}
SCALAR_READ = {'vmv_x_s', 'vfmv_f_s'}
SCALAR_WRITE = {'vmv_s_x', 'vfmv_s_f'}
WHOLE = {'vmv1r_v': 1, 'vmv2r_v': 2, 'vmv4r_v': 4, 'vmv8r_v': 8}
MASK_LOGIC = {'vmandn_mm', 'vmand_mm', 'vmor_mm', 'vmxor_mm', 'vmorn_mm', 'vmnand_mm', 'vmnor_mm', 'vmxnor_mm'}
V0_DATA = {
    'vadc_vvm', 'vadc_vxm', 'vadc_vim', 'vsbc_vvm', 'vsbc_vxm',
    'vmadc_vvm', 'vmadc_vxm', 'vmadc_vim', 'vmadc_vv', 'vmadc_vx', 'vmadc_vi',
    'vmsbc_vvm', 'vmsbc_vxm', 'vmsbc_vv', 'vmsbc_vx',
    'vmerge_vvm', 'vmerge_vxm', 'vmerge_vim', 'vfmerge_vfm',
    'vmv_v_v', 'vmv_v_x', 'vmv_v_i', 'vfmv_v_f',
}


def strategy(e):
    name = e['name']
    if name in REJECT: return 'nonzero-reject'
    if name in SCALAR_READ: return 'scalar-read-exception'
    if name in SCALAR_WRITE: return 'scalar-write-exception'
    if name in WHOLE: return 'whole-evl'
    if name in MASK_LOGIC or name in V0_DATA: return 'flagless-prefix'
    assert not e['mask'] & (1 << 25), ('unclassified fixed-vm encoding', name)
    return 'execution-mask'


ENTRIES = [e for e in catalog() if e['match'] & 127 == 0x57 and e['match'] >> 12 & 7 != 7]
assert len(ENTRIES) == 330
assert set().union(REJECT, SCALAR_READ, SCALAR_WRITE, WHOLE, MASK_LOGIC, V0_DATA) <= {e['name'] for e in ENTRIES}


def cases(sew):
    s = (sew // 8).bit_length() - 1
    pool = {8: [0, 1, 127, 128, 255, 33], 16: [0, 1, 0x7fff, 0x8000, 0xffff, 0x3c01],
            32: [0, 1, 0x3f800001, 0x80000000, 0x7f800001, 0x7f7fffff, 0xffffffff],
            64: [0, 1, 0x3ff0000000000001, 0x8000000000000000, 0x7ff0000000000001, 0x7fefffffffffffff, M64]}[sew]
    for m in (0, 1, 2, 3, 5, 6, 7):
        if m >= 4 and s > m - 5: continue
        maximum = ((16 >> s) << m) if m < 4 else (16 >> s) >> (8-m)
        for ordinal, e in enumerate(ENTRIES):
            kind = strategy(e); name = e['name']
            for layout in range(2):
                # Broad new overlap samples are same-width and mask-result
                # operations. M59 separately covers wide/narrow typed overlaps.
                special_group = name.startswith(('vw', 'vfw', 'vfn', 'vnsrl', 'vnsra', 'vnclip', 'vsext', 'vzext', 'vrgather', 'vslideup', 'vfslide1up', 'vslide1up'))
                vd = 16 if layout and (kind == 'whole-evl' or kind == 'execution-mask' and not special_group) else 8
                vs2 = 16; vs1 = 24
                for profile, (start, vm, vl) in enumerate([(0, 1, maximum), (1, 1, maximum), (2, 0, maximum), (127, 0, maximum), (1, 0, 0)]):
                    regs = [sum(pool[(r+k+ordinal+layout+profile) % len(pool)] << (sew*k) for k in range(128 // sew)) for r in range(32)]
                    regs[0] = 0 if profile == 3 else int('a596'*8, 16)
                    form = e['match'] >> 12 & 7
                    operand = 1 if form in (4, 5, 6) else (31 if profile % 2 else 1) if form == 3 else vs1
                    fields = vm << 25 | vs2 << 20 | operand << 15 | vd << 7
                    if name == 'vror_vi' and profile % 2: fields |= 1 << 26
                    raw = e['match'] | fields & ~e['mask']
                    scalar = [M64, 1, 1 << 63, 127, 33][profile]
                    if form == 5:
                        scalar = ([0xffffffff7f800001, 0xffffffff3f800001, 0x123456783f800000, 0xffffffff80000000, 0xffffffff00000001] if sew == 32 else
                                  [0x7ff0000000000001, 0x3ff0000000000001, 0x8000000000000000, 0xbff0000000000000, 1])[profile]
                    yield dict(name=name, raw=raw, strategy=kind, sew=sew, lmul=m, vd=vd, vs2=vs2, vs1=operand,
                               profile=profile, layout=layout, start=start, vm=raw >> 25 & 1, vl=vl, maximum=maximum,
                               vtype=s << 3 | m | (profile % 4) << 6, scalar=scalar, frm=(ordinal+profile) % 5,
                               flags=0 if profile in (1, 2) else 0x11, vcsr=(ordinal % 4) << 1 | (profile == 0), registers=regs)


def restore_prefix(old, new, base, bits):
    a = sum(x << (128*r) for r, x in enumerate(old))
    b = sum(x << (128*r) for r, x in enumerate(new))
    mask = ((1 << bits) - 1) << (128*base)
    b = (b & ~mask) | (a & mask)
    return [(b >> (128*r)) & M128 for r in range(32)]


def expected(c, fields):
    illegal = int(fields[2]); cause = int(fields[3])
    assert cause in (0, 2) and illegal == bool(cause)
    result = dict(registers=[int(x, 16) for x in fields[13:]], illegal=illegal,
                  value=int(fields[4], 16), writes=int(fields[5], 16), flags=int(fields[12], 16), sat=int(fields[10], 16), start=0)
    if c['strategy'] == 'execution-mask': result['registers'][0] = c['registers'][0]
    if illegal or c['strategy'] == 'nonzero-reject' and c['start']:
        return dict(registers=c['registers'], illegal=1, value=0, writes=0, flags=c['flags'], sat=c['vcsr'] & 1, start=c['start'])
    kind = c['strategy']
    if kind in ('flagless-prefix', 'whole-evl', 'scalar-read-exception', 'scalar-write-exception'):
        assert result['flags'] == c['flags'] and result['sat'] == c['vcsr'] & 1, 'flagless reference generated flags'
    if kind == 'whole-evl':
        count = WHOLE[c['name']]
        old = c['registers']; direct = list(old)
        for offset in range(count): direct[c['vd']+offset] = old[c['vs2']+offset]
        assert direct == result['registers'], 'whole-move Python baseline differs from Spike'
        result['registers'] = restore_prefix(old, direct, c['vd'], min(c['start']*c['sew'], 128*count))
    elif kind == 'scalar-write-exception':
        # The scalar-insert definition explicitly writes element zero whenever
        # vstart < vl; it is not an ordinary prestart-preserving element loop.
        if c['start'] >= c['vl']: result['registers'] = c['registers']
    elif kind == 'flagless-prefix':
        width = 1 if c['name'] in MASK_LOGIC or c['name'].startswith(('vmadc_', 'vmsbc_')) else c['sew']
        # Restore only the destination group: vstart can exceed VLMAX.
        count = 1 if width == 1 else (1 << c['lmul'] if c['lmul'] < 4 else 1)
        result['registers'] = restore_prefix(c['registers'], result['registers'], c['vd'], min(c['start']*width, 128*count))
    return result


def sources():
    return [Path(__file__).resolve(), ROOT/'tests/m57_isa_catalog.py', ROOT/'tests/m59_arch.py',
            ROOT/'tests/reference_fp.py', ROOT/'tests/reference_fp_resize_m54.py',
            ROOT/'tests/fp_reference.c', ROOT/'tests/fp_resize_reference_m54.c']


def prepare(sew):
    folder = OUT/'corpus'/f'sew{sew}'; folder.mkdir(parents=True, exist_ok=True)
    rows = list(cases(sew)); lines = []
    for c in rows:
        lines.append('Z')
        regs = list(c['registers'])
        if c['strategy'] == 'execution-mask':
            # v0 is exclusively the execution predicate in this class. Prefix
            # bits are cleared; the original v0 is restored in the expectation.
            regs[0] = (M128 if c['vm'] else regs[0]) & (M128 ^ ((1 << c['start'])-1))
        lines.extend(f'R {r} {v:032x}' for r, v in enumerate(regs))
        reference_raw = c['raw'] & ~(1 << 25) if c['strategy'] == 'execution-mask' else c['raw']
        lines.extend([f'I {c["vtype"]<<20|1<<15|7<<12|3<<7|0x57:x} 0 0 {c["vl"]:x}',
                      f'I {15<<20|1<<15|1<<12|3<<7|0x73:x} {c["vcsr"]:x} 0 0',
                      f'I {3<<20|1<<15|1<<12|3<<7|0x73:x} {(c["frm"]<<5)|c["flags"]:x} 0 0',
                      f'I {reference_raw:x} {c["scalar"]:x} 0 0'])
    lock = ROOT/'build/m55/reference/results.json'; ref = json.loads(lock.read_text())
    assert sha(ROOT/ref['binary']) == ref['binary_sha256']
    transport = '\n'.join(lines)+'\n'
    p = subprocess.run([ROOT/ref['binary']], input=transport, text=True, capture_output=True, cwd=ROOT, check=True, timeout=180)
    (folder/'spike-input.txt.gz').write_bytes(gzip.compress(transport.encode(), mtime=0))
    (folder/'spike-output.txt.gz').write_bytes(gzip.compress(p.stdout.encode(), mtime=0))
    (folder/'spike-stderr.log').write_text(p.stderr)
    states = p.stdout.splitlines(); assert len(states) == 4*len(rows)
    stats = Counter(); covered = {}; records = []; ident = 0; start = vxrm = sat = frm = flags = 0
    math_model = Model()
    vl = 0; typ = 1 << 63; regs = [0]*32
    def emit(out, raw, scalar=0, avl=0, bad=0, writes=0, value=0):
        nonlocal ident
        values = [ident, raw, scalar, 0, avl, bad, 2 if bad else 0, 0, writes, value, vl, typ, start, vxrm, sat, frm, flags]
        words = [r >> (64*k) & M64 for r in regs for k in range(2)]
        out.write('E '+' '.join(f'{x:x}' for x in words)+'\nI '+' '.join(f'{x:x}' for x in values)+' @ -\n'); ident += 1
    with gzip.open(folder/'stimulus.txt.gz', 'wt') as out:
        for i, c in enumerate(rows):
            regs = c['registers']; out.writelines(f'R {r} {v:032x}\n' for r, v in enumerate(regs))
            vl = c['vl']; typ = c['vtype']; start = 0
            emit(out, typ << 20 | 1 << 15 | 7 << 12 | 3 << 7 | 0x57, avl=vl, writes=1, value=vl)
            old = vxrm << 1 | sat; vxrm = c['vcsr'] >> 1; sat = c['vcsr'] & 1
            emit(out, 15 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=c['vcsr'], writes=1, value=old)
            old = frm << 5 | flags; frm = c['frm']; flags = c['flags']
            emit(out, 3 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=frm << 5 | flags, writes=1, value=old)
            start = c['start']; emit(out, 8 << 20 | 1 << 15 | 1 << 12 | 3 << 7 | 0x73, scalar=start, writes=1)
            f = states[4*i+3].split(); assert len(f) == 45 and int(f[1]) == 4*i+3
            r = expected(c, f); regs = r['registers']; start = r['start']; flags = r['flags']; sat = r['sat']
            if c['name'] in DESCRIPTORS:
                independent = math_model.execute(c)
                assert (regs, r['illegal'], start, flags, sat) == (independent['registers'], independent['illegal'], independent['vstart'], independent['fflags'], independent['vxsat']), ('mask-transform calibration', c['name'], c['sew'], c['lmul'], c['layout'], c['profile'])
                stats['math_calibration_targets'] += 1
            emit(out, c['raw'], scalar=c['scalar'], bad=r['illegal'], writes=r['writes'], value=r['value'])
            counts = covered.setdefault(c['name'], Counter())
            counts['rejected' if r['illegal'] else 'legal'] += 1
            stats['cases'] += 1; stats['rejected' if r['illegal'] else 'legal'] += 1
            if not r['illegal'] and c['start']:
                counts['nonzero_legal'] += 1; stats['nonzero_legal'] += 1
                if regs != c['registers'] or r['writes']:
                    counts['nonzero_visible_effect'] += 1; stats['nonzero_visible_effect'] += 1
            stats['flags_changed'] += not r['illegal'] and flags != c['flags']
            stats['sat_changed'] += not r['illegal'] and sat != c['vcsr'] & 1
            records.append({**{k: c[k] for k in ('name', 'strategy', 'sew', 'lmul', 'vd', 'vs2', 'layout', 'profile', 'start', 'vl', 'vm')}, 'illegal':r['illegal']})
    (folder/'cases.json.gz').write_bytes(gzip.compress(json.dumps(records, separators=(',', ':')).encode(), mtime=0))
    d = dict(status='PASS', sew=sew, commands=ident, stats=dict(stats), coverage=covered,
             oracle='CLASSIFIED_REFERENCE_TRANSFORMATIONS_SPIKE_ALWAYS_VSTART_ZERO', semantics_modified=False,
             oracle_binary=ref['binary'], oracle_binary_sha256=ref['binary_sha256'],
             source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources()},
             artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in [lock, *sorted(folder.glob('spike-*')), folder/'stimulus.txt.gz', folder/'cases.json.gz', ROOT/'tools/fp/libfp-reference.so', ROOT/'build/m54/reference/libresize.so']})
    (folder/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS M60 corpus', sew, ident, dict(stats), flush=True)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--sew', type=int, choices=[8, 16, 32, 64], required=True)
    p.add_argument('--prepare-only', action='store_true'); p.add_argument('--top', choices=['SpinorStandard', 'SpinorDeep'], default='SpinorStandard'); a = p.parse_args()
    if a.prepare_only: prepare(a.sew); return
    folder = OUT/'corpus'/f'sew{a.sew}'; corpus = folder/'results.json'; ref = json.loads(corpus.read_text())
    for group in ('source_sha256', 'artifact_sha256'):
        for rel, h in ref[group].items(): assert sha(ROOT/rel) == h, rel
    out = OUT/'runs'/f'sew{a.sew}'/a.top
    summary, negatives, artifacts = run_fixture(a.top, out, folder/'stimulus.txt.gz')
    assert f'commands={ref["commands"]} ' in summary
    artifacts[str(corpus.relative_to(ROOT))] = sha(corpus)
    d = dict(status='PASS', top=a.top, sew=a.sew, commands=ref['commands'], summary=summary, trace_replay=False,
             checked_registers_per_command=32, negative_controls=negatives,
             source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [*sources(), ROOT/'scripts/m58_stream.py', ROOT/'tests/m58_stream_driver.cc']}, artifact_sha256=artifacts)
    (out/'results.json').write_text(json.dumps(d, indent=2)+'\n')
    print('PASS M60 restart', a.top, a.sew, ref['commands'], flush=True)


if __name__ == '__main__': main()
