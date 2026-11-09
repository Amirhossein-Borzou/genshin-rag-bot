#!/usr/bin/env bash
# Daily data refresh: download new nanoka data and rebuild the FTS index.
# Phase 8: after rebuild, the deterministic regression gate runs. If retrieval
# metrics dropped vs data/regression_gate.json floors, the rebuild is marked
# FAILED and the old KB is restored (gate exit 1). Zero LLM tokens.
set -e
cd /home/borzou/genshin-bot

# keep the pre-refresh KB so a regressing rebuild can be rolled back
cp data/kb.sqlite data/kb.sqlite.bak

./venv/bin/python scripts/download_data.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_game8.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_builds.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_kqm.py >> data/update.log 2>&1
./venv/bin/python scripts/build_kb.py >> data/update.log 2>&1

# regression gate: deterministic retrieval eval vs saved floors
if ./venv/bin/python scripts/regression_gate.py >> data/update.log 2>&1; then
    rm -f data/kb.sqlite.bak
    echo "$(date '+%F %T') refresh ok (gate PASS)" >> data/update.log
else
    mv data/kb.sqlite data/kb.sqlite.regressed
    mv data/kb.sqlite.bak data/kb.sqlite
    echo "$(date '+%F %T') refresh GATE-FAIL: retrieval regressed, KB rolled back (see data/update.log)" >> data/update.log
    exit 1
fi
