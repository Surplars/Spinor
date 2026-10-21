#!/usr/bin/env python3
"""Build and exercise the optional registered top; preserve all legacy artifacts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from m61_build import ROOT,MODELS,emit,gsim,synth


def run(*args):
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)


def one(model):
    gsim(model)
    run('tests/test_m61_isolated.py','--model',model,'--prepare-only')
    # Compiler/simulation and mapping are independent consumers of frozen emit.
    with ThreadPoolExecutor(max_workers=2) as pool:
        test=pool.submit(run,'tests/test_m61_isolated.py','--model',model)
        mapped=pool.submit(synth,model)
        test.result();mapped.result()
    run('scripts/m61_isolation.py','--model',model)
    run('scripts/m61_timing.py','--model',model)


def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');p.add_argument('--models',default=','.join(MODELS));a=p.parse_args()
    if a.check_only:
        from report_m61 import audit
        audit();return
    models=a.models.split(',');assert set(models)<=MODELS.keys()
    if set(models)==MODELS.keys():run('scripts/m61_legacy.py')
    # Mill shares its compilation cache; keep elaboration sequential.
    for model in models:emit(model)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in [pool.submit(one,model) for model in models]:f.result()
    if set(models)==MODELS.keys():run('scripts/report_m61.py')


if __name__=='__main__':main()
