#!/usr/bin/env python3
"""Genshin RAG web app — same engine as the Telegram bot, one codebase.

FastAPI on 127.0.0.1:8010, nginx proxies /genshin/ here.
Reuses bot/rag.py (retrieval + LLM) and bot/chitchat.py (zero-token gate)
directly — the Telegram bot stays the only other entrypoint.
"""
import hashlib
import ipaddress
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(HERE, "..", "bot")
sys.path.insert(0, BOT_DIR)

import rag  # noqa: E402
import chitchat  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

META = os.path.join(HERE, "..", "data", "manifest.json")
LOG_PATH = os.path.join(HERE, "..", "data", "query_log.jsonl")

RATE_N = int(os.environ.get("GENSHIN_BOT_RATE_N", "15"))
RATE_WINDOW = 3600
MAX_Q = 300
_ip_hits: dict[str, list[float]] = {}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# CORS: the same chat UI ships as a static GitHub Pages site, calling this API
# cross-origin. GET+POST only, no credentials — read/write here is Q&A text.
_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "GENSHIN_WEB_ORIGINS",
    "https://amirhossein-borzou.github.io,https://gigpt.github.io,https://borzou.site"
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Ask(BaseModel):
    q: str


def _client_ip(request: Request) -> str:
    # CF sets this reliably even when a client spoofs X-Forwarded-For
    cf_ip = request.headers.get("cf-connecting-ip", "")
    if cf_ip:
        try:
            return str(ipaddress.ip_address(cf_ip.strip()))
        except ValueError:
            pass
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        try:  # leftmost = original client
            return str(ipaddress.ip_address(xff.split(",")[0].strip()))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"


def _rate_limited(key: str) -> bool:
    now = time.time()
    hits = [t for t in _ip_hits.get(key, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_N:
        _ip_hits[key] = hits
        return True
    hits.append(now)
    _ip_hits[key] = hits
    return False


def _log(uid_hash: str, q: str, kind: str, **kw) -> None:
    rec = {"ts": round(time.time(), 3), "user": uid_hash, "q": q,
           "kind": kind, "iface": "web", **kw}
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


@app.get("/api/health")
def health():
    try:
        ver = json.load(open(META))["live"]
    except Exception:
        ver = "?"
    return {"ok": True, "version": ver}


@app.post("/api/ask")
async def ask(body: Ask, request: Request):
    q = (body.q or "").strip()[:MAX_Q]
    ip = _client_ip(request)
    uid = hashlib.sha256(ip.encode()).hexdigest()[:16]  # same privacy scheme as the bot
    if not q:
        return JSONResponse({"error": "empty"}, status_code=400)
    if _rate_limited(ip):
        _log(uid, q, kind="rate_limited")
        return JSONResponse({"error": "rate_limited",
                             "message": f"Rate limit: max {RATE_N} questions/hour. Please wait a bit."},
                            status_code=429)
    # chitchat gate (zero tokens) — same two-strike rule as the Telegram bot
    try:
        if chitchat.is_chitchat(q):
            reply = chitchat.CHITCHAT_REPLY
            _log(uid, q, kind="chitchat", answer_len=len(reply))
            return JSONResponse({"answer": reply, "sources": [], "chitchat": True})
    except Exception:
        pass  # gate must never break answering
    t0 = time.time()
    try:
        # rag.answer does blocking SQLite + HTTP (GLM) — keep the event loop free
        answer, hits = await __import__("asyncio").to_thread(rag.answer, q)
        srcs: list[str] = []
        for h in hits:
            if h.get("name") and h["name"] not in srcs:
                srcs.append(h["name"])
        stats = dict(getattr(rag, "LAST_RETRIEVAL_STATS", {}))
        _log(uid, q, kind="ok", sources=srcs[:6], latency=round(time.time() - t0, 1),
             answer_len=len(answer), retrieval=stats,
             answerability=stats.get("answerability", "unknown"))
        try:
            ver = json.load(open(META))["live"]
        except Exception:
            ver = ""
        return JSONResponse({"answer": answer, "sources": srcs[:4],
                             "version": ver,
                             "latency_s": round(time.time() - t0, 1)})
    except Exception:
        # never leak internals to visitors
        _log(uid, q, kind="error", latency=round(time.time() - t0, 1))
        return JSONResponse({"error": "internal",
                             "message": "Something went wrong. Try again in a minute."},
                            status_code=500)


# static chat UI — source of truth is ../docs/ (also served by GitHub Pages)
_docs = os.path.join(HERE, "..", "docs")
app.mount("/", StaticFiles(directory=_docs, html=True), name="ui")
