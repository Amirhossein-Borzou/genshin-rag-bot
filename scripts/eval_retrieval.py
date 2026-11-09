#!/usr/bin/env python3
"""Deterministic retrieval evaluator (Phase 1.3) — NO LLM involved.
Reads data/benchmark_v2.json, runs the rag retrieval pipeline, computes:
Recall@5/@10, MRR, Evidence Coverage (in final context), Precision@5.
Writes data/eval_retrieval_<ts>.json and prints a report."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
import rag  # noqa: E402

DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
BENCH = os.path.join(DATA, "benchmark_v2.json")


def eval_case(case, k=24):
    """Return metrics for one benchmark case."""
    q = case["question"]
    exp_ids = set(case.get("expected_chunk_ids") or [])
    t0 = time.time()
    ctx, hits = rag.build_context(q)
    retrieve_s = time.time() - t0
    got_ids = [h.get("id") for h in hits if h.get("id")]
    got_set = set(got_ids)

    if not case.get("answerable", True):
        # unanswerable: metric = did retrieval at least not fabricate (no metric here; judge handles answer)
        return {
            "retrieved": got_ids[:k], "recall5": None, "recall10": None, "mrr": None,
            "evidence_coverage": None, "precision5": None, "retrieve_s": round(retrieve_s, 2),
        }

    # rank of first relevant chunk (1-based) for MRR
    mrr = 0.0
    for i, cid in enumerate(got_ids, 1):
        if cid in exp_ids:
            mrr = 1.0 / i
            break
    in5 = [c for c in got_ids[:5] if c in exp_ids]
    in10 = [c for c in got_ids[:10] if c in exp_ids]
    recall5 = len(in5) / len(exp_ids) if exp_ids else None
    recall10 = len(in10) / len(exp_ids) if exp_ids else None
    coverage = 1.0 if exp_ids and exp_ids.issubset(set(got_ids[:k])) else \
        (len(exp_ids & set(got_ids[:k])) / len(exp_ids) if exp_ids else None)
    precision5 = len(in5) / 5 if got_ids else 0.0
    return {
        "retrieved": got_ids[:k],
        "recall5": recall5, "recall10": recall10, "mrr": mrr,
        "evidence_coverage": coverage, "precision5": precision5,
        "retrieve_s": round(retrieve_s, 2),
        "missing_evidence": sorted(exp_ids - set(got_ids[:k])),
    }


def main():
    cases = json.load(open(BENCH))
    results, mets = [], {"recall5": [], "recall10": [], "mrr": [], "coverage": [], "precision5": []}
    for case in cases:
        m = eval_case(case)
        results.append({"id": case["id"], **m})
        if m.get("recall5") is not None:
            mets["recall5"].append(m["recall5"])
            mets["recall10"].append(m["recall10"])
            mets["mrr"].append(m["mrr"])
            mets["coverage"].append(m["evidence_coverage"])
            mets["precision5"].append(m["precision5"])

    n = len(mets["recall5"])
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kb_chunks": 6122,
        "cases_scored": n,
        "avg_recall@5": round(sum(mets["recall5"]) / n, 3),
        "avg_recall@10": round(sum(mets["recall10"]) / n, 3),
        "avg_MRR": round(sum(mets["mrr"]) / n, 3),
        "avg_evidence_coverage": round(sum(mets["coverage"]) / n, 3),
        "avg_precision@5": round(sum(mets["precision5"]) / n, 3),
        "perfect_coverage_cases": sum(1 for c in mets["coverage"] if c == 1.0),
        "cases": results,
    }
    ts = time.strftime("%Y%m%d_%H%M")
    out = os.path.join(DATA, f"eval_retrieval_{ts}.json")
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=1)

    print(f"== Deterministic Retrieval Eval ({n} answerable cases) ==")
    for k in ["avg_recall@5", "avg_recall@10", "avg_MRR", "avg_evidence_coverage", "avg_precision@5"]:
        print(f"  {k}: {report[k]}")
    print(f"  full evidence coverage: {report['perfect_coverage_cases']}/{n}")
    fails = [r for r in results if r.get("evidence_coverage") is not None and r["evidence_coverage"] < 1.0]
    print(f"\nCases with missing evidence ({len(fails)}):")
    for r in fails:
        c = next(c for c in cases if c["id"] == r["id"])
        print(f"  {r['id']}: missing {r['missing_evidence']}")
        print(f"        Q: {c['question'][:70]}")
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
