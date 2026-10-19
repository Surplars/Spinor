"""Check explicit semantic predicates in independent expectations bound to DUT runs."""
import gzip
import json
import re
import sys
from pathlib import Path
from m58_stream import ROOT,sha
sys.path.insert(0,str(ROOT/'tests'))
from test_m58_policies import cases

ELEMENTWISE=('vadd_','vsub_','vrsub_','vand_','vor_','vxor_','vmul_','vmulh_','vmulhu_','vmulhsu_',
             'vdiv_','vdivu_','vrem_','vremu_','vsll_','vsrl_','vsra_','vmin_','vminu_','vmax_','vmaxu_',
             'vsadd_','vsaddu_','vssub_','vssubu_','vaadd_','vaaddu_','vasub_','vasubu_','vssra_','vssrl_',
             'vsmul_','vmacc_','vnmsac_','vmadd_','vnmsub_','vandn_','vbrev','vrev8_','vclz_','vctz_',
             'vrol_','vror_','vfadd_','vfsub_','vfrsub_','vfmul_','vfdiv_','vfrdiv_','vfsqrt_',
             'vfsgnj','vfmin_','vfmax_','vfrec7_','vfrsqrt7_','vfclass_','vfcvt_',
             'vfmacc_','vfnmacc_','vfmsac_','vfnmsac_','vfmadd_','vfnmadd_','vfmsub_','vfnmsub_')


def preservation(c,registers):
    """Project chooses undisturbed for all four allowed policies, even TA/MA."""
    group=1<<c['lmul'] if c['lmul']<4 else 1
    old=b''.join(r.to_bytes(16,'little') for r in c['registers'])
    new=b''.join(r.to_bytes(16,'little') for r in registers)
    lo=8*16;hi=lo+16*group;width=c['sew']//8
    assert new[:lo]==old[:lo] and new[hi:]==old[hi:],'non-destination RF modified'
    tail=inactive=0
    for position in range(0,hi-lo,width):
        index=position//width
        if index>=c['length']:
            assert new[lo+position:lo+position+width]==old[lo+position:lo+position+width],'tail not preserved'
            tail+=1
        elif not c['vm'] and not (c['registers'][0]>>index&1):
            assert new[lo+position:lo+position+width]==old[lo+position:lo+position+width],'inactive element not preserved'
            inactive+=1
    return tail,inactive


def masked_flags(c,flags):
    assert flags==c['initial_flags'],'all-inactive FP generated flags'


def main():
    out=ROOT/'build/m58/clauses';out.mkdir(parents=True,exist_ok=True)
    paths=[];counts=dict(legal_targets=0,tail_elements=0,inactive_elements=0,elementwise_targets=0,all_inactive_fp=0)
    names=set();negative_tail=negative_fp=False
    for policy in range(4):
        folder=ROOT/f'build/m58/policies/p{policy}';ref=json.loads((folder/'results.json').read_text())
        for group in ('source_sha256','artifact_sha256'):
            for rel,h in ref[group].items():assert sha(ROOT/rel)==h,rel
        paths.extend([folder/'results.json',folder/'spike-output.txt.gz'])
        states=gzip.decompress((folder/'spike-output.txt.gz').read_bytes()).decode().splitlines()
        rows=cases(policy);assert len(states)==4*len(rows)
        for i,c in enumerate(rows):
            fields=states[4*i+3].split();assert int(fields[1])==4*i+3
            if int(fields[3]):continue
            counts['legal_targets']+=1
            assert int(fields[6],16)==c['length'] and int(fields[7],16)==c['vtype'] and int(fields[8],16)==0
            regs=[int(r,16) for r in fields[13:]]
            if c['name'].startswith(ELEMENTWISE) or c['name']=='vcpop_v':
                t,m=preservation(c,regs);counts['tail_elements']+=t;counts['inactive_elements']+=m
                counts['elementwise_targets']+=1;names.add(c['name'])
                if t and not negative_tail:
                    bad=list(regs);offset=c['length']*(c['sew']//8);bad[8+offset//16]^=1<<((offset%16)*8)
                    try:preservation(c,bad)
                    except AssertionError as e:assert 'tail not preserved' in str(e);negative_tail=True
                    else:raise AssertionError('tail predicate accepted corruption')
            if (c['raw']>>12&7) in (1,5) and c['name']!='vfmerge_vfm' and c['vm']==0 and c['registers'][0]==0:
                assert c['initial_flags']==0,'initial flags must not hide a newly raised exception'
                masked_flags(c,int(fields[12],16));counts['all_inactive_fp']+=1
                if not negative_fp:
                    try:masked_flags(c,c['initial_flags']^1)
                    except AssertionError as e:assert 'generated flags' in str(e);negative_fp=True
                    else:raise AssertionError('FP mask predicate accepted corruption')
    assert all(counts.values()) and negative_tail and negative_fp
    spec=ROOT/'docs/references/m57-v-spec-maintained.adoc';text=' '.join(spec.read_text().split())
    clauses=[
        dict(id='V-POLICY-4',anchor='sec-agnostic',quote='All systems must support all four options:',evidence='all 330 encodings x 22 vtypes x 4 vta/vma; unsupported geometry rejected'),
        dict(id='V-UNDISTURBED',anchor='sec-agnostic',quote='A simple in-order implementation can ignore the settings and simply execute all vector instructions using the undisturbed policy.',evidence='explicit tail/inactive predicates on listed same-width elementwise operations; full RF differential for all encodings'),
        dict(id='V-MASK-NO-EXCEPTION',quote='Element operations that are masked off (inactive) never generate exceptions.',evidence='all-inactive FP flags unchanged, including sNaN/subnormal data; normal RAM masked-off faults in recovery cases'),
        dict(id='V-SEGMENT-RESTART',anchor='sec-vector-memory',quote='The `vstart` value is in units of whole segments.',evidence='324 stride scenarios; field faults at element0/1, retry from observed segment index'),
        dict(id='V-FOF-VL',anchor='sec-vector-memory',quote='If element 0 raises an exception, `vl` is not modified, and the trap is taken.',evidence='40 element0 traps plus 40 later truncations; following arithmetic and CSR consume actual new VL'),
    ]
    raw=spec.read_text()
    for c in clauses:
        assert c['quote'] in text,c['id']
        matched=re.search(r'\s+'.join(map(re.escape,c['quote'].split())),raw)
        assert matched,c['id']
        c['source_line']=raw.count('\n',0,matched.start())+1
        if 'anchor' in c:assert '[['+c['anchor']+']]' in raw
        c['source']='docs/references/m57-v-spec-maintained.adoc'
        c['status']='BOUNDED_SAMPLES_PASS_NOT_COMPLETE_EXTENSION_COMPLIANCE'
    recovery=json.loads((ROOT/'build/m58/recovery/results.json').read_text());assert recovery['fof_element0_traps']==recovery['fof_later_truncations']==40
    paths.extend([spec,ROOT/'build/m58/recovery/results.json',ROOT/'build/m58/recovery/cases.csv'])
    d=dict(status='PASS',scope='INDEPENDENT_EXPECTATION_PREDICATES_LINKED_TO_FULL_RF_CSR_DUT_DIFFERENTIAL',counts=counts,
           elementwise_encodings=sorted(names),clauses=clauses,negative_controls={'tail-bit-corruption':'REJECTED','all-inactive-FP-flag':'REJECTED'},
           source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'tests/test_m58_policies.py']},
           artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in paths})
    (out/'results.json').write_text(json.dumps(d,indent=2)+'\n');print('PASS semantic clause predicates',counts,flush=True)


if __name__=='__main__':main()
