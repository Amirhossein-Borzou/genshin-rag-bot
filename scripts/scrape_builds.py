#!/usr/bin/env python3
"""Scrape Game8 'Best Builds' pages: signature/best weapons, best artifact sets per character.
Produces data/game8/char_builds.json: {char: {best_weapons: [...], bis: str, best_sets: [...]}}"""
import json
import os
import re
import time
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "data", "game8"))
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
TIER_URL = "https://game8.co/games/Genshin-Impact/archives/297465"


def get(url):
    r = httpx.get(url, headers=H, timeout=40, follow_redirects=True)
    r.raise_for_status()
    return r.text


def strip(s):
    t = re.sub(r"<[^>]+>", " | ", s)
    t = re.sub(r"(\s*\|\s*)+", " | ", t)
    t = t.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", t).strip()


def char_build_links():
    """char name -> build page url, from the tier list page links."""
    h = get(TIER_URL)
    links = {}
    for url, name in re.findall(
        r'href="(https://game8\.co/games/Genshin-Impact/archives/\d+)"[^>]*>\s*<img[^>]*alt="Genshin - ([^"]+?)"', h
    ):
        name = name.replace(" Image", "").replace(" DPS Rank", "").replace(" Sub-DPS Rank", "").replace(" Support Rank", "")
        if name and name not in links:
            links[name] = url
    return links


def parse_build_page(url, char):
    h = get(url)
    out = {"build_url": url}
    # weapons section: from 'Best Weapons' to the next <h2
    m = re.search(r"Best Weapons(.*?)<h2", h, re.S)
    if not m:
        m = re.search(r"Best Weapons(.{0,6000})", h, re.S)
    if m:
        seg = m.group(1)
        out["best_weapons_text"] = strip(seg)[:1600]
        # signature phrase variants:
        #   "best-in-slot ... signature weapon, the | X |"
        #   "X | is her signature weapon and most likely her best-in-slot"
        s = strip(seg)
        bis = re.search(r"signature weapon,?\s*(?:the\s*)?\|\s*([^|]+?)\s*\|", s)
        if not bis:
            bis = re.search(r"\|\s*([^|]+?)\s*\|\s*(?:is|are)\s+(?:her|his|their)\s+signature\s+weapon", s)
        if not bis:
            bis = re.search(r"signature\s+weapon[^|]*?\|\s*([^|]+?)\s*\|", s)
        if bis:
            sig = bis.group(1).strip(" |")
            # reject junk captures (sentence fragments from 'Alternative options...' phrasing)
            if len(sig) < 45 and not sig.lower().startswith(("alternative", "other", "you")):
                out["signature"] = sig
        # weapon names = link texts inside the segment
        wnames = []
        for l in re.findall(r"<a[^>]*>(.*?)</a>", seg, re.S):
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", l)).strip()
            if t and t not in wnames and len(t) < 45:
                wnames.append(t)
        out["best_weapons"] = wnames[:8]
    # artifacts section: 'Best Artifacts' to next <h2
    m = re.search(r"Best Artifacts(.*?)<h2", h, re.S)
    if not m:
        m = re.search(r"Best Artifacts(.{0,6000})", h, re.S)
    if m:
        seg = m.group(1)
        out["best_artifacts_text"] = strip(seg)[:1600]
        anames = []
        for l in re.findall(r"<a[^>]*>(.*?)</a>", seg, re.S):
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", l)).strip()
            if t and t not in anames and len(t) < 55:
                anames.append(t)
        out["best_artifacts"] = anames[:8]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    links = char_build_links()
    print(f"build pages found: {len(links)}")
    out = {}
    for i, (name, url) in enumerate(sorted(links.items())):
        try:
            out[name] = parse_build_page(url, name)
        except Exception as e:
            out[name] = {"error": str(e)[:120]}
        if i % 20 == 0:
            print(f"  {i}/{len(links)}")
        time.sleep(0.4)
    json.dump(out, open(os.path.join(OUT, "char_builds.json"), "w"), indent=1)
    n_sig = sum(1 for v in out.values() if v.get("signature"))
    print(f"saved {len(out)} builds, {n_sig} with explicit signature")
    print("DONE")


if __name__ == "__main__":
    main()
