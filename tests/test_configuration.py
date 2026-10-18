#!/usr/bin/env python3
"""CLI rejection and emitted hardware/manifest consistency, not a configuration mock."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/configuration';OUT.mkdir(parents=True,exist_ok=True)
from sys import path
path.insert(0,str(ROOT/'scripts'))
from generate_profiles import PROFILES,PROFILE_ROOT
records=[]
cases=[(['--vlen','256'],'VLEN128/ELEN64'),(['--lanes','2'],'Multiple execution lanes'),(['--alu-stage-bits','64'],'ALU stage bits'),(['--fp','yes'],'--fp must be'),(['--region-base','0xfffffffffffffff8','--region-bytes','16'],'requirement failed'),(['--unknown','1'],'Unknown option'),(['--preset','standard','--preset','deep'],'Duplicate option')]
for index,(opts,error) in enumerate(cases):
 out=OUT/f'reject-{index}';log=OUT/f'reject-{index}.log'
 run=subprocess.run([str(ROOT/'mill'),'Vpu.runMain','vpu.GenerateConfigured','--out',str(out),*opts],cwd=ROOT,capture_output=True,text=True);log.write_text(run.stdout+run.stderr)
 assert run.returncode!=0 and error in run.stdout+run.stderr,(opts,run.stdout+run.stderr)
 assert not list(out.glob('*.sv')),opts
 records.append(dict(options=opts,error=error,exit_code=run.returncode,log=str(log.relative_to(ROOT))))
for preset,top in PROFILES.items():
 cfg=json.loads((ROOT/f'build/rtl/{top}.json').read_text());text=(ROOT/f'build/rtl/{top}.sv').read_text()
 assert cfg['top']==top and cfg['preset']==preset and cfg['alu_stage_bits']==(16 if 'deep' in preset else 32)
 fp='integer' not in preset;assert cfg['fp32_fp64']==fp and cfg['has_fp_csr_ports']==fp
 assert ('io_core_frm' in text)==fp and ('io_core_fflags' in text)==fp
 assert ('module FloatingPointLaneResize(' in text)==fp
 assert 'VersionedRegisterFileRam' in text and 'storage_ext' in text
 local=PROFILE_ROOT/top
 for ext in ['sv','json']:assert (local/f'{top}.{ext}').read_bytes()==(ROOT/f'build/rtl/{top}.{ext}').read_bytes(),(top,ext)
 helper='LishiVpuMemory'+('16' if cfg['alu_stage_bits']==16 else '')
 expected='RamVector'+('Fp' if fp else 'Integer')+'Memory'+('16' if cfg['alu_stage_bits']==16 else '')
 for folder,suffix in [('verification','Verification'),('verification/assert','Verification-Assert')]:
  assert 'layers-'+expected+'-'+suffix+'.sv' in (local/folder/f'layers-{helper}-{suffix}.sv').read_text(),(top,folder)
 assert cfg['vlen']==128 and cfg['lanes']==1 and cfg['instruction_capacity']==1
assert 'layers-RamVectorFpMemory-Verification.sv' in (ROOT/'build/rtl/verification/layers-LishiVpuMemory-Verification.sv').read_text()
assert (ROOT/'build/rtl/SpinorStandard.sv').read_text().replace('SpinorStandard','SpinorVpu')==(ROOT/'build/rtl/SpinorVpu.sv').read_text()
files=[Path(__file__).resolve(),ROOT/'src/main/scala/vpu/SpinorParams.scala',ROOT/'src/main/scala/vpu/GenerateConfigured.scala',ROOT/'scripts/generate_profiles.py']+[ROOT/f'build/rtl/{top}.{ext}' for top in PROFILES.values() for ext in ['sv','json']]+[p for p in PROFILE_ROOT.rglob('*') if p.is_file()]
r=dict(status='PASS',scope='CLI_REJECTION_AND_EMITTED_PRESET_CONSISTENCY',negative_cases=records,presets=list(PROFILES),sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(OUT/'results.json').write_text(json.dumps(r,indent=2)+'\n');print('PASS configuration rejection and four emitted hardware presets')
