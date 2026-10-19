#!/usr/bin/env python3
"""Normalize actual exported DSP observations; never substitute incompatible arcs."""
import csv,hashlib,json,math,re
from collections import Counter,defaultdict
from pathlib import Path
from zipfile import ZipFile
from report_m51 import ROOT,check
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    out=ROOT/'reports/dsp-m53';path=out/'input-dsp-delay.zip'
    resume_path=ROOT/'reports/local-m53-resume/receipt.json';resume=json.loads(resume_path.read_text());check(resume)
    with ZipFile(path) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        for n in z.namelist():
            assert n.startswith('dsp_delay/') and '..' not in Path(n).parts and '\\' not in n
            assert n=='dsp_delay/' or (n.count('/')==1 and n.endswith('.txt'))
        raw={Path(n).name:z.read(n) for n in z.namelist() if not n.endswith('/')}
    assert set(raw)==set(resume['DSP_reported_rows_per_file'])
    files={};rows=[];grouped=defaultdict(list)
    for name,body in sorted(raw.items()):
        properties={};arcs=[];seen=set()
        for line in body.decode('utf-8-sig').splitlines():
            line=line.strip()
            if line.startswith('#property '):
                m=re.fullmatch(r'#property (\S+)(?:\s+(.*))?',line);assert m,line
                assert m[1] not in properties;properties[m[1]]=m[2] or ''
            elif line and not line.startswith('#'):
                parts=line.split();assert len(parts) in [3,4],line
                source,destination=parts[:2];values=list(map(float,parts[2:]));assert all(map(math.isfinite,values))
                assert values[0]>=0 and (source,destination) not in seen;seen.add((source,destination))
                if source=='clk':kind='clock_to_output_exported_arrival';assert destination!='clk' and len(parts)==3
                elif destination=='clk':kind='input_to_sequential_endpoint';assert len(parts)==4
                else:kind='input_to_output_combinational';assert len(parts)==3
                arc=dict(source=source,destination=destination,kind=kind,delay_ns=values[0],
                         setup_ns=values[1] if len(values)==2 else None)
                arcs.append(arc);rows.append(dict(file=name,**arc))
        assert len(arcs)==resume['DSP_reported_rows_per_file'][name]
        dsp=next(n for n in resume['DSP_configurations'] if n.replace('/','-')+'.txt'==name)
        for key,value in resume['DSP_configurations'][dsp].items():assert properties[key]==value,(name,key)
        signature=sha(json.dumps(properties,sort_keys=True,separators=(',',':')).encode())
        files[name]=dict(instance=dsp,sha256=sha(body),configuration_id=signature,properties=properties,arcs=arcs)
        grouped[signature].append(name)
    assert len(rows)==611 and len(grouped)==2
    counts=Counter(r['kind'] for r in rows)
    assert counts==dict(clock_to_output_exported_arrival=290,input_to_sequential_endpoint=321)
    # All six partial-product tables are identical at the exporter's 0.01ns
    # precision. Keep each original file/hash but deduplicate the reference.
    configurations={}
    for sig,names in grouped.items():
        reference=files[names[0]]
        assert all(files[n]['arcs']==reference['arcs'] for n in names)
        by_kind={}
        for kind in sorted({r['kind'] for r in reference['arcs']}):
            arcs=[r for r in reference['arcs'] if r['kind']==kind]
            by_kind[kind]=dict(count=len(arcs),delay_ns_range=[min(r['delay_ns'] for r in arcs),max(r['delay_ns'] for r in arcs)])
            setups=[r['setup_ns'] for r in arcs if r['setup_ns'] is not None]
            if setups:by_kind[kind]['setup_ns_range']=[min(setups),max(setups)]
        configurations[sig]=dict(properties=reference['properties'],instances=[files[n]['instance'] for n in names],
                                 filenames=names,arcs=reference['arcs'],ranges=by_kind)
    mapped_path=ROOT/'build/synth/SpinorVpu/mapped.json';mapped=json.loads(mapped_path.read_text());mapped_dsps={}
    def reg_config(c):return {k:int(c['parameters'].get(k,'0'),2) for k in ['AREG','BREG','MREG','PREG']}
    sampled={tuple(int(c['properties'][k]) for k in ['AREG','BREG','MREG','PREG']) for c in configurations.values()}
    for module in mapped['modules'].values():
        for name,cell in module.get('cells',{}).items():
            if cell['type']=='DSP48E2':
                cfg=reg_config(cell);mapped_dsps[name]=dict(registers=cfg,observed_register_configuration=tuple(cfg.values()) in sampled)
    assert len(mapped_dsps)==9 and all(not d['observed_register_configuration'] for d in mapped_dsps.values())
    assert all(d['registers']==dict(AREG=0,BREG=0,MREG=0,PREG=0) for d in mapped_dsps.values())
    reference=dict(scope='OBSERVED_REGISTERED_VIVADO_DSP_EXPORTS_NOT_COMPLETE_CELL_STA',part=resume['part'],
        tool='Vivado 2025.1 build 6140274',units='ns',printed_precision_ns=0.01,
        reported_checkpoint_sha256=resume['reported_checkpoint_sha256'],rtl_sha256=resume['rtl_sha256'],
        exporter_sha256=sha((ROOT/'third_party/rapidwright/dump_all_dsp_delay.tcl').read_bytes()),
        raw_files={n:{k:v for k,v in d.items() if k!='arcs'} for n,d in files.items()},configurations=configurations,
        limitations=['Only active pins and paths found by upstream report_timing -delay_type max.',
                     'No min/hold characterization or complete internal DSP register-to-register coverage.',
                     'clock-to-output exporter returns cumulative arrival at the output pin, not an independently de-embedded cell C-to-Q.',
                     'Input-to-clk fourth column is signed setup, not hold; preserve its sign.',
                     'No input-to-output combinational observations for these PREG=1 instances.',
                     'Clock/configuration/location context and two-decimal export precision limit transferability.',
                     'No separately labelled complete slow/fast corner database.'])
    ref_path=out/'reference.json';ref_path.write_text(json.dumps(reference,indent=2)+'\n')
    csv_path=out/'arcs.csv'
    with csv_path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['file','source','destination','kind','delay_ns','setup_ns'],lineterminator='\n');w.writeheader();w.writerows(rows)
    result=dict(status='PASS',scope='RAW_DSP_IMPORT_AND_CONFIGURATION_COMPATIBILITY_AUDIT',part=resume['part'],
        DSP_instances=7,raw_rows=611,distinct_full_configurations=2,unique_rows_after_configuration_dedup=156,
        arc_kinds=dict(counts),all_raw_properties_match_resume=True,
        Yosys_DSPs=9,Yosys_register_configuration_matches=0,Yosys_DSP_configurations=mapped_dsps,
        cloud_DSP_reference_imported=True,cloud_fixed_budget_changed=False,cloud_full_DSP_calibration_complete=False,
        DSP_arc_completeness_verified=False,SoC_300MHz_signoff=None,passes_500MHz=None,
        source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__).read_bytes())},
        artifact_sha256={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in
                        [path,resume_path,ref_path,csv_path,out/'evaluation.md',mapped_path,ROOT/'third_party/rapidwright/dump_all_dsp_delay.tcl']})
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS raw DSP import: 7 files, 611 rows, 2 configurations; 0/9 Yosys register configurations compatible')
if __name__=='__main__':main()
