"""
SecureCode - Flask backend (Member 4: GUI + integration).

Run from the repository root:

    python app.py                 # http://127.0.0.1:5000

Endpoints
    GET  /                      the analysis workbench (single page)
    POST /api/analyze           {"source": "<C code>"} -> full pipeline JSON
    GET  /api/health            liveness check used by the header badge
    GET  /api/samples           list of files in test_cases/
    GET  /api/samples/<name>    source of one sample file
"""

import os

from flask import Flask, jsonify, render_template, request, abort

from src.integration.pipeline import run_pipeline


ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(ROOT, "test_cases")

# Large enough for any realistic single-file submission, small enough that a
# pasted binary blob cannot tie up the analyzer.
MAX_SOURCE_BYTES = 200_000

app = Flask(__name__)
# Keep AST fields in declaration order instead of alphabetical.
app.json.sort_keys = False


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/analyze")
def analyze():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source")

    if not isinstance(source, str):
        return jsonify({"ok": False, "error": "Request body must be JSON with a 'source' string."}), 400
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return jsonify({"ok": False, "error": "Source is larger than 200 KB."}), 413

    try:
        report = run_pipeline(source)
    except Exception as exc:  # noqa: BLE001 - surface pipeline crashes to the GUI
        app.logger.exception("pipeline crashed")
        return jsonify({"ok": False, "error": f"Internal pipeline error - {type(exc).__name__}: {exc}"}), 500

    return jsonify(report)


def _sample_files():
    if not os.path.isdir(SAMPLES_DIR):
        return []
    return sorted(f for f in os.listdir(SAMPLES_DIR) if f.endswith(".c"))


@app.get("/api/samples")
def samples():
    return jsonify(_sample_files())


@app.get("/api/samples/<name>")
def sample(name):
    # Only names from the directory listing are served - no path traversal.
    if name not in _sample_files():
        abort(404)
    with open(os.path.join(SAMPLES_DIR, name), encoding="utf-8") as handle:
        return jsonify({"name": name, "source": handle.read()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
