#!/usr/bin/env python3
"""Summarize the bot's query log: volume, unique users, top questions, error rate.
Usage: python3 stats_querylog.py [days]"""
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.abspath(os.path.join(HERE, "..", "data", "query_log.jsonl"))

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
SINCE = time.time() - DAYS * 86400


def main():
    if not os.path.exists(LOG):
        print("no log yet")
        return
    rows = []
    for line in open(LOG, encoding="utf-8"):
        try:
            r = json.loads(line)
            t = time.mktime(time.strptime(r["ts"], "%Y-%m-%d %H:%M:%S"))
            if t >= SINCE:
                rows.append(r)
        except Exception:
            continue
    if not rows:
        print(f"no queries in last {DAYS} days")
        return
    n = len(rows)
    users = Counter(r["user"] for r in rows)
    kinds = Counter(r["kind"] for r in rows)
    lat = [r["latency_s"] for r in rows if r.get("latency_s")]
    print(f"Last {DAYS}d: {n} queries | {len(users)} unique users")
    print(f"kinds: {dict(kinds)}")
    if lat:
        print(f"latency: avg {sum(lat)/len(lat):.1f}s | max {max(lat):.1f}s")
    print("\nTop questions:")
    for q, c in Counter(r["q"].lower().strip() for r in rows).most_common(10):
        print(f"  x{c}  {q[:90]}")
    # most-queried entities (capitalized names)
    ents = Counter()
    for r in rows:
        for w in r["q"].split():
            if w[:1].isupper() and len(w) > 2:
                ents[w.strip("?'*!.,")] += 1
    print("\nTop mentioned entities:", ", ".join(f"{k}({v})" for k, v in ents.most_common(12)))
    err = kinds.get("error", 0) + kinds.get("rate_limited", 0)
    print(f"\nerrors+limits: {err}/{n} ({100*err/n:.0f}%)")


if __name__ == "__main__":
    main()
