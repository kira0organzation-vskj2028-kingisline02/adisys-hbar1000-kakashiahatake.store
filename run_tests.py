#!/usr/bin/env python3
"""RiceVision Master Test Suite Runner.
Usage:
    python run_tests.py              # Run all core requirement and unit tests
    python run_tests.py --all        # Run all test suites including browser integration
    python run_tests.py <name>       # Run a specific test (e.g. test_m1_m19_requirements)
"""
import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
TESTS_DIR = os.path.join(ROOT_DIR, "tests")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
if "HMI_AUTH" not in os.environ:
    os.environ["HMI_AUTH"] = "admin:admin123"

CORE_TESTS = [
    "test_tension_and_security.py",
    "test_stn2_calibrate_requirements.py",
    "test_m1_m19_requirements.py",
    "test_turn12_requirements.py",
    "test_hmi_web.py",
    "test_bag_accuracy.py",
    "test_audit_hardening.py",
]

INTEGRATION_TESTS = [
    "test_new_endpoints.py",
    "test_stream_no_flicker.py",
    "test_turn11_specific_fixes.py",
]


def run_suites(files):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for f in files:
        mod_name = os.path.splitext(f)[0]
        try:
            mod = __import__(mod_name)
            suite.addTests(loader.loadTestsFromModule(mod))
        except Exception as e:
            print(f"[FAIL] Could not load {f}: {e}")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    args = sys.argv[1:]
    if not args:
        print("=== Running RiceVision Core Test Suites ===")
        ok = run_suites(CORE_TESTS)
        sys.exit(0 if ok else 1)
    elif "--all" in args:
        print("=== Running All Unit & Integration Test Suites ===")
        ok = run_suites(CORE_TESTS + INTEGRATION_TESTS)
        sys.exit(0 if ok else 1)
    else:
        target = args[0]
        if not target.endswith(".py"):
            target += ".py"
        print(f"=== Running Single Test Suite: {target} ===")
        ok = run_suites([target])
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
