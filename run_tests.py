"""
Validation-set runner - Member 4.

Runs every C file in test_cases/ through the full pipeline and compares the
detected vulnerabilities against the ground truth written in each file's
header comment:

    /*
     * EXPECT: DANGEROUS_FUNC 9 HIGH
     */

A file with no EXPECT lines must produce zero findings. The comparison is an
exact set match on (rule_id, line, severity) - a missed detection and a false
positive both fail.

    python run_tests.py              # summary table
    python run_tests.py -v           # also list every finding
    python run_tests.py 04           # only files whose name contains "04"

Exit code is 0 when every file passes, 1 otherwise.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.integration.pipeline import run_pipeline  # noqa: E402


CASES_DIR = os.path.join(ROOT, "test_cases")
EXPECT_RE = re.compile(r"EXPECT:\s*([A-Z_]+)\s+(\d+)\s+(HIGH|MEDIUM|LOW)")


def load_cases(name_filter=None):
    cases = []
    for name in sorted(os.listdir(CASES_DIR)):
        if not name.endswith(".c") or (name_filter and name_filter not in name):
            continue
        with open(os.path.join(CASES_DIR, name), encoding="utf-8") as handle:
            source = handle.read()
        expected = {(rule, int(line), sev) for rule, line, sev in EXPECT_RE.findall(source)}
        cases.append((name, source, expected))
    return cases


def check_case(source, expected):
    """Return (passed, actual, missing, unexpected, error)."""
    report = run_pipeline(source)
    if not report["ok"]:
        return False, set(), expected, set(), report["error"]

    actual = {(f["rule_id"], f["line"], f["severity"]) for f in report["findings"]}
    missing = expected - actual
    unexpected = actual - expected

    error = None
    if report["rule_errors"]:
        error = "; ".join(f"{e['rule_id']}: {e['error']}" for e in report["rule_errors"])

    return not missing and not unexpected and error is None, actual, missing, unexpected, error


def fmt(items):
    return ", ".join(f"{rule}@{line}/{sev}" for rule, line, sev in sorted(items, key=lambda t: (t[1], t[0])))


def main(argv):
    verbose = "-v" in argv
    args = [a for a in argv if not a.startswith("-")]
    cases = load_cases(args[0] if args else None)

    if not cases:
        print("No test cases found.")
        return 1

    passed = 0
    total_expected = 0
    total_detected = 0
    false_positives = 0

    print(f"{'File':<30}{'Result':<8}{'Expected':<10}{'Detected':<10}Notes")
    print("-" * 86)

    for name, source, expected in cases:
        ok, actual, missing, unexpected, error = check_case(source, expected)
        passed += ok
        total_expected += len(expected)
        total_detected += len(expected & actual)
        false_positives += len(unexpected)

        notes = []
        if missing:
            notes.append(f"MISSED {fmt(missing)}")
        if unexpected:
            notes.append(f"EXTRA {fmt(unexpected)}")
        if error:
            notes.append(f"ERROR {error}")

        print(f"{name:<30}{'PASS' if ok else 'FAIL':<8}{len(expected):<10}{len(actual):<10}{' | '.join(notes)}")
        if verbose and actual:
            for item in sorted(actual, key=lambda t: (t[1], t[0])):
                mark = "ok " if item in expected else "?? "
                print(f"    {mark}{item[0]:<22} line {item[1]:<4} {item[2]}")

    print("-" * 86)
    rate = (100.0 * total_detected / total_expected) if total_expected else 100.0
    print(f"{passed}/{len(cases)} files passed  ·  detection {total_detected}/{total_expected} "
          f"({rate:.0f}%)  ·  {false_positives} false positive(s)")

    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
