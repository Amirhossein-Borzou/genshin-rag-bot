#!/usr/bin/env python3
"""Scrape Game8 build metadata (character tier list, weapon tier list, artifact sets)
into JSON files under data/game8/ for the KB builder."""
import json
import os
import re
import time
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "data", "game8"))
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}

CHAR_TIER_URL = "https://game8.co/games/Genshin-Impact/archives/297465"
WEAPON_TIER_URL = "https://game8.co/games/Genshin-Impact/archives/305739"
ARTIFACT_URL = "https://game8.co/games/Genshin-Impact/archives/297493"


def get(url):
    r = httpx.get(url, headers=H, timeout=40, follow_redirects=True)
    r.raise_for_status()
    return r.text


def clean(c):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()


def scrape_char_tiers():
    h = get(CHAR_TIER_URL)
    tables = re.findall(r"<table[^>]*>.*?</table>", h, re.S)
    out = {}  # name -> {role: tier}
    for t in tables:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            ths = re.findall(r"<th[^>]*>(.*?)</th>", row, re.S)
            if not ths:
                continue
            tier_alts = re.findall(r'alt="([^"]+Tier)"', ths[0])
            if not tier_alts:
                continue
            tier = tier_alts[0].replace(" Tier", "")
            for role, c in zip(["DPS", "Sub-DPS", "Support"], re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)[:3]):
                for name in re.findall(r'alt="Genshin - ([^"]+?) (?:DPS|Sub-DPS|Support) Rank"', c):
                    out.setdefault(name, {})[role] = tier
    return out


def scrape_weapon_tiers():
    h = get(WEAPON_TIER_URL)
    tables = re.findall(r"<table[^>]*>.*?</table>", h, re.S)
    out = {}  # name -> [{tier, role}]
    for t in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        if not rows or "Sub DPS" not in rows[0]:
            continue
        for row in rows[1:]:
            ths = re.findall(r"<th[^>]*>(.*?)</th>", row, re.S)
            tier = "?"
            if ths:
                alts = re.findall(r"alt='([^']+?) Rank Icon'|alt=\"([^\"]+?) Rank Icon\"", ths[0])
                if alts:
                    tier = (alts[0][0] or alts[0][1]).replace("Genshin - ", "")
            for role, c in zip(["Main DPS", "Sub DPS", "Support"], re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)[:3]):
                for a, b in re.findall(r"alt='([^']+?) Image'|alt=\"([^\"]+?) Image\"", c):
                    nm = (a or b).replace(" Image", "")
                    out.setdefault(nm, []).append({"tier": tier, "role": role})
    return out


def scrape_artifacts():
    h = get(ARTIFACT_URL)
    tables = re.findall(r"<table[^>]*>.*?</table>", h, re.S)
    out = []
    for t in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        if len(rows) < 2:
            continue
        header = clean(rows[0]).lower()
        if not header.startswith("set set bonus"):
            continue
        for row in rows[1:]:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            if len(cells) < 2:
                continue
            name = clean(cells[0])
            bonus = clean(cells[1])
            if name and bonus:
                out.append({"name": name, "bonus": bonus})
    return out


def main():
    os.makedirs(OUT, exist_ok=True)

    chars = scrape_char_tiers()
    json.dump(chars, open(os.path.join(OUT, "char_tiers.json"), "w"), indent=1)
    print(f"char tiers: {len(chars)}")

    time.sleep(1)
    weapons = scrape_weapon_tiers()
    json.dump(weapons, open(os.path.join(OUT, "weapon_tiers.json"), "w"), indent=1)
    print(f"weapon tiers: {len(weapons)}")

    time.sleep(1)
    arts = scrape_artifacts()
    json.dump(arts, open(os.path.join(OUT, "artifact_sets.json"), "w"), indent=1)
    print(f"artifact sets: {len(arts)}")

    json.dump({"scraped_at": time.strftime("%Y-%m-%d %H:%M")}, open(os.path.join(OUT, "meta.json"), "w"))
    print("DONE")


if __name__ == "__main__":
    main()
