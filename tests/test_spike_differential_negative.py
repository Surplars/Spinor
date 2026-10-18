#!/usr/bin/env python3
"""Require a deliberate wrong Spike RF expectation to fail the real checker."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'build/spike-differential/SpinorStandard-bounded-rtl'
out=ROOT/'build/spike-negative';out.mkdir(parents=True,exist_ok=True)
receipt=json.loads((source/'results.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key in ['source_sha256','artifact_sha256']:
    for rel,h in receipt[key].items():assert sha(ROOT/rel)==h,rel
inputs=json.loads((source/'inputs.json').read_text())
states=json.loads((source/'expected.json').read_text())
event=next(e for e in inputs if e['kind']=='I' and e['name']=='vadd_vv' and e['instruction']>>25&1 and not states[e['id']]['illegal'])
ident=event['id'];text=(source/'tb.sv').read_text()
start=text.index(f"command({ident},32'h{event['instruction']:x},")
tail=text[start:];pattern=r"ctx_access\(16,0,64'h([0-9a-f]+)\);"
match=re.search(pattern,tail);assert match
expected=int(match[1],16)
assert expected==states[ident]['registers'][8]&((1<<64)-1)
replacement=f"ctx_access(16,0,64'h{expected^1:x});"
mutated=text[:start]+tail[:match.start()]+replacement+tail[match.end():]
assert text!=mutated and len(re.findall(pattern,text))==len(re.findall(pattern,mutated))
tb=out/'tb.sv';tb.write_text(mutated)
files=[tb,ROOT/'build/rtl/SpinorStandard.sv']
bin_dir=ROOT/'tools/oss-cad-suite/bin'
with (out/'compile.log').open('w') as log:
    subprocess.run([bin_dir/'iverilog','-g2012','-s','tb','-DTOP=SpinorStandard','-o',out/'sim',*files],stdout=log,stderr=log,check=True)
run=subprocess.run([bin_dir/'vvp',out/'sim'],capture_output=True,text=True,timeout=120)
output=run.stdout+run.stderr;(out/'run.log').write_text(output)
needle=f'Spike RF mismatch command={ident} chunk=16'
assert run.returncode!=0 and needle in output,output[-1500:]
sources=[Path(__file__).resolve(),ROOT/'tests/spike_differential_tb.sv',ROOT/'tests/test_spike_differential.py']
artifacts=[*files,source/'tb.sv',source/'results.json',source/'inputs.json',source/'expected.json',out/'compile.log',out/'run.log']
result=dict(status='PASS',scope='NEGATIVE_CONTROL_EXPECTED_FAILURE',mutation='XOR_BIT0_EXPECTED_VD8_CHUNK0_AFTER_VADD',command=ident,
            simulation_exit_code=run.returncode,detected_by=needle,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
            artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts})
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS Spike checker rejects deliberately wrong RF expectation',flush=True)
