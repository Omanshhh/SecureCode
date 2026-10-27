"""
Integration tests - Member 4.

1. Every file in test_cases/ must produce exactly the findings declared in its
   EXPECT header (same check as run_tests.py, but inside pytest).
2. The Flask API returns every pipeline stage as JSON and reports syntax
   errors instead of crashing.
"""

import json

import pytest

from app import app
from run_tests import load_cases, check_case


CASES = load_cases()


@pytest.mark.parametrize("name,source,expected", CASES, ids=[c[0] for c in CASES])
def test_case_file(name, source, expected):
    ok, actual, missing, unexpected, error = check_case(source, expected)
    assert error is None, error
    assert not missing, f"missed: {sorted(missing)}"
    assert not unexpected, f"false positives: {sorted(unexpected)}"


def test_validation_set_size():
    # A floor, not a ceiling: the corpus must be substantial, and every file
    # in it is already checked individually by test_case_file above, so
    # adding demo programs should not fail the suite.
    assert len(CASES) >= 8


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def post(client, source):
    return client.post("/api/analyze", data=json.dumps({"source": source}),
                       content_type="application/json")


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"SecureCode" in res.data


def test_analyze_returns_every_stage(client):
    source = "int main() {\n    char buffer[8];\n    char input[20];\n\n    strcpy(buffer, input);\n\n    return 0;\n}\n"
    body = post(client, source).get_json()

    assert body["ok"] is True
    assert body["tokens"][0] == {"index": 0, "type": "KEYWORD", "lexeme": "int", "line": 1, "column": 1}
    assert body["tokens"][-1]["type"] == "EOF"
    assert body["ast"]["node"] == "ProgramNode"
    assert "FuncCallNode(name='strcpy', line=5)" in body["ast_text"]
    assert {s["name"]: s["type"] for s in body["symbols"]} == {"buffer": "char[8]", "input": "char[20]"}
    assert body["cfgs"]["main"]["dot"].startswith("digraph CFG {")
    assert [(f["rule_id"], f["line"], f["severity"]) for f in body["findings"]] == [("DANGEROUS_FUNC", 5, "HIGH")]
    assert body["summary"]["counts"] == {"HIGH": 1, "MEDIUM": 0, "LOW": 0}
    assert body["summary"]["risk_score"] == 35


def test_syntax_error_reported_not_raised(client):
    res = post(client, "int main( {")
    body = res.get_json()
    assert res.status_code == 200
    assert body["ok"] is False
    assert "ParserError" in body["error"]


def test_bad_request(client):
    res = client.post("/api/analyze", data="nope", content_type="text/plain")
    assert res.status_code == 400


def test_samples_listing_and_traversal(client):
    names = client.get("/api/samples").get_json()
    assert names == [c[0] for c in CASES]
    assert client.get(f"/api/samples/{names[0]}").get_json()["source"]
    assert client.get("/api/samples/..%2Fapp.py").status_code == 404
