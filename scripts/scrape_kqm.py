#!/usr/bin/env python3
"""Scrape KeqingMains (KQM) character guides into data/kqm/*.json
Each guide -> {url, title, chunks: [{heading, text}]}"""
import json
import os
import re
import time
import html as htmlmod
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "data", "kqm"))
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}


def get(url):
    r = httpx.get(url, headers=H, timeout=45, follow_redirects=True)
    r.raise_for_status()
    return r.text


def guide_urls():
    all_urls = []
    for s in ["wp-sitemap-posts-post-1.xml", "wp-sitemap-posts-page-1.xml",
              "wp-sitemap-posts-quick-guides-1.xml", "wp-sitemap-posts-misc-1.xml"]:
        try:
            r = httpx.get(f"https://keqingmains.com/{s}", headers=H, timeout=30, follow_redirects=True)
            all_urls.extend(re.findall(r"<loc>([^<]+)</loc>", r.text))
        except Exception:
            pass
    # root-level slugs are the character/team guides
    urls = [u for u in all_urls if re.match(r"https://keqingmains\.com/[a-z0-9\-]+/?$", u)]
    return sorted(set(urls))


def parse_guide(url):
    h = get(url)
    title_m = re.search(r"<title>([^<]+)</title>", h)
    title = htmlmod.unescape(title_m.group(1)).split(" - KQM")[0].strip() if title_m else url

    # isolate article body
    art = re.search(r"<article[^>]*>(.*?)</article>", h, re.S) or re.search(r"<main[^>]*>(.*?)</main>", h, re.S)
    body = art.group(1) if art else h

    # cut at comments section / footer
    for stop in ["<footer", 'id="comments"', 'class="post-navigation"']:
        i = body.find(stop)
        if i > 0:
            body = body[:i]

    # split into chunks by h2/h3
    parts = re.split(r"(<h[23][^>]*>.*?</h[23]>)", body, flags=re.S)
    chunks = []
    cur_head = "Overview"
    for p in parts:
        hm = re.match(r"<h[23][^>]*>(.*?)</h[23]>", p, re.S)
        if hm:
            cur_head = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", hm.group(1))).strip()[:80]
            continue
        # paragraphs & lists to text
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", p, flags=re.S)
        text = re.sub(r"<li[^>]*>", "\n- ", text)
        text = re.sub(r"<(p|div|tr|br)[^>]*>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = htmlmod.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" ?\n ?", "\n", text)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        # drop nav junk
        if len(text) < 120:
            continue
        if re.search(r"Read more|Share this|Related Articles|Leave a comment|Click to comment|Prev Article|Next Article", text, re.I):
            continue
        chunks.append({"heading": cur_head, "text": text[:2200]})
    return {"url": url, "title": title, "chunks": chunks}


def main():
    os.makedirs(OUT, exist_ok=True)
    urls = guide_urls()
    print(f"guides: {len(urls)}")
    done = 0
    all_data = {}
    for i, u in enumerate(urls):
        slug = u.rstrip("/").split("/")[-1]
        out = os.path.join(OUT, f"{slug}.json")
        if os.path.exists(out):
            continue
        try:
            data = parse_guide(u)
            if data["chunks"]:
                all_data[slug] = data
                with open(out, "w") as f:
                    json.dump(data, f, ensure_ascii=False)
                done += 1
        except Exception as e:
            print(f"  ERR {slug}: {str(e)[:80]}")
        if i % 25 == 0:
            print(f"  {i}/{len(urls)}")
        time.sleep(0.3)
    print(f"scraped {done} new guides")
    print("DONE")


if __name__ == "__main__":
    main()
