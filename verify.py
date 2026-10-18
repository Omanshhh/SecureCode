"""
One-command health check for the whole project.

    python verify.py

Runs, in order, and prints a PASS/FAIL checklist:

  1. pytest              - unit tests for every module + Flask API tests
  2. validation set      - test_cases/*.c, expected vs actual findings
  3. live server         - boots app.py on a free port and calls the real
                           HTTP endpoints (page, health, analyze, samples)

Exit code 0 only when every check passes, so CI and scripts can rely on it.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

SAMPLE = (
    "int main() {\n    char buffer[8];\n    char input[20];\n\n"
    "    strcpy(buffer, input);\n\n    return 0;\n}\n"
)


def run(cmd):
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def last_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def check_server():
    """Start app.py, hit every endpoint, always stop the server."""
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PORT=str(port))
    server = subprocess.Popen([PY, "app.py"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        for _ in range(50):
            try:
                http(f"{base}/api/health")
                break
            except OSError:
                time.sleep(0.2)
        else:
            return [("server starts", False, "no response on /api/health after 10s")]

        status, body = http(f"{base}/")
        results.append(("GET /  (workbench page)", status == 200 and b"SecureCode" in body, f"HTTP {status}"))

        status, body = http(f"{base}/api/health")
        results.append(("GET /api/health", json.loads(body) == {"status": "ok"}, body.decode().strip()))

        status, body = http(f"{base}/api/analyze", {"source": SAMPLE})
        report = json.loads(body)
        stages = all(report.get(k) for k in ("tokens", "ast", "symbols", "cfgs", "findings"))
        found = [(f["rule_id"], f["line"]) for f in report.get("findings", [])]
        results.append(("POST /api/analyze  (all stages)", report.get("ok") and stages and found == [("DANGEROUS_FUNC", 5)],
                        f"{len(report.get('tokens', []))} tokens, findings {found}"))

        status, body = http(f"{base}/api/analyze", {"source": "int main( {"})
        report = json.loads(body)
        results.append(("POST /api/analyze  (syntax error)", report.get("ok") is False and "ParserError" in (report.get("error") or ""),
                        report.get("error") or ""))

        status, body = http(f"{base}/api/samples")
        names = json.loads(body)
        results.append(("GET /api/samples", len(names) >= 8, f"{len(names)} sample files"))
    except Exception as exc:  # noqa: BLE001 - report, don't crash the checklist
        results.append(("server requests", False, f"{type(exc).__name__}: {exc}"))
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    return results


def main():
    checks = []

    ok, out = run([PY, "-m", "pytest", "-p", "no:cacheprovider"])
    checks.append(("pytest  (unit + API tests)", ok, last_line(out)))

    ok, out = run([PY, "run_tests.py"])
    checks.append(("validation set  (test_cases/)", ok, last_line(out)))
    if not ok:
        print(out)

    checks.extend(check_server())

    width = max(len(name) for name, _, _ in checks) + 2
    print()
    print("SecureCode verification")
    print("-" * 78)
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}{detail}")
    print("-" * 78)

    failed = sum(1 for _, ok, _ in checks if not ok)
    if failed:
        print(f"  {failed} check(s) FAILED")
        return 1
    print(f"  All {len(checks)} checks passed - everything is working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
