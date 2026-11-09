#!/usr/bin/env python3
"""Phase 7 — pipeline diagnostics: why did the bot retrieve/answer this way?

Zero-token, deterministic: replays every pipeline stage for one question and
prints what each stage did — normalization, glossary hits, intent, FTS terms,
per-chunk provenance, hop decisions, answerability verdict.

Usage:
  venv/bin/python scripts/diagnose.py "why does Hu Tao want EM?"
  venv/bin/python scripts/diagnose.py            # interactive-ish demo set

Nothing here calls the LLM; answers are not generated, only the retrieval
story. For answer-quality you still need the (expensive) LLM judge.
"""
import json
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
import rag  # noqa: E402

DB = rag.DB


def fmt_chunk(h, mark_ids=None, width=72):
    mark = " <-EXPECTED" if mark_ids and h.get("id") in mark_ids else ""
    body_prev = re.sub(r"\s+", " ", h["body"])[:60]
    return f"    {h['id']}  [{h['kind']}]  {body_prev}...{mark}"


def diagnose(question, show_body=False):
    print("=" * 78)
    print(f"QUESTION: {question}")
    print("=" * 78)

    # ---- stage 1: normalization + glossary ----
    glossary_hits = rag._matched_glossary(question)
    norm = rag.normalize_query(question)
    print("\n[1] NORMALIZATION")
    print(f"    glossary hits : {glossary_hits or 'none'}")
    print(f"    normalized    : {norm!r}")

    # ---- stage 2: intent ----
    intent = rag.detect_intent(norm)
    entity_names = sorted(
        nm for nm in rag._KNOWN_NAMES if nm in norm.lower()
    )
    print("\n[2] INTENT")
    print(f"    detected      : {intent}")
    print(f"    entity names  : {entity_names or 'none'}")
    print(f"    boosted kinds : (see rag.retrieve INTENT_BOOST for '{intent}')")

    # ---- stage 3: FTS terms ----
    terms = [t for t in re.findall(r"[\w]+", norm.lower()) if t not in rag.STOP and len(t) > 1]
    expanded = []
    for t in terms:
        variants = [t]
        for tail in rag.STEM_TAIL:
            if t.endswith(tail) and len(t) - len(tail) >= 3:
                base = t[: len(t) - len(tail)]
                if base not in variants:
                    variants.append(base)
        expanded.extend(variants)
    expanded = list(dict.fromkeys(expanded))
    print("\n[3] FTS MATCH TERMS")
    print(f"    base terms    : {terms}")
    print(f"    w/ stemming   : {expanded}")

    # which terms actually match something?
    con = sqlite3.connect(DB)
    term_hits = {}
    for t in expanded:
        try:
            n = con.execute("SELECT count(*) FROM kb WHERE kb MATCH ?", (t,)).fetchone()[0]
        except sqlite3.OperationalError:
            n = -1
        if n:
            term_hits[t] = n
    dead = [t for t in expanded if t not in term_hits]
    print(f"    matching      : {term_hits or 'NOTHING — query will fail'}")
    if dead:
        print(f"    dead terms    : {dead}")

    # ---- stage 4: retrieval result + expected-chunk check ----
    t0 = __import__("time").time()
    ctx, hits = rag.build_context(question)
    dt = __import__("time").time() - t0
    stats = dict(rag.LAST_RETRIEVAL_STATS)
    print(f"\n[4] RETRIEVAL  ({dt * 1000:.0f} ms, stats={stats})")
    print(f"    chunks out    : {len(hits)}")
    for i, h in enumerate(hits[:24], 1):
        prov = rag._prov_map().get(h.get("id"), ("?", "?"))
        flag = " HOP" if h.get("_hop") else ""
        print(f"    {i:2}. {h['id']}  [{h['kind']}|{prov[1]}]{flag}")
        if show_body:
            prev = re.sub(r"\s+", " ", h["body"])[:100]
            print(f"        {prev}")

    # ---- stage 5: answerability (post-hoc, same rule the engine applies) ----
    ans = rag.classify_answerability(question, hits)
    print(f"\n[5] ANSWERABILITY: {ans}")
    if ans == "insufficient_context":
        mentioned = [nm for nm in rag._KNOWN_NAMES if nm in question.lower()]
        hit_names = {h["name"].lower() for h in hits}
        print(f"    mentioned {mentioned} but hit names were {sorted(hit_names)[:8]}")

    # ---- stage 6: what WOULD the LLM see (context size only, no call) ----
    print(f"\n[6] CONTEXT BUILT: {len(ctx)} chars ({len(ctx) // 4} ~tokens est.) — zero LLM tokens spent")
    con.close()
    print()
    return {"intent": intent, "chunks": len(hits), "answerability": ans}


def main():
    args = sys.argv[1:]
    if args:
        q = " ".join(args)
        diagnose(q, show_body="--body" in q or "--body" in sys.argv)
        return
    demo = [
        "What does Ayaka's burst do?",                # exact fact
        "ناحیده متریال ارتقا",                          # Persian glossary
        "who is better for Hu Tao: Xingqiu or Yelan?",  # comparison
        "is vesna's sig a good weapon for zibai c0?",   # weapon-fit
        "how reliable are the answers so far?",         # chitchat-ish
    ]
    for q in demo:
        diagnose(q)


if __name__ == "__main__":
    main()
