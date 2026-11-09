# GIGPT — Domain RAG Bot: Technical Report

**Project:** `@GIGPT_bot` — Genshin Impact knowledge assistant on Telegram
**Stack:** Python 3.11 · python-telegram-bot 22.x · SQLite FTS5 · httpx · GLM-4.x (OpenAI-compatible endpoint)
**Live since:** 2026-11-08 · **Deployment:** systemd unit on a Linux VPS
**Author:** Amirhossein Tayebi (@AmirhT)

---

## 1. What It Is

GIGPT is a domain-specific Retrieval-Augmented Generation (RAG) assistant. Users ask
Genshin Impact questions in natural language (English or Persian); the system retrieves
relevant ground-truth records from a local knowledge base and a reasoning LLM composes
the answer strictly from that context.

Design goal: **precise, current, verifiable game answers with zero hallucination** —
something neither a vanilla LLM (stale training data) nor raw JSON dumps (unreadable) can
deliver alone.

---

## 2. Architecture

```
                     ┌──────────────────────────────────────────────┐
                     │                 DATA SOURCES                 │
                     │  nanoka.cc (game API)   Game8   KQM   curated│
                     └───────┬──────────────┬────────┬──────┬──────┘
                             │              │        │      │
                     download_data.py  scrape_game8.py  scrape_builds.py
                             │        scrape_kqm.py        │
                             ▼                             ▼
                     raw JSON on disk  ───────────►  build_kb.py
                                                     │ parse → clean → chunk
                                                     ▼
                                            SQLite FTS5 (~6.1k chunks)
                                                     │
  user question ──► normalize (glossary+stem) ──► retrieve ──► second-hop expand
                                                     │
                                                     ▼
                                          prompt (SYSTEM + CONTEXT + Q)
                                                     │
                                                     ▼
                                             GLM (reasoning ON)
                                                     │
                                                     ▼
                                       answer + sources footer → Telegram
```

### 2.1 Data ingestion layer

| Script | Source | Output | Notes |
|---|---|---|---|
| `download_data.py` | nanoka.cc API | 152 full character kits + 2 beta kits + 289 full weapon files + indexes | Browser UA required; polite 0.12–0.15 s pacing; incremental (skips existing files) |
| `scrape_game8.py` | Game8 wiki | char tier list (129), weapon tier list (192), artifact sets (60) | Plain `httpx` — no WAF encountered; HTML table parsing via regex |
| `scrape_builds.py` | 500 Game8 build pages | per-char signature weapon (68 explicit), best weapons/sets | Multi-variant signature-phrase regex; junk-capture rejection |
| `scrape_kqm.py` | KeqingMains (WordPress) | 143 guides → heading-split chunks | Discovered via `wp-sitemap-*.xml`; article-body isolation; nav-junk filtering |

All scrapers are **incremental and idempotent** — safe to re-run, they only fetch what's
missing, then `build_kb.py` rebuilds the entire index deterministically.

### 2.2 Knowledge base: chunking strategy

Instead of naive fixed-size chunking, the KB uses **semantic unit chunks** — one chunk
per game concept:

- one chunk per skill (with extracted skill-type: Normal Attack / Elemental Skill / Burst),
- one per passive talent, one per constellation (C1–C6),
- one per ascension+talent material set (with per-tier lines and totals),
- one per weapon (base ATK at lv.90 computed from growth curves, substat, R1+R5 refinements),
- one per artifact set (2pc/4pc bonus text),
- one per character build (signature, recommended weapons/sets),
- one per KQM guide section (heading-scoped).

This granularity matters: a question about a specific constellation retrieves that
constellation's exact text — not a 2k-token dump of the whole character page.

**Provenance tagging** is built in: beta characters are stored with kind `beta` and an
explicit `[BETA — unreleased, subject to change]` prefix on every chunk, and community
content (Game8/KQM) is labeled as such in-body — so the LLM can and must cite the nature
of its source.

### 2.3 Retrieval pipeline (the interesting part)

The retriever is multi-stage, in `bot/rag.py`:

1. **Query normalization** — Persian-digit transliteration, then a curated Persian→English
   glossary (game terms: «هیلت ایتاکا»→burst; «اسنشن»→ascension; and ~100 character-name
   transliterations). Longest-key matching with consumption so «هیلت ایتاکا» doesn't also
   emit «هیلت»→heal.
2. **Naive stemming** — `ing/er/ed/ies/s` suffix stripping expands `prefarming`→`prefarm`,
   `materials`→`material` — compensating for FTS5's lack of a stemmer.
3. **Entity-anchored fetch** — for every candidate entity term, an FTS query constrained
   by `name MATCH term` pulls that entity's own chunks, so a multi-entity question gets
   balanced coverage.
4. **Core-kit fill (COLLATE NOCASE)** — every mentioned entity gets its core
   `character/tier/beta` chunks prepended regardless of FTS rank. (This fixed a real bug:
   SQLite's `=` on mixed-case names is case-sensitive while FTS MATCH is not, so kits
   were silently missing from context.)
5. **Global FTS fetch** with `bm25` ranking fills remaining slots.
6. **Round-robin balancing** — results are grouped per entity and interleaved so one
   popular character can't crowd out others in a comparison question.
7. **Second-hop expansion** — build/knowledge chunks are scanned for concrete
   weapon/artifact names (sliding 1–4-word window over capitalized tokens); matching
   full-weapon chunks (preferring the rich `Refinement:` variant over the raw index row)
   are appended and flagged `_hop` so they survive the context cap.

Final context: ≤24 chunks, deduped by header, with provenance labels intact.

### 2.4 Generation

- System prompt: answer **strictly from context**, cite version, never invent data;
  task-specific guidelines (compare material lists item-by-item; two-layer weapon-fit
  analysis: raw stats always active vs passive conditional; label inferences; flag beta data).
- Reasoning stays **ON** (user preference): the model thinks before answering, so
  `max_tokens=4000` to leave room for the final answer after the reasoning trace.
- Temperature 0.3; answers in English (GLM's Persian output quality was unreliable);
  Persian→English understanding handled by the retrieval-side glossary instead.

---

## 3. Evaluation

### 3.1 Benchmark design

A 40-question test set (`data/test_results.jsonl`, runner `scripts/run_testset.py`)
covering six categories: basic build lookup (10), team synergy (10), comparative
reasoning (10), multi-hop composition (5), negative/unanswerable (5), plus reference
answers. Scoring is **LLM-as-judge** (same GLM endpoint, temperature 0) on four 1–5
metrics: retrieval quality, faithfulness, relevance, completeness.

### 3.2 Results

| Metric | Score (39/40 scored) |
|---|---|
| Retrieval | 4.69 / 5 |
| **Faithfulness** | **4.90 / 5** |
| Relevance | 4.95 / 5 |
| Completeness | 4.44 / 5 |

Key outcomes:

- **No fabricated game data in any answer** — the highest-weighted failure mode for
  domain RAG bots was absent across all 40 runs, including adversarial unanswerable
  questions ("exact DPS delta at R1?", "compare an artifact I haven't shown you").
- Negative/unanswerable category scored near-perfect: the bot refuses precisely and
  explains what data would be needed instead of guessing.
- Multi-hop team-composition questions (4 characters × sets × stats) are grounded and
  mostly complete; residual incompleteness traces to context-cap trade-offs.

### 3.3 Debugging wins worth noting

Each of these was found by real usage and fixed at the root cause:

| Symptom | Root cause | Fix |
|---|---|---|
| "Burst" queries missed the burst chunk | Skill-type labels live in colored spans, not always present | Label validation + positional fallback (last skill = Burst) |
| Persian queries retrieved nothing | FTS index is English-only | Glossary + query augmentation |
| Model answered "heal" for «هیلت» | Raw Persian reached the LLM unreinterpreted | Matched-glossary notes injected into the prompt |
| Empty content responses | GLM reasoning consumed the token budget | max_tokens 900→4000 (kept reasoning ON) |
| Nicole's kit missing from comparisons | `name = ?` case sensitivity vs lowercased queries | `COLLATE NOCASE` core-kit fill |
| One character hogged all context slots | bm25 rank imbalance | Round-robin interleaving |
| "Signature weapon" questions lacked stats | Hop expansion returned raw index row (no passive) | Prefer full-weapon chunk by `body LIKE '%Refinement:%'` |
| Engine errors during eval | Test runner didn't pass the API key | Fixed harness (not the engine) |
| Chatty messages burned full RAG+LLM cycles ("how reliable are the answers so far?") | No filter before retrieval; FTS matched junk chunks and GLM ran anyway | Zero-token chitchat gate (`bot/chitchat.py`): two-strike rule — game signal (game words / glossary term / known entity name) must be present, else a short message with chat/meta markers gets a canned reply without touching the LLM |

---

## 4. Production concerns

- **Security review (pre-public):** secrets only in `bot.env` (0600); no user input ever
  reaches a shell; `/update` is owner-only and doesn't echo internal paths; error replies
  are generic (no stack-trace/key leakage); outbound-only polling (no listening ports);
  LLM output rendered as plain text (no HTML injection surface).
- **Abuse control:** per-user rate limit (15 queries/hour, configurable) protects the
  upstream LLM quota from scripted spam; `/start` documents the limit. A zero-token
  chitchat gate (`bot/chitchat.py`) short-circuits non-game chatter before retrieval —
  a game-signal check (game vocabulary, Persian glossary term, or known entity name)
  must pass, otherwise chat/meta messages get a canned reply and never reach the LLM;
  ambiguous messages fall through to the normal RAG path (fail-open).
- **Observability:** every query is logged to `data/query_log.jsonl` — timestamp,
  pseudonymous SHA-256 user hash (never raw IDs), question, outcome kind, latency,
  retrieved sources. `scripts/stats_querylog.py` summarizes volume, unique users, error
  rate, latency distribution, top questions and mentioned entities.
- **Ops:** single systemd unit, auto-restart, unbuffered logging; data refresh is a
  separate oneshot unit (timer currently disabled at owner's discretion) plus an
  owner-only `/update` command; all scrapers resumable and patch-tolerant.
- **Regression gate (Phase 8):** `scripts/regression_gate.py` re-runs the deterministic
  retrieval eval after every rebuild and compares against floors in
  `data/regression_gate.json` (baseline 2026-11-09 18:59 minus a 0.03 patch-day
  tolerance). `daily_refresh.sh` backs up the old KB first; on gate FAIL the rebuilt
  KB is rolled back and the refresh exits non-zero. The owner-only `/update` command
  runs the same gate and reports GATE-FAIL to the chat. Zero LLM tokens end-to-end.
- **Pipeline diagnostics (Phase 7):** `scripts/diagnose.py "question"` replays every
  retrieval stage (normalization → glossary → intent → FTS terms with dead-term
  detection → chunk list with provenance → answerability verdict → context size)
  deterministically and token-free — the first stop when an answer looks wrong.

---

## 5. Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|---|---|---|
| RAG over fine-tuning | Game data changes every patch; fine-tunes rot and hallucinate numbers | Requires retrieval plumbing (built once, benefits every patch) |
| SQLite FTS5 over vector DB | Exact lexical matches dominate this domain (proper nouns, item names); zero infra | No semantic generalization — mitigated with stemming + glossary |
| Many small semantic chunks over big pages | Precision of retrieval per concept | More rows to balance — solved with round-robin + per-entity fill |
| Two-hop retrieval over one-shot | Build guides name concrete weapons; their stats live elsewhere | Slight latency cost, large grounding win |
| English answers from Persian questions | LLM's Persian prose quality unstable | Persian users read English names/terms natively anyway |
| Reasoning ON | Multi-hop comparisons need analysis; user preference | ~3–8× token cost per query vs direct answer |
| Regression gate on deterministic metrics only | LLM-judge gates are non-deterministic (judge drift) and expensive; retrieval regressions are measurable token-free | Answer-quality drops without retrieval drops need the (expensive) judge — out of scope for the gate |

---

## 6. Repo Layout

```
genshin-bot/
├── bot/
│   ├── main.py          # Telegram frontend: handlers, rate limit, logging
│   └── rag.py           # Retrieval + prompt + LLM client (the engine)
├── scripts/
│   ├── download_data.py # nanoka.cc ingestion (kits, beta, weapons)
│   ├── build_kb.py      # parser/chunker → SQLite FTS5
│   ├── scrape_game8.py  # tier lists, artifact sets
│   ├── scrape_builds.py # per-character build pages
│   ├── scrape_kqm.py    # KeqingMains guides
│   ├── run_testset.py   # 40-q benchmark + LLM judge
│   ├── stats_querylog.py# production analytics
│   └── daily_refresh.sh # full pipeline (timer currently off)
├── data/
│   ├── kb.sqlite        # 6,122 chunks
│   ├── query_log.jsonl  # production telemetry
│   ├── test_results.jsonl
│   └── {kits,weapons,game8,kqm,knowledge}/
└── genshin-bot.service
```

---

## 7. Possible Next Steps

- Persian answer mode (optional per-user toggle) once a stable Persian-capable model is
  available on the endpoint.
- Vector/semantic secondary index (e.g. sqlite-vec) hybridized with FTS5 for paraphrase
  robustness ("best sword for Ayaka" vs exact item lookups).
- Auto-judge on production logs: sample answered questions daily, score against retrieved
  context, alert on faithfulness dips after game patches.
- Team-level pages: a dedicated "team comp" chunk type encoding role coverage per
  composition to sharpen multi-character answers.
