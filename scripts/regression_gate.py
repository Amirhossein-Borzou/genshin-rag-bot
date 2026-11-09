#!/usr/bin/env python3
"""Phase 8 — deterministic regression gate. NO LLM involved.

Runs the deterministic retrieval eval, then compares the fresh metrics
against the floors in data/regression_gate.json. Exit code:
  0 = PASS (all metrics >= floors, case count intact)
  1 = REGRESSION (a metric fell below its floor — KB build or retrieval
      change made things worse; do NOT ship this rebuild)
  2 = CONFIG ERROR (gate file missing/corrupt, benchmark missing)

The 0.03 tolerance absorbs patch-day noise (new beta characters shift the
chunk population). Tighten/loosen by editing data/regression_gate.json.

Usage:
  venv/bin/python scripts/regression_gate.py            # eval + compare
  venv/bin/python scripts/regression_gate.py --report X # compare saved report
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
GATE = os.path.join(ROOT, "data", "regression_gate.json")
PY = os.path.join(ROOT, "venv", "bin", "python")
EVAL = os.path.join(HERE, "eval_retrieval.py")


def load_gate():
    if not os.path.exists(GATE):
        print(f"CONFIG ERROR: {GATE} missing", file=sys.stderr)
        sys.exit(2)
    try:
        g = json.load(open(GATE))
        assert "floors" in g and "min_cases_scored" in g
        return g
    except Exception as e:
        print(f"CONFIG ERROR: gate file corrupt: {e}", file=sys.stderr)
        sys.exit(2)


def run_fresh_eval():
    """Run eval_retrieval.py, return the path of the report it just wrote."""
    r = subprocess.run([PY, EVAL], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print("EVAL FAILED:\n" + r.stdout[-2000:] + r.stderr[-2000:], file=sys.stderr)
        sys.exit(2)
    # eval writes data/eval_retrieval_<ts>.json — newest one is ours
    import glob
    reports = sorted(glob.glob(os.path.join(ROOT, "data", "eval_retrieval_*.json")))
    return reports[-1]


def compare(report_path, gate):
    rep = json.load(open(report_path))
    floors = gate["floors"]
    failures = []
    rows = []
    for metric, floor in floors.items():
        got = rep.get(metric)
        if got is None:
            failures.append(f"{metric}: MISSING from report")
            continue
        ok = got >= floor
        rows.append((metric, got, floor, ok))
        if not ok:
            failures.append(f"{metric}: {got} < floor {floor}  (baseline {gate['baseline_metrics'].get(metric)})")
    n_got = rep.get("cases_scored", 0)
    n_min = gate["min_cases_scored"]
    if n_got < n_min:
        failures.append(f"cases_scored: {n_got} < minimum {n_min} (benchmark shrank?)")
    return rows, failures


def main():
    gate = load_gate()
    if "--report" in sys.argv:
        path = sys.argv[sys.argv.index("--report") + 1]
    else:
        path = run_fresh_eval()
    print(f"gate report: {path}")
    rows, failures = compare(path, gate)
    print(f"{'metric':24} {'now':>7} {'floor':>7}  verdict")
    for metric, got, floor, ok in rows:
        print(f"{metric:24} {got:7.3f} {floor:7.3f}  {'ok' if ok else 'REGRESSION'}")
    if failures:
        print("\nGATE: FAIL")
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("\nGATE: PASS (no retrieval regression vs baseline)")


if __name__ == "__main__":
    main()
