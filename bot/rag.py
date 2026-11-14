#!/usr/bin/env python3
"""Genshin RAG engine: retrieve from FTS5 KB, build prompt, call LLM (avalai, GLM)."""
import json
import os
import re
import sqlite3
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "data", "kb.sqlite")
META = os.path.join(HERE, "..", "data", "manifest.json")

import os as _os
BASE_URL = _os.environ.get("GENSHIN_BOT_LLM_BASE", "https://api.avalai.ir/v1")
API_KEY = _os.environ.get("GENSHIN_BOT_LLM_KEY", "")
MODEL = _os.environ.get("GENSHIN_BOT_LLM_MODEL", "glm-5.3-flash")

STOP = {"the", "a", "an", "is", "of", "for", "to", "in", "on", "and", "or", "what",
        "which", "how", "does", "do", "best", "with", "my", "your", "me", "should",
        "are", "is", "was", "were", "be", "been", "being", "have", "has", "had",
        "can", "could", "would", "will", "shall", "it", "its", "there", "that",
        "this", "these", "those", "something", "anything", "everything"}

STEM_TAIL = {"ing", "ers", "er", "ed", "ies", "s"}

# Persian (Finglish/Farsi) -> KB terms. Longest keys are applied first.
GLOSSARY = {
    # game terms
    "هیلت ایتاکا": "burst", "هرست ایتاکا": "burst", "هیلت": "burst", "هرست": "burst",
    "التیمیت": "burst", "اولت": "burst",
    "نرمال اتک": "Normal Attack", "اتک": "Attack",
    "المنتال اسکیل": "Elemental Skill", "اسکیل": "skill",
    "المون": "element", "المان": "element", "عنصر": "element",
    "اسنشن": "ascension", "آسندنس": "ascension", "ارتقا": "ascension materials level",
    "کانستلیشن": "constellation", "کنستلیشن": "constellation", "کانست": "constellation",
    "سی تو": "C2", "سی سه": "C3", "سی شیش": "C6", "سی یک": "C1",
    "استت": "stats", "امار": "stats",
    "کریت ریت": "crit", "سی ار": "crit rate", "سی دی": "crit dmg",
    "اتچمنت": "artifact", "اتچمنی": "artifact", "ارتیفکت": "artifact",
    "ریلیک": "artifact", "گلاو": "artifact",
    "ریچارج": "Energy Recharge", "انرژی ریچارج": "Energy Recharge",
    "دمیج": "damage DMG", "دج": "damage DMG", "ضربه": "damage DMG",
    "باف": "buff", "دیباف": "debuff",
    "هیلر": "heal", "هیل": "heal", "شیلد": "shield",
    "سلاح": "weapon", "شمشیر": "sword", "کاتالیست": "catalyst", "کمان": "bow",
    "کلیمور": "claymore", "نیزه": "polearm",
    "کاراکتر": "character", "پرسوناژ": "character",
    "متریال": "materials", "جنس ارتقا": "ascension materials",
    "تالنت": "talent", "پسیو": "passive", "پسیوو": "passive",
    "ریجن": "region", "منطقه": "region",
    "بهترین": "best",
    # popular characters (Persian transliterations)
    "آیاکا": "Ayaka", "کامیساتو": "Kamisato",
    "ناحیده": "Nahida", "ناهیدا": "Nahida", "ناحید": "Nahida",
    "ماویکا": "Mavuika", "مافویکا": "Mavuika",
    "آرلچینو": "Arlecchino", "ارلچینو": "Arlecchino", "آرلکینو": "Arlecchino",
    "فوریا": "Furina", "فوورینا": "Furina", "فورین": "Furina",
    "نوولت": "Neuvillette", "نویوت": "Neuvillette", "نوویلت": "Neuvillette",
    "رایدن": "Raiden", "شوگان": "Shogun",
    "ژونگ لی": "Zhongli", "ژونگلی": "Zhongli", "جونگلی": "Zhongli",
    "هو تائو": "Hu Tao", "هوتائو": "Hu Tao",
    "گانیو": "Ganyu", "ایولا": "Eula",
    "کازوها": "Kazuha", "سیینو": "Cyno", "سینو": "Cyno",
    "تیغناری": "Tighnari", "نیلوی": "Nilou", "نیلو": "Nilou",
    "لاوما": "Lauma", "فلینز": "Flins", "نفر": "Nefer",
    "کلوریند": "Clorinde", "کلریند": "Clorinde",
    "اسکیرک": "Skirk", "ونتی": "Venti", "وِنتی": "Venti",
    "الهایثم": "Alhaitham", "الحیثم": "Alhaitham",
    "وریوزلی": "Wriothesley", "ریوزلی": "Wriothesley",
    "ناویا": "Navia", "شووروز": "Chevreuse", "چوروز": "Chevreuse",
    "سیگوینه": "Sigewinne", "سیگ وینه": "Sigewinne",
    "کینیک": "Kinich", "موالانی": "Mualani", "چاسکا": "Chasca",
    "سیترالی": "Citlali", "ایانسان": "Iansan", "وارسا": "Varesa",
    "اورورون": "Ororon", "کلینده": "Charlotte", "شارلوت": "Charlotte",
    "لی نی": "Lyney", "لینت": "Lynette", "فرمینه": "Freminet",
    "ژیانگ لینگ": "Xiangling", "شینگ چیو": "Xingqiu", "شیائو": "Xiao",
    "کلی": "Klee", "دیلوک": "Diluc", "کیا": "Kaeya", "جین": "Jean",
    "فیشل": "Fischl", "باربارا": "Barbara", "نوول": "Noelle",
    "بیدو": "Beidou", "شینوبو": "Shinobu", "یائوی": "Yaoyao",
    "کللی": "Collei", "دیونا": "Diona", "یومیا": "Yoimiya",
    "یائمی کو": "Yae Miko", "میکو": "Yae Miko",
    "شیان یون": "Xianyun", "لایلا": "Layla", "کندیس": "Candace",
    "تیغنری": "Tighnari", "سایتو": "Heizou", "هیزو": "Heizou",
    "سیتلا لی": "Citlali", "اینه فا": "Ineffa", "ایفا": "Ifa",
    "داک": "Durin", "ورکا": "Varka", "کلمبین": "Columbina",

    # 2026-11-14: new-beta + roster gaps (web user hit out_of_scope on ساریتسا/میتیا)
    "تزاریتسا": "Tsaritsa",
    "ساریتسا": "Tsaritsa",
    "میتیا": "Mitya",
    "متیا": "Mitya",
    "دانیکا": "Danica",
    "نیکول": "Nicole",
    "وزنا": "Vesna",
    "وسنا": "Vesna",
    "زیبای": "Zibai",
    "زی بی": "Zibai",
    "پرون": "Prune",
    "لائوما": "Lauma",
    "اینفا": "Ineffa",
    "آینو": "Aino",
    "اینو": "Aino",
    "وادیانیتسا": "Vodyanitsa",
    "مانکین": "Manekin",
    "الیوسا": "Alyosha",
    "جاهودا": "Jahoda",
    "لینیا": "Linnea",
    "لوئن": "Lohen",
    "اودت": "Odette",
    "ساندرون": "Sandrone",
    "والری": "Valeriy",
    "ایلوگا": "Illuga",
    "شنه": "Shenhe",
    "شن هه": "Shenhe",
    "کوکومی": "Kokomi",
    "کوکومه": "Kokomi",
    "که کینگ": "Keqing",
    "کیکینگ": "Keqing",
    "ایتو": "Itto",
    "آراتاکی ایتو": "Arataki Itto",
    "بایجو": "Baizhu",
    "بای ژو": "Baizhu",
    "یلان": "Yelan",
    "یائو یائو": "Yaoyao",
    "کیرارا": "Kirara",
    "سائو": "Sayu",
    "سایو": "Sayu",
    "ستوس": "Sethos",
    "دهیا": "Dehya",
    "کاوره": "Kaveh",
    "کاوه": "Kaveh",
    "شیوری": "Chiori",
    "امیلی": "Emilie",
    "ایمیلی": "Emilie",
    "زیلونن": "Xilonen",
    "گیمینگ": "Gaming",
    "لان یان": "Lan Yan",
    "میزوکی": "Mizuki",
    "ترتالیا": "Tartaglia",
    "تارتاگیا": "Tartaglia",
    "چایلد": "Tartaglia",
    "واندرر": "Wanderer",
    "اسکرموشه": "Wanderer",
    "آلبدو": "Albedo",
    "مونا": "Mona",
    "یون جین": "Yun Jin",
    "نینگ گوانگ": "Ningguang",
    "نینگوانگ": "Ningguang",
    "شینوبو": "Shinobu",
    "کوجو سارا": "Kujou Sara",
    "سارا": "Sara",
    "داهلیا": "Dahlia",
}

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_query(q):
    q = q.translate(PERSIAN_DIGITS)
    extra = []
    # longest keys first; consume matches so shorter keys don't re-match inside them
    for k in sorted(GLOSSARY, key=len, reverse=True):
        if k in q:
            extra.append(GLOSSARY[k])
            q = q.replace(k, " ")
    if extra:
        q = q + " " + " ".join(extra)
    return q


def retrieve(query, k=8):
    con = sqlite3.connect(DB)
    terms = [t for t in re.findall(r"[\w]+", query.lower()) if t not in STOP and len(t) > 1]
    if not terms:
        return []
    # naive stemming variants so 'prefarming' matches 'prefarm', 'materials' -> 'material'
    expanded = []
    for t in terms:
        variants = [t]
        for tail in STEM_TAIL:
            if t.endswith(tail) and len(t) - len(tail) >= 3:
                base = t[: len(t) - len(tail)]
                if base not in variants:
                    variants.append(base)
        expanded.extend(variants)
    expanded = list(dict.fromkeys(expanded))

    # optional semantic path (Phase 4) — feature-flagged via env, degrades to FTS-only on failure
    sem_ranks = {}
    if os.environ.get("GENSHIN_BOT_HYBRID", "0") == "1":
        try:
            import sqlite_vec  # load vec0 extension on THIS connection
            con.enable_load_extension(True)
            sqlite_vec.load(con)
            con.enable_load_extension(False)
            qv = list(_embed_model().embed([query]))[0]
            srows = con.execute(
                "SELECT chunk_id FROM vec_chunks WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (sqlite_vec.serialize_float32([float(x) for x in qv]), 20),
            ).fetchall()
            for rank, (cid,) in enumerate(srows, 1):
                sem_ranks[cid] = rank
        except Exception:
            sem_ranks = {}  # semantic path is best-effort only

    # 1) entity-anchored fetch: rows whose name is one of the terms rank first
    names = [t for t in expanded if not t.isdigit()]
    rows = []
    for nm in names:
        try:
            got = con.execute(
                "SELECT title, name, kind, header, body FROM kb WHERE kb MATCH ? AND name MATCH ? ORDER BY rank LIMIT ?",
                (match_all(expanded), nm, 6),
            ).fetchall()
            rows.extend(got)
        except sqlite3.OperationalError:
            pass

    # 1b) balanced per-entity fill: every named entity gets its core kit chunks
    for nm in names:
        # names come from the lowercased query; the KB stores mixed-case names — match case-insensitively
        try:
            got = con.execute(
                "SELECT title, name, kind, header, body FROM kb WHERE name = ? COLLATE NOCASE AND kind IN ('character','tier','beta') ORDER BY rowid LIMIT 6",
                (nm,),
            ).fetchall()
            rows[:0] = got  # core kit chunks go FIRST
        except sqlite3.OperationalError:
            pass

    # 2) global ranked fetch to fill remaining slots
    try:
        got = con.execute(
            "SELECT title, name, kind, header, body FROM kb WHERE kb MATCH ? ORDER BY rank LIMIT ?",
            (" OR ".join(expanded), k),
        ).fetchall()
        rows.extend(got)
    except sqlite3.OperationalError:
        pass

    # 2b) general-intent: pull curated knowledge chunks directly (they are universal guides;
    # FTS often drowns them under name-matched rows)
    if detect_intent(query) == "general":
        try:
            got = con.execute(
                "SELECT title, name, kind, header, body FROM kb WHERE kind='knowledge' ORDER BY rowid LIMIT 4",
            ).fetchall()
            rows.extend(got)
        except sqlite3.OperationalError:
            pass

    con.close()
    out, seen = [], set()
    # dedupe by header, but keep per-name balance: interleave so no single name hogs the slots
    # group by name preserving order
    groups = {}
    order = []
    for cid, name, kind, header, body in rows:
        if header in seen:
            continue
        seen.add(header)
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append({"id": cid, "name": name, "kind": kind, "header": header, "body": body})
    # round-robin across names, with query-intent-aware kind boost (reorder only):
    # general/why/compare questions favor knowledge+tier chunks; build questions favor
    # build/artifact/weapon chunks; kit questions favor character/beta chunks (default).
    INTENT_BOOST = {
        "general": ("knowledge",),
        "build": ("build", "artifact", "weapon"),
        "kit": ("character", "beta", "tier"),
    }
    intent = detect_intent(query)
    boosted = INTENT_BOOST[intent]

    def sort_key(chunk, original_pos):
        # stable sort: boosted kinds first (keep internal order), then original order
        is_boosted = 0 if chunk["kind"] in boosted else 1
        return (is_boosted, original_pos)

    out = []
    idx = 0
    while len(out) < k + 10 and any(groups[n][idx:] for n in order):
        batch = []
        for n in order:
            bucket = groups[n][idx:]
            if bucket:
                batch.append(bucket[0])
                if len(out) + len(batch) >= k + 10:
                    break
        # stable reorder: boosted kinds first, preserving original order inside each group
        batch.sort(key=lambda c: (0 if c["kind"] in boosted else 1))
        out.extend(batch)
        idx += 1

    # ---- Phase 4: RRF fusion with the semantic path (behind GENSHIN_BOT_HYBRID=1) ----
    if sem_ranks:
        K = 60
        fts_rank = {}
        for pos, c in enumerate(out, 1):
            fts_rank[c["id"]] = pos
        fused = {}
        for cid, fr in fts_rank.items():
            fused[cid] = 1.0 / (K + fr) + 1.0 / (K + sem_ranks[cid]) if cid in sem_ranks else 1.0 / (K + fr)
        # semantic-only hits (missed by FTS entirely) enter the candidate pool
        existing_ids = {c["id"] for c in out}
        sem_only = [cid for cid in sem_ranks if cid not in existing_ids]
        if sem_only:
            for c in _semantic_chunks(sem_only[:6]):
                c["_hop"] = True
                out.append(c)
                fused[c["id"]] = 1.0 / (K + sem_ranks[c["id"]])
        # final order: fusion score desc — but FTS rank-1..N (evidence floor) never falls off:
        # keep ALL FTS hits in the list, fusion only reorders them; sem-only extras appended after.
        fts_hits = [c for c in out if not c.get("_hop")]
        sem_hits = [c for c in out if c.get("_hop")]
        fts_hits.sort(key=lambda c: -fused.get(c["id"], 0.0))
        sem_hits.sort(key=lambda c: -fused.get(c["id"], 0.0))
        out = fts_hits[: k + 10] + sem_hits[:6]
        # dedupe preserving order
        seen_ids = set()
        deduped = []
        for c in out:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                deduped.append(c)
        out = deduped

    LAST_RETRIEVAL_STATS["sem_hits"] = len(sem_ranks)
    return out


_embed_model_instance = None


def _embed_model():
    global _embed_model_instance
    if _embed_model_instance is None:
        import sqlite_vec  # registers vec0 support
        from fastembed import TextEmbedding
        _embed_model_instance = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _embed_model_instance


def _semantic_chunks(cids):
    """Fetch full chunk rows by id for semantic-only hits."""
    if not cids:
        return []
    try:
        con = sqlite3.connect(DB)
        qs = ",".join("?" * len(cids))
        rows = con.execute(
            f"SELECT title, name, kind, header, body FROM kb WHERE title IN ({qs})", cids
        ).fetchall()
        con.close()
        by_id = {r[0]: {"id": r[0], "name": r[1], "kind": r[2], "header": r[3], "body": r[4]} for r in rows}
        return [by_id[c] for c in cids if c in by_id]
    except sqlite3.OperationalError:
        return []



# known entity names for intent detection (loaded once)
_KNOWN_NAMES = set()
try:
    with open(os.path.join(os.path.dirname(DB), "character_index.json")) as _f:
        for _v in json.load(_f).values():
            if _v.get("en"):
                _KNOWN_NAMES.add(_v["en"].lower())
    with open(os.path.join(os.path.dirname(DB), "weapon_live.json")) as _f:
        for _v in json.load(_f).values():
            if _v.get("en"):
                _KNOWN_NAMES.add(_v["en"].lower())
    # beta characters (not in live index) — cached locally to avoid network at import
    _beta_idx = os.path.join(os.path.dirname(DB), "beta_index.json")
    _beta_map = {}
    if os.path.exists(_beta_idx):
        with open(_beta_idx) as _f:
            _beta_map = json.load(_f)
    else:
        import urllib.request as _u
        with open(os.path.join(os.path.dirname(DB), "beta_new_ids.json")) as _f:
            _ids = json.load(_f)
        for _cid in _ids:
            try:
                _req = _u.Request(f"https://static.nanoka.cc/gi/7.2.50/en/character/{_cid}.json",
                                  headers={"User-Agent": "Mozilla/5.0"})
                with _u.urlopen(_req, timeout=10) as _r:
                    _nm = json.load(_r).get("name")
                    if _nm:
                        _beta_map[_cid] = _nm
                        _KNOWN_NAMES.add(_nm.lower())
            except Exception:
                pass
        with open(_beta_idx, "w") as _f:
            json.dump(_beta_map, _f)
    for _nm in _beta_map.values():
        _KNOWN_NAMES.add(_nm.lower())
except Exception:
    pass

def detect_intent(q):
    ql = q.lower()
    # multi-entity comparisons are kit questions even with 'better'/'vs' — their evidence is the kits
    entity_hits = sum(1 for nm in _KNOWN_NAMES if nm in ql)
    if entity_hits >= 2:
        return "kit"
    if any(w in ql for w in ["why", "should", "better", "decide", "prioritize", "vs",
                             "compare", "replace", "optimize", "worth"]):
        return "general"
    if any(w in ql for w in ["build", "artifact", "set", "weapon", "stats", "substat",
                             "refinement", "best", "recommend"]):
        return "build"
    return "kit"


def match_all(terms):
    return " OR ".join(terms)


_META_CACHE = None


def _prov_map():
    """chunk_id -> (source_name, content_status) from the metadata table."""
    global _META_CACHE
    if _META_CACHE is None:
        m = {}
        try:
            con = sqlite3.connect(DB)
            for cid, sname, status in con.execute(
                "SELECT chunk_id, source_name, content_status FROM chunk_meta"
            ):
                m[cid] = (sname, status)
            con.close()
        except sqlite3.OperationalError:
            pass
        _META_CACHE = m
    return _META_CACHE


def build_context(query):
    norm = normalize_query(query)
    hits = retrieve(norm)
    if not hits:
        return "", []
    prov = _prov_map()
    seen, blocks = set(), []
    for h in hits:
        if h["header"] in seen:
            continue
        seen.add(h["header"])
        sname, status = prov.get(h.get("id"), ("unknown", "unknown"))
        tag = f" [source: {sname}" + (", PROVISIONAL BETA DATA" if status == "beta" else "") + "]"
        blocks.append(f"[{h['name']} | {h['header']}{tag}]\n{h['body']}")
    ctx = "\n\n".join(blocks)
    return ctx, hits


SYSTEM = (
    "You are a Genshin Impact game-knowledge assistant. Answer STRICTLY from the provided "
    "CONTEXT, which is live game data (v{ver}). If the context does not contain the answer, "
    "say you are not sure and suggest what to check. Be concise and precise with numbers, "
    "percentages, and cooldowns. Always reply in English. Do not invent game data.\n"
    "Guidelines:\n"
    "- For prefarm/material questions, compare the ASCENSION and TALENT material lists of the "
    "characters mentioned: name every SHARED item and every DIFFERENT item explicitly.\n"
    "- For build questions ('best artifact set for X', 'best weapon for X'): the dataset has no "
    "community build recommendations; say so, but you MAY infer from the character's kit in the "
    "context (their element, scaling stat listed in their stats, and what their skills scale from) "
    "and clearly label it as inference, e.g. 'her stats scale with DEF, so sets with DEF% like ... "
    "are likely good — community guides (KeqingMains) are a better source'.\n"
    "- For weapon-fit questions ('can X use Y's weapon?', 'is Y good for X?'), evaluate in TWO "
    "layers and report both: (1) RAW STATS — base ATK and the substat are ALWAYS active on any "
    "character who can equip it; a high base ATK + CRIT DMG/CRIT Rate substat makes a weapon a "
    "viable stat-stick for DPS characters even when the passive is useless. (2) PASSIVE — check "
    "whether the passive's condition/scaling (DEF%, HP%, element-specific DMG, reaction type) "
    "matches the character's kit from the context. IMPORTANT: a passive granting only ATK%/CRIT "
    "bonuses is DEAD for a character whose kit scales with DEF or HP (ATK does not multiply "
    "DEF/HP-scaling damage) — do not call such a passive a good match for DEF/HP scalers. "
    "Base ATK itself is also worth little to a DEF/HP-scaling character — the substat (CRIT/EM) "
    "is what still works for them. Verdict format: can they equip it? what part works? what part "
    "is dead? is there a better option in the retrieved data?\n"
    "- Chunks tagged [BETA — unreleased] are datamined beta data: always mention they may change."
)


LAST_RETRIEVAL_STATS = {"direct": 0, "hop": 0, "intent": "kit"}


def _matched_glossary(q):
    """Return {persian_term: english_term} for glossary keys present in the question."""
    q = q.translate(PERSIAN_DIGITS)
    out = {}
    for k in sorted(GLOSSARY, key=len, reverse=True):
        if k in q:
            out[k] = GLOSSARY[k]
    return out


def answer(question, api_key=None, base_url=None, model=None):
    api_key = api_key or API_KEY
    base_url = base_url or BASE_URL
    model = model or MODEL
    meta = json.load(open(META))
    ver = meta["live"]

    ctx, hits = build_context(question)
    if not ctx:
        LAST_RETRIEVAL_STATS["answerability"] = "out_of_scope"
        return "Nothing relevant found in my database. Try the exact character/weapon name?", []

    glossary_hits = _matched_glossary(question)
    if glossary_hits:
        note = "[Persian terms in the question translated: " + \
               ", ".join(f"'{k}' means '{v}'" for k, v in glossary_hits.items()) + \
               ". Interpret the question accordingly.]\n"
    else:
        note = ""

    # dynamic retrieval: guarantee coverage of every distinct retrieved entity (name-level)
    primary = list(hits)
    mentioned = []
    for h in primary:
        if h["name"] not in mentioned:
            mentioned.append(h["name"])
    # ignore id-like names (e.g. beta artifacts named '15001') — they pollute expansion
    mentioned = [m for m in mentioned if not m.isdigit()]
    extra = []
    for nm in mentioned[:3]:
        for h in retrieve(nm, k=6):
            if h["name"] == nm and all(h["header"] != e["header"] for e in extra):
                extra.append(h)
    merged = primary + [e for e in extra if all(e["header"] != p["header"] for p in primary)]
    # second hop: build chunks mention concrete weapon/set names — pull their full data too
    # expansion budget: max 6 hop chunks per query; skip entities already expanded
    HOP_BUDGET = 6
    hop_added = 0
    expanded_names = set()
    build_chunks = [h for h in merged if h["kind"] == "build"]
    con = sqlite3.connect(DB)
    for bc in build_chunks[:6]:
        if hop_added >= HOP_BUDGET:
            break
        # multi-word weapon names split by the regex; try sliding 1-4 word joins
        words = re.findall(r"[A-Za-z'’\-]+", bc["body"])
        candidates = set()
        for i in range(len(words)):
            for span in (4, 3, 2, 1):
                if i + span <= len(words):
                    cand = " ".join(words[i:i + span])
                    if cand[0].isupper():
                        candidates.add(cand)
        for nm in list(candidates)[:60]:
            if hop_added >= HOP_BUDGET:
                break
            if nm in mentioned or nm in expanded_names or nm in (
                "The", "Game8", "Best", "Recommended", "Signature", "Weapon", "Weapons"
            ):
                continue
            try:
                got = con.execute(
                    "SELECT title, name, kind, header, body FROM kb WHERE name = ? COLLATE NOCASE AND kind='weapon' AND body LIKE '%Refinement:%' LIMIT 1",
                    (nm,),
                ).fetchall() or con.execute(
                    "SELECT title, name, kind, header, body FROM kb WHERE name = ? COLLATE NOCASE AND kind='weapon' LIMIT 1",
                    (nm,),
                ).fetchall() or con.execute(
                    "SELECT title, name, kind, header, body FROM kb WHERE name = ? COLLATE NOCASE AND kind = 'artifact' LIMIT 1",
                    (nm,),
                ).fetchall()
                for g in got:
                    if all(g[3] != p["header"] for p in merged):
                        merged.append({"id": g[0], "name": g[1], "kind": g[2], "header": g[3], "body": g[4], "_hop": True})
                        hop_added += 1
                        expanded_names.add(g[1])
            except sqlite3.OperationalError:
                pass
    con.close()
    # drop id-named artifact/weapon rows when real-name rows exist for the same query
    if mentioned:
        merged = [h for h in merged if not h["name"].isdigit() or h["kind"] not in ("artifact", "weapon")]
    # cap total context size — but second-hop weapon/artifact chunks always make the cut
    hop = [h for h in merged if h.get("_hop")]
    base = [h for h in merged if not h.get("_hop")]
    seen2, blocks = set(), []
    for h in (base[:14] + hop + base[14:24]):
        if h["header"] in seen2:
            continue
        seen2.add(h["header"])
        blocks.append(f"[{h['name']} | {h['header']}]\n{h['body']}")
    ctx = "\n\n".join(blocks)
    hits = base[:14] + hop + base[14:24]

    LAST_RETRIEVAL_STATS.update({
        "direct": sum(1 for h in hits if not h.get("_hop")),
        "hop": sum(1 for h in hits if h.get("_hop")),
        "intent": detect_intent(normalize_query(question)),
    })

    sys = SYSTEM.format(ver=ver)
    user = f"CONTEXT:\n{ctx}\n\n---\n{note}QUESTION: {question}"
    r = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        timeout=90,
    )
    r.raise_for_status()
    txt = r.json()["choices"][0]["message"]["content"] or ""
    txt = sanitize_answer(txt)
    LAST_RETRIEVAL_STATS["answerability"] = classify_answerability(question, hits)
    return txt, hits


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Ayaka burst damage"
    key = os.environ.get("GENSHIN_BOT_LLM_KEY", "")
    if not key:
        # fall back to reading the hermes .env key without printing it
        for line in open(_os.path.expanduser("~/genshin-bot/bot.env")):
            if line.startswith("GENSHIN_BOT_LLM_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    txt, hits = answer(q, api_key=key)
    print("RETRIEVED:", [h["name"] for h in hits])
    print("---")
    print(txt)


def classify_answerability(question, hits):
    """Rule-based answerability classification (Phase 6, zero extra tokens).
    Returns one of: answerable | partially_answerable | insufficient_context | out_of_scope"""
    if not hits:
        return "out_of_scope"
    ql = question.lower()
    mentioned = [nm for nm in _KNOWN_NAMES if nm in ql]
    hit_names = {h["name"].lower() for h in hits}
    if mentioned and not any(any(m in hn or hn in m for hn in hit_names) for m in mentioned):
        # user named specific entities but none of their chunks came back
        return "insufficient_context"
    # beta-only coverage (no live character kit for the asked entity) = partial
    for m in mentioned:
        ent_chunks = [h for h in hits if m in h["name"].lower() or h["name"].lower() in m]
        if ent_chunks and all(h["kind"] != "character" for h in ent_chunks):
            has_beta = any(h["kind"] == "beta" for h in ent_chunks)
            if has_beta:
                return "partially_answerable"
    return "answerable"


def sanitize_answer(text):
    """Defensive: strip any fake source citations the model may have invented in its text.
    Real source footers are added by main.py from actual retrieved chunks."""
    import re as _re
    return _re.sub(r"\[source:[^\]]*\]", "", text)
