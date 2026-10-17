#!/usr/bin/env python3
"""Pure offline approved-pair/manifest boundary regressions; no backend/JVM."""
from copy import deepcopy
import unittest
from rc_runtime_identity import (
    ORIGINAL_FINAL_REVISION as OLD, ORIGINAL_FINAL_JAR as JAR,
    F3_REVISION, F3_JAR, approved_pair, manifest_identity, legacy_stage_pair,
)


class IdentityBoundaries(unittest.TestCase):
    def seal(self):return {"source_revision":OLD,"artifacts":{"JAR":{"sha256":JAR}}}
    def test_existing_final_pair_stays_supported(self):
        self.assertEqual(manifest_identity(self.seal(),OLD,JAR)["role"],"candidate")
    def test_baseline_requires_explicit_baseline_role(self):
        with self.assertRaises(ValueError):approved_pair(F3_REVISION,F3_JAR)
        self.assertEqual(approved_pair(F3_REVISION,F3_JAR,allow_baseline=True)["role"],"baseline")
    def test_unknown_or_cross_paired_identity_rejected(self):
        for revision,digest in (("a"*40,"b"*64),(OLD,F3_JAR),(F3_REVISION,JAR)):
            with self.subTest(revision=revision),self.assertRaises(ValueError):approved_pair(revision,digest,allow_baseline=True)
    def test_full_lowercase_identity_required(self):
        for revision,digest in ((OLD[:7],JAR),(OLD,JAR[:12]),(OLD.upper(),JAR),(OLD,JAR.upper()),(None,JAR)):
            with self.subTest(revision=revision),self.assertRaises(ValueError):approved_pair(revision,digest)
    def test_approved_expected_pair_cannot_mask_wrong_manifest(self):
        for wrong in (dict(self.seal(),source_revision=F3_REVISION),dict(self.seal(),artifacts={"JAR":{"sha256":F3_JAR}}),{}):
            with self.subTest(wrong=wrong),self.assertRaises(ValueError):manifest_identity(wrong,OLD,JAR)
    def test_packaging_git_head_does_not_replace_explicit_core_identity(self):
        seal=deepcopy(self.seal());seal["workspace_git_HEAD"]="c"*40
        self.assertEqual(manifest_identity(seal,OLD,JAR)["source_revision"],OLD)
    def test_legacy_cli_defaults_do_not_guess_any_new_candidate(self):
        self.assertEqual(legacy_stage_pair(self.seal()),(OLD,JAR))
        self.assertEqual(legacy_stage_pair({"source_revision":F3_REVISION,"artifacts":{"JAR":{"sha256":F3_JAR}}}),(F3_REVISION,F3_JAR))
        with self.assertRaises(ValueError):legacy_stage_pair({"source_revision":"a"*40,"artifacts":{"JAR":{"sha256":"b"*64}}})
    def test_operator_supplied0113_pair_requires_explicit_matching_manifest(self):
        revision="0113ef30f2269f9ea51e7c15e585792828fd2a51";digest="70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c"
        seal={"source_revision":revision,"artifacts":{"JAR":{"sha256":digest}}}
        self.assertEqual(manifest_identity(seal,revision,digest)["role"],"candidate")
        with self.assertRaises(ValueError):manifest_identity(seal,OLD,JAR)
        with self.assertRaises(ValueError):legacy_stage_pair(seal)


if __name__=="__main__":unittest.main()
