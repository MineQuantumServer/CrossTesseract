#!/usr/bin/env python3
"""Offline attribution boundaries for the standalone, archive-portable FE recipe."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("rc_fe_recipe", Path(__file__).with_name("compare-rc-fe.py"))
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class RuntimeAttribution(unittest.TestCase):
    def test_both_closed_candidate_generations_keep_their_exact_pair(self):
        for revision, jar in recipe.REVIEWED_CANDIDATES.items():
            self.assertEqual(recipe.reviewed_runtime("candidate", revision, jar), revision)

    def test_new_and_old_source_and_binary_cannot_be_cross_paired(self):
        first, second = list(recipe.REVIEWED_CANDIDATES)
        for revision, jar in ((first, recipe.REVIEWED_CANDIDATES[second]),
                              (second, recipe.REVIEWED_CANDIDATES[first])):
            with self.assertRaises(ValueError):
                recipe.reviewed_runtime("candidate", revision, jar)

    def test_original_baseline_cannot_be_relabelled_a_candidate(self):
        revision = "f3c59b772dcbd343596174c73093b2fef536f19c"
        jar = "7924ab808667c69aabbbe71c2c92f1294437a7cc8bb19e409c366af1f682553a"
        self.assertEqual(recipe.reviewed_runtime("baseline", revision, jar), revision)
        with self.assertRaises(ValueError):
            recipe.reviewed_runtime("candidate", revision, jar)

    def test_unknown_short_or_unreviewed_attribution_is_rejected(self):
        revision, jar = next(iter(recipe.REVIEWED_CANDIDATES.items()))
        for role, source, binary in (("candidate", revision[:7], jar), ("candidate", "f" * 40, jar),
                                      ("candidate", revision, "f" * 64), ("unknown", revision, jar)):
            with self.assertRaises(ValueError):
                recipe.reviewed_runtime(role, source, binary)


if __name__ == "__main__":
    unittest.main()
