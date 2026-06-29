"""Run the mandatory leakage test suite with a process-level failure code."""
import sys
import unittest


if __name__ == "__main__":
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromName("tests.test_feature_leakage_gate"),
        unittest.defaultTestLoader.loadTestsFromName("tests.test_shadow_monitoring"),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
