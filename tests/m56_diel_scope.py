"""Explicit normative scope; absence from Zvkt is not an implementation failure."""
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def rows():
    out=[]
    excluded=['vsadd','vssub','vnclip','vcompress','vdiv','vrem','vaadd','vasub','vmin','vmax','vsmul','vred','vwred','vssra','vssrl']
    masks={'vcpop_m','vfirst_m','vid_v','viota_m','vmsbf_m','vmsif_m','vmsof_m'}
    covered=['vadd','vsub','vrsub','vwadd','vwsub','vadc','vmadc','vmsbc','vsbc','vmseq','vmsne','vmslt','vmsle','vmsgt','vmv_', 'vmv1r','vmv2r','vmv4r','vmv8r',
       'vsext','vzext','vand','vor','vxor','vmand','vmnand','vmor','vmnor','vmxor','vmxnor',
       'vmul','vwmul','vmacc','vmadd','vnmsac','vnmsub','vwmacc','vmerge','vrgather','vsll','vsrl','vsra','vnsrl','vnsra','vslide']
    for r in csv.DictReader((ROOT/'reports/m55/canonical-coverage.csv').open()):
        n=r['name'];family=r['family']
        if family in ['memory','configuration']:scope='EXCLUDED';reason=family
        elif n.startswith(('vfslide1up','vfslide1down')):scope='REQUIRED';reason='explicit scalar-element slide'
        elif n=='vmv_x_s':scope='REVIEW';reason='conservatively measured; copy-list shorthand requires review'
        elif family=='floating':scope='EXCLUDED';reason='floating-point arithmetic/transfer outside explicit slide list'
        elif n in masks or any(n.startswith(p) for p in excluded):scope='EXCLUDED';reason='explicit excluded integer family'
        elif family=='zvbb' or any(n.startswith(p) for p in covered):scope='REQUIRED';reason='explicit covered family'
        else:raise AssertionError(('unclassified normative scope',n))
        controls='gather indices' if n.startswith('vrgather') else 'slide amount' if n.startswith(('vslideup','vslidedown')) else 'none beyond vl/vtype/execution mask/instruction constants'
        out.append(dict(r,scope=scope,reason=reason,exempt_control=controls))
    return out
if __name__=='__main__':
    from collections import Counter
    print(Counter(r['scope'] for r in rows()))
