#!/usr/bin/env python3
"""Offline regressions for non-atomic frozen-agent export publication."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('rc_probe_readiness_tests_subject',ROOT/'scripts/rc-probe-benchmark.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class Readiness(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rc-probe-readiness-',dir=ROOT/'scratch')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'launches':{'A':{'output':str(self.root)}}}))
        self.window=probe.ProbeWindows(manifest,servers=('A',));self.window.token='offline-token'
        self.path=self.root/'offline-token.start.json'
        self.valid=json.dumps({'token':'offline-token','state':'ACTIVE'}).encode()+b'\n'
    def writer(self,write):
        def later():time.sleep(.04);write()
        thread=threading.Thread(target=later);thread.start();self.addCleanup(thread.join)
    def test_delayed_partial_json_is_read_only_retried(self):
        self.path.write_bytes(b'{"token":"offline-token",\n')
        self.writer(lambda:self.path.write_bytes(self.valid))
        result=self.window.wait_files('.start.json')
        attempts=self.window.commands[-1]['file_reads']
        self.assertTrue(any(a['state']=='NOT_READY' and 'JSONDecodeError' in a['error'] for a in attempts))
        self.assertEqual(result['A']['source']['sha256'],probe.hashlib.sha256(self.valid).hexdigest())
        self.assertTrue(all(a['observer_start']<=a['observer_end'] for a in attempts))
        self.assertFalse(any('command' in c for c in self.window.commands))
    def test_valid_json_without_final_newline_waits_for_completion(self):
        self.path.write_bytes(self.valid[:-1]);self.writer(lambda:self.path.write_bytes(self.valid))
        self.window.wait_files('.start.json')
        self.assertTrue(any('final newline' in a.get('error','') for a in self.window.commands[-1]['file_reads']))
    def assert_deadline(self,raw):
        self.path.write_bytes(raw);clock=[0.0]
        def now():clock[0]+=.1;return clock[0]
        with patch.object(probe.time,'monotonic',side_effect=now),patch.object(probe.time,'sleep',return_value=None):
            with self.assertRaises(TimeoutError):self.window.wait_files('.start.json')
        self.assertFalse(self.window.commands[-1]['completed'])
        self.assertAlmostEqual(self.window.commands[-1]['fixed_deadline']-self.window.commands[-1]['observer_start'],15)
    def test_permanent_invalid_json_fails_original_fixed_deadline(self):self.assert_deadline(b'{broken\n')
    def test_missing_newline_never_qualifies(self):self.assert_deadline(self.valid[:-1])
    def test_wrong_token_or_state_never_qualifies(self):
        for body in ({'token':'foreign','state':'ACTIVE'},{'token':'offline-token','state':'CLOSED'}):
            with self.subTest(body=body):self.assert_deadline(json.dumps(body).encode()+b'\n')
    def test_oversized_file_is_rejected_without_retry(self):
        self.window.MAX_EXPORT_BYTES=16;self.path.write_bytes(b'x'*17)
        with self.assertRaises(AssertionError):self.window.wait_files('.start.json')
        self.assertEqual(self.window.commands[-1]['file_reads'][0]['state'],'REJECTED_OVERSIZED')


if __name__=='__main__':unittest.main()
