# GIGPT — Genshin Impact RAG Assistant for Telegram

[![Benchmark](https://img.shields.io/badge/faithfulness-4.9%2F5-brightgreen)](data/test_results.jsonl) [![Coverage](https://img.shields.io/badge/evidence_coverage-0.64-blue)]() [![Hallucination](https://img.shields.io/badge/hallucination-0%20cases-success)]()

Domain-specific **RAG (Retrieval-Augmented Generation)** assistant that answers Genshin
Impact questions — character kits, constellations, ascension materials, weapon stats &
refinements, artifact sets, team building — strictly from live game data and community
guides. Never from model memory.

**Bot:** [@GIGPT_bot](https://t.me/GIGPT_bot) · **Technical report:** [GIGPT_technical_report.md](GIGPT_technical_report.md)

---

## How it works

```
nanoka.cc (game API) ─┐
Game8 tier lists ─────┤→ scrapers → chunker → SQLite FTS5 (6.1k chunks)
Game8 build pages ────┤                        ↕
KeqingMains guides ───┘              hybrid retrieval (FTS5 + sqlite-vec, RRF)
                                              ↕
Persian query ── glossary+stem ──► GLM (reasoning ON) ──► answer + provenance footer
```

### Retrieval pipeline

1. **Normalize** — Persian-digit transliteration + curated Persian→English glossary
   (game terms and ~100 character transliterations), with longest-match consumption.
2. **Stem** — naive suffix expansion (`prefarming→prefarm`) compensating FTS5's missing stemmer.
3. **Entity-anchored fetch** — per-entity constrained FTS queries for balanced coverage.
4. **Core-kit fill** — `COLLATE NOCASE` exact-name lookup guarantees every mentioned
   character's kit chunks enter the context regardless of bm25 rank.
5. **Semantic path** (feature flag) — local `bge-small` embeddings (384d) in sqlite-vec,
   fused via Reciprocal Rank Fusion (k=60). Falls back to FTS5-only on any failure.
6. **Second-hop expansion** — build chunks are scanned for concrete weapon/artifact names;
   their full stat chunks (base ATK at lv.90, substat, R1/R5 refinements) are pulled with a
   budget (max 6) and dedupe.
7. **Intent-aware boost** — general/build/kit intent reorders chunk kinds; multi-entity
   questions force kit coverage.
8. **Provenance** — every chunk carries source (nanoka/Game8/KQM/curated), status
   (current/beta), and game version; beta chunks are explicitly tagged `PROVISIONAL`.

### Grounding & abstention (zero extra tokens)

- `classify_answerability()` — rule-based: `answerable / partially_answerable /
  insufficient_context / out_of_scope` (beta-aware via cached beta index).
- `sanitize_answer()` — strips any `[source: …]` tags the model invents; the real source
  footer is assembled in application code from actually-retrieved chunks.
- Prompt guidelines force two-layer weapon-fit analysis (raw stats vs passive), itemized
  material comparisons, and labeled inferences for build questions.

---

## Evaluation

Deterministic, LLM-free retrieval benchmark (`scripts/eval_retrieval.py`, ~4s runtime):

| Metric | Baseline | After hybrid + intent |
|---|---|---|
| Evidence Coverage | 0.407 | **0.640** |
| Full coverage | 7/36 | **17/36** |
| Recall@5 | 0.214 | **0.359** |
| Recall@10 | 0.469 | 0.457 |

Answer-quality LLM-judge (40-question set, 4 metrics): **faithfulness 4.90/5, zero
hallucinated game data**, near-perfect abstention on unanswerable questions.

Benchmark schema: `data/benchmark_v2.json` — each case carries `answerable`,
`expected_chunk_ids` (verified against the KB), `expected_answer_facts`, and
`expected_refusal_reason`.

---

## Run it

```bash
git clone https://github.com/Amirhossein-Borzou/genshin-rag-bot.git
cd genshin-rag-bot
python3 -m venv venv && venv/bin/pip install -r requirements.txt

cp .env.example bot.env   # fill in token + key
venv/bin/python scripts/download_data.py      # ~5 min, incremental
venv/bin/python scripts/scrape_game8.py
venv/bin/python scripts/scrape_builds.py      # ~4 min
venv/bin/python scripts/scrape_kqm.py         # ~2 min
venv/bin/python scripts/build_kb.py
venv/bin/python scripts/build_semantic_index.py  # optional, enables hybrid

venv/bin/python bot/main.py                   # polling start
```

`bot/rag.py` also runs standalone: `venv/bin/python bot/rag.py "Ayaka burst damage"`

---

## Repo layout

```
bot/main.py                  Telegram frontend (rate limit, logging, commands)
bot/rag.py                   Retrieval engine + prompt + LLM client
scripts/download_data.py     nanoka.cc ingestion (kits, beta kits, 289 weapons)
scripts/scrape_game8.py      tier lists + artifact sets
scripts/scrape_builds.py     per-character build pages (500)
scripts/scrape_kqm.py        KeqingMains guides (143)
scripts/build_kb.py          chunker → FTS5 + chunk_meta provenance + quality report
scripts/build_semantic_index.py  sqlite-vec embeddings (optional)
scripts/eval_retrieval.py    deterministic Recall@K / MRR / coverage evaluator
scripts/run_testset.py       40-q end-to-end benchmark + LLM judge
scripts/stats_querylog.py    production analytics
data/knowledge/              curated general building knowledge
```

## Privacy

Query logs store a **SHA-256 hash** of the user id — never raw Telegram IDs, names, or
phone numbers. `bot.env` (secrets) is gitignored.

## Status

Public beta. Data refresh is manual (`/update`, owner-only) — the auto-refresh timer is
written but disabled. Feedback welcome via Telegram or issues.
