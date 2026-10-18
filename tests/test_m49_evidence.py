#!/usr/bin/env python3
"""Reject execution dependency changes; allow the enumerated delivery edits."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import m49_evidence as policy


class EvidencePolicy(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp',prefix='spinor-m49-policy-')
        self.root=Path(self.tmp.name);self.prior=policy.ROOT;policy.ROOT=self.root
        sources=['src/Vpu.scala','tests/reference.py','scripts/synth.py','README.md','scripts/package.py']
        artifact='build/model.json'
        for name in sources+[artifact]:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original\n')
        receipt=dict(status='FOF_LOADS_ATOMIC_VL_AND_FIXED_CLOUD_REFERENCE_GATE_PASSED',
                     source_sha256={s:policy.sha(self.root/s) for s in sources},
                     artifact_sha256={artifact:policy.sha(self.root/artifact)})
        p=self.root/'reports/m48/receipt.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(receipt))

    def tearDown(self):
        policy.ROOT=self.prior;self.tmp.cleanup()

    def test_exact(self):self.assertEqual(policy.base_evidence()[1]['changed_delivery_only'],[])
    def test_hardware_change(self):self.reject('src/Vpu.scala')
    def test_reference_change(self):self.reject('tests/reference.py')
    def test_mapper_change(self):self.reject('scripts/synth.py')
    def test_netlist_change(self):self.reject('build/model.json')
    def reject(self,name):
        (self.root/name).write_text('changed\n')
        with self.assertRaises(AssertionError):policy.base_evidence()
    def test_missing_artifact(self):
        (self.root/'build/model.json').unlink()
        with self.assertRaises(AssertionError):policy.base_evidence()
    def test_delivery_changes(self):
        for name in ['README.md','scripts/package.py']:(self.root/name).write_text('delivery update\n')
        self.assertEqual(policy.base_evidence()[1]['changed_delivery_only'],['README.md','scripts/package.py'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(EvidencePolicy)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    root=Path(__file__).resolve().parents[1]
    paths=[Path(__file__).resolve(),root/'scripts/m49_evidence.py']
    report=dict(status='PASS' if result.wasSuccessful() else 'FAIL',checks=result.testsRun,
                source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    out=root/'build/m49-policy/results.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
