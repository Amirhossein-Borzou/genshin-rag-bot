#!/usr/bin/env python3
"""Genshin Impact RAG Telegram bot (nanoka.cc data)."""
import asyncio
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import rag  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.constants import ChatAction  # noqa: E402
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters  # noqa: E402

TOKEN = os.environ["GENSHIN_BOT_TOKEN"]
ALLOWED = {
    int(x) for x in os.environ.get("GENSHIN_BOT_ALLOWED", "").replace(" ", "").split(",") if x
}
OWNER = next(iter(ALLOWED)) if ALLOWED else None

# public-mode rate limiting: N queries per user per hour (protects the LLM quota)
import time as _time
RATE_N = int(os.environ.get("GENSHIN_BOT_RATE_N", "15"))
RATE_WINDOW = 3600
_user_hits: dict[int, list[float]] = {}


def rate_limited(user_id: int) -> bool:
    now = _time.time()
    hits = [t for t in _user_hits.get(user_id, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_N:
        _user_hits[user_id] = hits
        return True
    hits.append(now)
    _user_hits[user_id] = hits
    return False

META = os.path.join(HERE, "..", "data", "manifest.json")

WELCOME = (
    "⚔️ Genshin Impact Assistant\n"
    "I answer from live game data (nanoka.cc) — characters, skills, "
    "constellations, ascension materials, weapons, artifacts — plus "
    "build guides from Game8 & KeqingMains.\n\n"
    "Just ask, e.g.:\n"
    "• What does Ayaka's burst do?\n"
    "• Nahida ascension materials\n"
    "• Mavuika C2 effect\n\n"
    "Limit: 15 questions/hour. Beta characters are datamined and may change."
)


def _ver():
    try:
        return json.load(open(META))["live"]
    except Exception:
        return "?"


# ---- query analytics log (for later evaluation) ----
# privacy: only a hashed user id is stored, never usernames or phone numbers.
import hashlib as _hl

LOG_PATH = os.path.join(HERE, "..", "data", "query_log.jsonl")


def log_query(uid, question, kind="ok", sources=None, latency=None, answer_len=None, retrieval=None, answerability=None):
    try:
        h = _hl.sha256(f"{uid}:{TOKEN}".encode()).hexdigest()[:12]
        rec = {
            "ts": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "user": h,  # pseudonymous hash — stable per user, not reversible
            "q": question[:300],
            "kind": kind,
            "latency_s": latency,
            "sources": sources or [],
            "answer_len": answer_len,
            "retrieval": retrieval or {},
            "answerability": answerability or (retrieval or {}).get("answerability", "unknown"),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never break answering


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)


async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Owner-only: re-download data + rebuild KB."""
    if OWNER and update.effective_user.id != OWNER:
        await update.message.reply_text("Owner only.")
        return
    def run():
        a = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "download_data.py")],
                           capture_output=True, text=True, timeout=900)
        b = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "build_kb.py")],
                           capture_output=True, text=True, timeout=300)
        return (a.stdout + a.stderr + "\n" + b.stdout + b.stderr).strip()[-500:]
    out = await asyncio.to_thread(run)
    await update.message.reply_text("Refreshing data… ⏳ done ✅")


async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = (update.message.text or "").strip()
    if not q:
        return
    uid = update.effective_user.id if update.effective_user else 0
    if rate_limited(uid):
        await update.message.reply_text("⚠️ Rate limit: max 15 questions/hour. Please wait a bit.")
        log_query(uid, q, kind="rate_limited")
        return
    # chitchat gate (zero tokens): non-game chatter never reaches the LLM
    try:
        import chitchat
        if chitchat.is_chitchat(q):
            await update.message.reply_text(chitchat.CHITCHAT_REPLY)
            log_query(uid, q, kind="chitchat", answer_len=len(chitchat.CHITCHAT_REPLY))
            return
    except Exception:
        pass  # gate must never break answering
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    t0 = _time.time()
    try:
        answer, hits = await asyncio.to_thread(rag.answer, q)
        srcs = []
        for h in hits:
            if h["name"] not in srcs:
                srcs.append(h["name"])
        footer = f"\n\n📚 {', '.join(srcs[:4])} • v{_ver()}"
        await update.message.reply_text(answer + footer)
        stats = dict(getattr(rag, "LAST_RETRIEVAL_STATS", {}))
        log_query(uid, q, kind="ok", sources=srcs[:6], latency=round(_time.time() - t0, 1),
                  answer_len=len(answer),
                  retrieval=stats,
                  answerability=stats.get("answerability", "unknown"))
    except Exception:
        # never leak internal error details (paths/keys) to users
        await update.message.reply_text("⚠️ Something went wrong. Try again in a minute.")
        log_query(uid, q, kind="error", latency=round(_time.time() - t0, 1))


def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("genshin-bot polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
