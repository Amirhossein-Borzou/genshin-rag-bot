#!/usr/bin/env python3
"""Download Genshin data from nanoka.cc into ~/genshin-bot/data/."""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "https://static.nanoka.cc"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DATA_DIR = os.path.abspath(DATA_DIR)

INDEX_TYPES = ["character", "weapon", "artifact"]


def fetch_json(path, retries=3):
    url = f"{BASE}{path}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                print(f"  FAIL {url}: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    manifest = fetch_json("/manifest.json")
    if not manifest:
        sys.exit("Could not fetch manifest")
    gi = manifest["gi"]
    live = gi["live"]
    beta = gi["latest"]
    print(f"live={live} beta={beta}")

    with open(os.path.join(DATA_DIR, "manifest.json"), "w") as f:
        json.dump({"live": live, "beta": beta, "available": gi["available"]}, f, indent=2)

    # Indexes (id -> summary) for live version
    for t in INDEX_TYPES:
        idx = fetch_json(f"/gi/{live}/{t}.json")
        if idx:
            with open(os.path.join(DATA_DIR, f"{t}_index.json"), "w") as f:
                json.dump(idx, f, ensure_ascii=False, indent=1)
            print(f"index {t}: {len(idx)} entries")

    # Full character kits (en locale)
    char_index = fetch_json(f"/gi/{live}/character.json") or {}
    kits_dir = os.path.join(DATA_DIR, "kits", live, "en")
    os.makedirs(kits_dir, exist_ok=True)
    ok = fail = 0
    for cid in char_index:
        out = os.path.join(kits_dir, f"{cid}.json")
        if os.path.exists(out):
            ok += 1
            continue
        kit = fetch_json(f"/gi/{live}/en/character/{cid}.json")
        if kit:
            with open(out, "w") as f:
                json.dump(kit, f, ensure_ascii=False)
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)  # be polite
    print(f"kits: ok={ok} fail={fail}")

    # Beta-only character kits (unreleased, e.g. Danica) for the KB
    try:
        beta_idx = fetch_json(f"/gi/{beta}/character.json") or {}
        new_ids = [cid for cid in beta_idx if cid not in char_index]
        bkits_dir = os.path.join(DATA_DIR, "kits", beta, "en")
        os.makedirs(bkits_dir, exist_ok=True)
        with open(os.path.join(DATA_DIR, "beta_new_ids.json"), "w") as f:
            json.dump(new_ids, f)
        bok = 0
        for cid in new_ids:
            kit = fetch_json(f"/gi/{beta}/en/character/{cid}.json")
            if kit:
                with open(os.path.join(bkits_dir, f"{cid}.json"), "w") as f:
                    json.dump(kit, f, ensure_ascii=False)
                bok += 1
            time.sleep(0.15)
        print(f"beta new kits: {bok}/{len(new_ids)} {new_ids}")
    except Exception as e:
        print(f"beta kits skipped: {e}")

    # Also save weapons + artifacts full data (they are small indexes with useful info)
    for t in ["weapon", "artifact"]:
        idx = fetch_json(f"/gi/{live}/{t}.json")
        if idx:
            with open(os.path.join(DATA_DIR, f"{t}_live.json"), "w") as f:
                json.dump(idx, f, ensure_ascii=False, indent=1)

    # Full weapon detail files (base ATK, substat, refinement R1-R5, ascension mats)
    widx = fetch_json(f"/gi/{live}/weapon.json") or {}
    wdir = os.path.join(DATA_DIR, "weapons", live)
    os.makedirs(wdir, exist_ok=True)
    wok = 0
    for wid in widx:
        out = os.path.join(wdir, f"{wid}.json")
        if os.path.exists(out):
            wok += 1
            continue
        w = fetch_json(f"/gi/{live}/en/weapon/{wid}.json")
        if w:
            with open(out, "w") as f:
                json.dump(w, f, ensure_ascii=False)
            wok += 1
        time.sleep(0.12)
    print(f"weapon details: {wok}/{len(widx)}")

    print("DONE")


if __name__ == "__main__":
    main()
