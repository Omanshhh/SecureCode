"""
Fixture-driven validation of the security rule engine.

Each file in tests/fixtures/ seeds specific, known vulnerabilities. EXPECTED
below is the ground truth: the exact set of (rule_id, line, severity) the
engine must produce for each file - no more and no less. Two fixtures are
clean and must produce nothing, which is what makes the false-positive claim
meaningful.
"""

import os

import pytest

from src.rules.engine import RuleEngine, summarize
from src.rules.finding import Severity


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

HIGH, MEDIUM, LOW = Severity.HIGH, Severity.MEDIUM, Severity.LOW


EXPECTED = {
    "clean.c": set(),
    "loops.c": set(),

    "dangerous_functions.c": {
        ("DANGEROUS_FUNC", 7, HIGH),      # gets
        ("DANGEROUS_FUNC", 8, HIGH),      # strcpy
        ("DANGEROUS_FUNC", 9, MEDIUM),    # scanf
        ("DANGEROUS_FUNC", 10, HIGH),     # system
    },

    "hardcoded_credentials.c": {
        ("HARDCODED_CREDENTIAL", 2, HIGH),     # api_key
        ("HARDCODED_CREDENTIAL", 5, HIGH),     # db_password
        ("HARDCODED_CREDENTIAL", 6, MEDIUM),   # session_token
        # hostname is deliberately NOT flagged
    },

    "unreachable_code.c": {
        ("UNREACHABLE_CODE", 13, LOW),
    },

    "uninitialized_variable.c": {
        ("UNINITIALIZED_VAR", 12, HIGH),
    },

    "buffer_overflow.c": {
        ("BUFFER_OVERFLOW", 8, HIGH),     # numbers[5] on int[3]
        ("BUFFER_OVERFLOW", 10, HIGH),    # strcpy of a 36-char literal into char[8]
        ("DANGEROUS_FUNC", 10, HIGH),     # ... which is also an unsafe call
    },

    "null_dereference.c": {
        ("NULL_DEREFERENCE", 14, HIGH),
    },

    "integer_overflow.c": {
        ("INTEGER_OVERFLOW", 3, HIGH),      # 2147483647 + 1
        ("INTEGER_OVERFLOW", 4, MEDIUM),    # char = 300
        ("INTEGER_OVERFLOW", 8, MEDIUM),    # malloc(count * 4)
    },

    "combined.c": {
        ("HARDCODED_CREDENTIAL", 2, HIGH),
        ("DANGEROUS_FUNC", 15, HIGH),
        ("BUFFER_OVERFLOW", 16, HIGH),
        ("DANGEROUS_FUNC", 16, HIGH),
        ("UNINITIALIZED_VAR", 18, HIGH),
        ("NULL_DEREFERENCE", 19, HIGH),
        ("UNREACHABLE_CODE", 23, LOW),
    },
}


def analyze(filename):
    path = os.path.join(FIXTURES, filename)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    result = RuleEngine().analyze_source(source)

    assert result["ok"], f"{filename} failed to parse: {result['error']}"
    assert result["rule_errors"] == [], (
        f"{filename} raised inside a rule: {result['rule_errors']}"
    )
    return result


def actual_set(result):
    return {(f.rule_id, f.line, f.severity) for f in result["findings"]}


@pytest.mark.parametrize("filename", sorted(EXPECTED))
def test_fixture_detections(filename):
    result = analyze(filename)
    assert actual_set(result) == EXPECTED[filename]


@pytest.mark.parametrize("filename", ["clean.c", "loops.c"])
def test_clean_files_have_no_false_positives(filename):
    result = analyze(filename)
    assert result["findings"] == []


def test_every_finding_carries_a_usable_location():
    for filename in EXPECTED:
        result = analyze(filename)
        for finding in result["findings"]:
            assert finding.line > 0, f"{filename}: finding without a line"
            assert finding.message
            assert finding.suggested_fix


def test_findings_are_sorted_by_line():
    result = analyze("combined.c")
    lines = [f.line for f in result["findings"]]
    assert lines == sorted(lines)


def test_report_dict_contract():
    """The GUI depends on these exact keys - Member 4's integration point."""
    result = analyze("combined.c")
    row = result["findings"][0].to_dict()

    assert set(row) == {
        "rule_id", "type", "line", "severity", "message",
        "suggested_fix", "function",
    }


def test_summary_counts():
    result = analyze("combined.c")
    counts = summarize(result["findings"])

    assert counts[HIGH] == 6
    assert counts[LOW] == 1


def test_syntax_error_is_reported_not_raised():
    result = RuleEngine().analyze_source("int x = ;")
    assert result["ok"] is False
    assert "ParserError" in result["error"]


def test_a_broken_rule_does_not_kill_the_report():
    """Rule isolation: one failing rule must not lose the other findings."""
    from src.rules.base import Rule
    from src.rules.dangerous_functions import DangerousFunctionRule

    class ExplodingRule(Rule):
        rule_id = "BOOM"
        name = "Exploding Rule"

        def run(self, ctx):
            raise RuntimeError("deliberate failure")

    engine = RuleEngine(rules=[DangerousFunctionRule, ExplodingRule])
    path = os.path.join(FIXTURES, "dangerous_functions.c")
    result = engine.analyze_source(open(path, encoding="utf-8").read())

    assert len(result["findings"]) == 4
    assert len(result["rule_errors"]) == 1
    assert result["rule_errors"][0]["rule_id"] == "BOOM"


def test_2d_buffer_overflow_detection():
    engine = RuleEngine()

    # Case 1: out-of-bounds on second dimension specifically
    src_overflow = """
    int foo() {
        int grid[3][4];
        grid[1][9] = 1;
        return grid[0][0];
    }
    """
    res_overflow = engine.analyze_source(src_overflow)
    assert res_overflow["ok"] is True
    overflow_findings = [f for f in res_overflow["findings"] if f.rule_id == "BUFFER_OVERFLOW"]
    assert len(overflow_findings) == 1
    assert overflow_findings[0].line == 4
    assert "Second index 9 is out of bounds" in overflow_findings[0].message

    # Case 2: safe in-bounds 2D access
    src_safe = """
    int foo() {
        int grid[3][4];
        grid[1][2] = 1;
        return grid[2][3];
    }
    """
    res_safe = engine.analyze_source(src_safe)
    assert res_safe["ok"] is True
    safe_overflows = [f for f in res_safe["findings"] if f.rule_id == "BUFFER_OVERFLOW"]
    assert len(safe_overflows) == 0
