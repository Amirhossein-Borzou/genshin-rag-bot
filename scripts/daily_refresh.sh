#!/usr/bin/env bash
# Daily data refresh: download new nanoka data and rebuild the FTS index.
set -e
cd /home/borzou/genshin-bot
./venv/bin/python scripts/download_data.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_game8.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_builds.py >> data/update.log 2>&1
./venv/bin/python scripts/scrape_kqm.py >> data/update.log 2>&1
./venv/bin/python scripts/build_kb.py >> data/update.log 2>&1
echo "$(date '+%F %T') refresh ok" >> data/update.log
