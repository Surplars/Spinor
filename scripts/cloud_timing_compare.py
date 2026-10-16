#!/usr/bin/env python3
"""Compare fixed-route reference paths with Vivado; never issue timing signoff."""
import argparse,csv,hashlib,json,re,statistics
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def paths(folder):
    result=[]
    for block in re.split(r'(?=Slack \()', (folder/'setup_paths.rpt').read_text())[1:]:
        source=re.search(r'Source:\s+(\S+)',block).group(1)
        end=re.search(r'Destination:\s+(\S+)',block).group(1)
        launch=re.search(r'\(Prop_[^\n]+\)\n\s+([-\d.]+)\s+[-\d.]+\s+[rf]\s+(\S+)',block)
        if launch is None:raise ValueError('Cannot identify launch arc: '+source)
        data=float(re.search(r'Data Path Delay:\s+([\d.]+)ns',block).group(1))
        result.append(dict(source=source,output_pin=launch[2],endpoint=end,
            slack_ns=float(re.search(r'Slack \(\w+\)\s*:\s*([-\d.]+)ns',block).group(1)),
            data_ns=data,launch_arc_ns=float(launch[1]),q_to_d_ns=data-float(launch[1])))
    assert len(result)==20,'Expected the exported top 20 setup paths'
    return result

def verify(folder):
    expected=json.loads((folder/'output-sha256.json').read_text(encoding='utf-8-sig'))
    for n,h in expected.items():
        assert sha(folder/n)==h,'Export hash mismatch: '+n
    return expected

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',required=True,type=Path);p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--prepare',action='store_true');a=p.parse_args()
    verify(a.results);rows=paths(a.results);a.reference.mkdir(parents=True,exist_ok=True)
    queries=a.reference/'queries.tsv'
    if a.prepare:
        queries.write_text(''.join(r['output_pin']+'\t'+r['endpoint']+'\n' for r in rows));return
    probe=json.loads((a.reference/'probe.json').read_text())
    assert probe['status']=='BUILT_REFERENCE_GRAPH'
    for name,h in probe['source_or_artifact_sha256'].items():assert sha(Path(name))==h,name
    # An apparently successful graph from another run must not be compared.
    for name in ['routed.dcp','routed.edf']:
        assert probe['source_or_artifact_sha256'][str((a.results/name).resolve())]==sha(a.results/name)
    matched=list(csv.DictReader((a.reference/'matched-paths.tsv').open(),delimiter='\t'))
    assert len(rows)==len(matched)
    errors=[]
    for row,ref in zip(rows,matched):
        assert (row['output_pin'],row['endpoint'])==(ref['source'],ref['endpoint'])
        row['status']=ref['status']
        if ref['status']=='MATCHED':
            row['reference_q_to_d_ns']=float(ref['reference_ps'])/1000
            row['reference_minus_vivado_ns']=row['reference_q_to_d_ns']-row['q_to_d_ns']
            errors.append(row['reference_minus_vivado_ns'])
    run=dict(line.split('=',1) for line in (a.results/'run-summary.txt').read_text().splitlines() if '=' in line)
    period=float(run['period_ns']);wns=float(run['worst_timed_setup_slack_ns'])
    budgets=[dict(MHz=f,setup_slack_ns=round(wns+1000/f-period,6)) for f in [300,333.333,350,400,500]]
    report=dict(scope='FIXED_ROUTED_DATA_PATH_REFERENCE_NOT_NEW_RTL_SIGNOFF',
        exported_paths=len(rows),matched_paths=len(errors),paths=rows,
        mean_absolute_error_ns=statistics.mean(abs(e) for e in errors) if errors else None,
        worst_underestimate_ns=max([0]+[-e for e in errors]),
        worst_overestimate_ns=max([0]+errors),
        frequency_what_if=budgets,signoff_STA=False,
        limitations=['Only the exported top 20 paths, not full graph error coverage.',
        'Q-to-D comparison excludes Vivado launch clock-to-output arc; model may choose another path between the same pins.',
        'Frequency scan reuses fixed routes, setup checks and clock assumptions; no new implementation, hold or pulse-width qualification.',
        'No complete DSP internal-arc coverage, min-delay or actual clock-tree validation.'],
        evidence_sha256={str(a.results/n):sha(a.results/n) for n in ['setup_paths.rpt','run-summary.txt','routed.dcp','routed.edf']})
    (a.reference/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['paths','evidence_sha256']},indent=2))
if __name__=='__main__':main()
