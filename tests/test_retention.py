#!/usr/bin/env python3
"""Ensure compact indexes cannot be confused with intact original evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from maintenance import retention


class RetentionChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.rel = 'receipt.json'
        self.original = b'{"status":"PASS","source_sha256":{"x":"123"}}\n'
        self.packed = gzip.compress(self.original,mtime=0)
        self.item = dict(kind='compressed-receipt',storage='gzip',bytes=len(self.original),
                         sha256=hashlib.sha256(self.original).hexdigest(),git_blob='0'*40,
                         compressed_path='receipt.json.gz',compressed_sha256=hashlib.sha256(self.packed).hexdigest())
        self.data = dict(schema_version=1,baseline_commit='0'*40,entries={self.rel:self.item})
        (self.root/'receipt.json.gz').write_bytes(self.packed)
        (self.root/self.rel).write_text('{"format":"compact-index"}')
        self.patch_root = patch.object(retention,'ROOT',self.root)
        self.patch_manifest = patch.object(retention,'manifest',return_value=self.data)
        self.patch_root.start();self.patch_manifest.start()
        retention.verify_entry.cache_clear()

    def tearDown(self):
        self.patch_manifest.stop();self.patch_root.stop()
        retention.verify_entry.cache_clear()
        self.directory.cleanup()

    def test_reader_uses_original_not_index(self):
        self.assertEqual(retention.read_receipt(self.rel),json.loads(self.original))
        self.assertTrue(retention.matches_original(self.rel,self.item['sha256']))
        self.assertFalse(retention.matches_original(self.rel,'f'*64))

    def test_corrupt_compressed_copy_is_rejected(self):
        (self.root/'receipt.json.gz').write_bytes(self.packed[:-1]+b'x')
        with self.assertRaises(AssertionError):retention.original_bytes(self.rel)

    def test_changed_original_is_rejected_even_if_compression_hash_matches(self):
        packed = gzip.compress(self.original.replace(b'PASS',b'FAIL'),mtime=0)
        (self.root/'receipt.json.gz').write_bytes(packed)
        self.item['compressed_sha256'] = hashlib.sha256(packed).hexdigest()
        with self.assertRaises(AssertionError):retention.original_bytes(self.rel)

    def test_missing_git_object_has_recovery_guidance(self):
        self.item['storage'] = 'git'
        with patch.object(retention.subprocess,'run') as run:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError,'full clone'):
                retention.original_bytes(self.rel)


if __name__ == '__main__':unittest.main()
