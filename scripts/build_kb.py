#!/usr/bin/env python3
"""Build a searchable knowledge base (SQLite FTS5) from downloaded nanoka data."""
import json
import os
import re
import sqlite3
import html as htmllib

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
DB = os.path.abspath(os.path.join(HERE, "..", "data", "kb.sqlite"))

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t]+")


def clean(text):
    """Strip HoYoverse color tags and collapse whitespace; keep \n as separator."""
    if not text:
        return ""
    t = text.replace("\\n", "\n")
    t = TAG.sub(" ", t)
    t = htmllib.unescape(t)
    t = WS.sub(" ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    return t.strip()


def rows_from_kit(cid, kit, idx_entry):
    rows = []
    info = kit.get("chara_info") or {}
    name = kit.get("name") or idx_entry.get("en", cid)

    # 1. overview chunk
    title = info.get("title", "")
    region = info.get("region", "")
    vision = kit.get("element", "")
    wep = {"WEAPON_SWORD_ONE_HAND": "Sword", "WEAPON_CATALYST": "Catalyst",
           "WEAPON_CLAYMORE": "Claymore", "WEAPON_BOW": "Bow",
           "WEAPON_POLE": "Polearm"}.get(kit.get("weapon"), kit.get("weapon", ""))
    rar = {"QUALITY_ORANGE": "5-star", "QUALITY_PURPLE": "4-star"}.get(kit.get("rarity"), kit.get("rarity", ""))
    release = info.get("release_date", "")
    desc = clean(kit.get("desc", ""))
    detail = clean(info.get("detail", ""))
    over = (f"{name} ({rar} {vision} {wep}) — {title}. Region: {region}. "
            f"Released {release}.\nDescription: {desc}\n{detail[:1200]}")
    rows.append((f"char:{cid}:overview", name, "character", f"{name} | {title} | {vision} | {wep} | {region} | overview", over))

    # 2. one chunk per skill — extract the skill-type label (Normal Attack / Elemental Skill / Burst...)
    KNOWN_TYPES = ("normal attack", "charged attack", "plunging attack", "elemental skill",
                   "alternate sprint", "burst", "skill")
    n_sk = len(kit.get("skills", []))
    for i, sk in enumerate(kit.get("skills", [])):
        raw = sk.get("desc", "")
        stype = ""
        for m in re.finditer(r"<color=#FFD780FF>([^<]+)</color>", raw):
            cand = m.group(1).strip().lower()
            if any(cand.startswith(k) for k in KNOWN_TYPES):
                stype = m.group(1).strip()
                break
        if not stype:
            # positional fallback: 0=NA, 1=ES, last=Burst (HoYoverse convention)
            if i == 0:
                stype = "Normal Attack"
            elif i == 1:
                stype = "Elemental Skill"
            elif i == n_sk - 1:
                stype = "Burst"
            else:
                stype = "Skill"
        clean_desc = clean(raw)
        body = f"{sk.get('name','')} ({stype})\n{clean_desc}"
        header = f"{name} | {sk.get('name','')} | {stype} | {vision} | skill talent burst"
        rows.append((f"char:{cid}:skill:{i}", name, "character", header, body[:2500]))

    # 3. passives
    for i, p in enumerate(kit.get("passives", [])):
        body = f"{p.get('name','')} (passive)\n{clean(p.get('desc',''))}"
        rows.append((f"char:{cid}:passive:{i}", name, "character",
                     f"{name} | {p.get('name','')} | passive talent", body[:1500]))

    #  ascension + talent materials summary
    mat = kit.get("materials") or {}
    asc = mat.get("ascensions") or []
    if asc:
        lines = [f"{name} ASCENSION materials (to level 90):"]
        totals = {}
        for step in asc:
            lv = step.get("level", f"tier {len(lines)}")
            for m in step.get("mats", []):
                mname, cnt = m.get("name", "?"), m.get("count", 0)
                totals[mname] = totals.get(mname, 0) + cnt
            part = ", ".join(f"{m.get('name')} x{m.get('count')}" for m in step.get("mats", []))
            if part:
                lines.append(f"  - {part}")
        if totals:
            lines.append("TOTALS: " + ", ".join(f"{k} x{v}" for k, v in totals.items()))
        body = "\n".join(lines)[:2200]

        # talent books (unique across all talent levels) + weekly boss
        tal = mat.get("talents")
        book_names, weekly = [], []
        if isinstance(tal, list):
            for level in tal:
                if isinstance(level, list):
                    for step in level:
                        for m in step.get("mats", []):
                            if m.get("name") and m["name"] not in book_names:
                                book_names.append(m["name"])
        levelup = kit.get("skill_level_up") or {}
        wk = levelup.get("cost_items") if isinstance(levelup, dict) else None
        body += "\nTalent books: " + (", ".join(book_names) if book_names else "unknown")
        header = f"{name} | ascension materials | talent books | level up items | prefarm"
        rows.append((f"char:{cid}:materials", name, "character", header, body))

        # weekly/talent weekly boss material if present in talent mats ranks
        wknames = [n for n in book_names if "Guide" not in n and "Teachings" not in n and "Philosophies" not in n and "Vayuda" not in n.lower() or True]
        if isinstance(tal, list) and tal:
            deepest = tal[-1]
            if isinstance(deepest, list) and deepest:
                dstep = deepest[-1]
                wk = [m.get("name") for m in dstep.get("mats", []) if isinstance(m, dict) and m.get("rank", 0) >= 4]
                if wk:
                    body2 = f"{name} talent max-level materials (likely weekly/late-tier): {', '.join(wk)}"
                    rows.append((f"char:{cid}:talent_weekly", name, "character",
                                 f"{name} | talent materials | weekly boss | late tier", body2))

    #  constellations
    for i, c in enumerate(kit.get("constellations", [])):
        cn = f"C{i+1}"
        body = f"{cn} — {c.get('name','')}\n{clean(c.get('desc',''))}"
        rows.append((f"char:{cid}:const:{i}", name, "character",
                     f"{name} | {cn} | {c.get('name','')} | constellation", body[:1200]))

    #  base stats
    sm = kit.get("stats_modifier") or {}
    asc_stat = sm.get("ascension")
    if isinstance(asc_stat, dict):
        stat_name = str(asc_stat.get("stat", ""))
    elif isinstance(asc_stat, list):
        stat_name = ", ".join(str(x) for x in asc_stat)
    else:
        stat_name = ""
    rows.append((f"char:{cid}:stats", name, "character",
                 f"{name} | base stats | ascension stat {stat_name}",
                 f"{name} base stats: HP {kit.get('base_hp')}, ATK {kit.get('base_atk')}, DEF {kit.get('base_def')}, "
                 f"CR {kit.get('crit_rate')}, CD {kit.get('crit_dmg')}, EM {kit.get('elemental_mastery')}. "
                 f"Ascension stat: {stat_name}"))
    return rows


def rows_from_index(idx, kind):
    rows = []
    for oid, e in idx.items():
        name = e.get("en", oid)
        bits = [name]
        for k in ("en", "ko", "zh", "ja", "desc", "rank", "weapon", "element", "type"):
            if k in e:
                bits.append(str(e[k]))
        body = json.dumps(e, ensure_ascii=False)
        rows.append((f"{kind}:{oid}", name, kind, " | ".join(bits), body[:2000]))
    return rows



# ---- provenance metadata (Phase 3) ----
from datetime import datetime as _dt
import hashlib as _hl

META_TABLE = """CREATE TABLE IF NOT EXISTS chunk_meta (
    chunk_id TEXT PRIMARY KEY,
    source_name TEXT, source_url TEXT, source_type TEXT,
    game_version TEXT, content_status TEXT, language TEXT,
    updated_at TEXT, content_hash TEXT)"""

_now = _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# source registry per chunk-id prefix
_SOURCES = {
    "char:":    ("nanoka.cc", "https://gi.nanoka.cc", "game_data", "current", "en"),
    "beta:":    ("nanoka.cc", "https://gi.nanoka.cc", "game_data", "beta", "en"),
    "weapon:full:": ("nanoka.cc", "https://gi.nanoka.cc", "game_data", "current", "en"),
    "weapon:":  ("nanoka.cc", "https://gi.nanoka.cc", "game_data", "current", "en"),
    "artifact:":("nanoka.cc", "https://gi.nanoka.cc", "game_data", "current", "en"),
    "g8:char:": ("Game8", "https://game8.co/games/Genshin-Impact", "community_guide", "current", "en"),
    "g8:weapon:": ("Game8", "https://game8.co/games/Genshin-Impact", "community_guide", "current", "en"),
    "g8:artifact:": ("Game8", "https://game8.co/games/Genshin-Impact/archives/297493", "community_guide", "current", "en"),
    "g8:build:": ("Game8", "https://game8.co/games/Genshin-Impact", "community_guide", "current", "en"),
    "kqm:":     ("KeqingMains", "https://keqingmains.com", "community_guide", "current", "en"),
    "kn:":      ("curated", "", "curated_knowledge", "current", "en"),
}


def provenance_for(chunk_id, game_version):
    for prefix, (sname, surl, stype, status, lang) in _SOURCES.items():
        if chunk_id.startswith(prefix) or chunk_id.startswith("beta:" + prefix):
            if chunk_id.startswith("beta:"):
                status = "beta"
            return (sname, surl, stype, game_version if status != "beta" else "beta", status, lang)
    return ("unknown", "", "unknown", "unknown", "unknown", "en")


def add(con, row, game_version):
    title, name, kind, header, body = row
    if not body or len(body.strip()) < 30:  # skip empty/near-empty chunks (data bug upstream)
        return False
    con.execute("INSERT INTO kb VALUES (?,?,?,?,?)", row)
    sname, surl, stype, ver, status, lang = provenance_for(title, game_version)
    con.execute(
        "INSERT OR REPLACE INTO chunk_meta VALUES (?,?,?,?,?,?,?,?,?)",
        (title, sname, surl, stype, ver, status, lang, _now, _hl.sha256(body.encode()).hexdigest()[:16]),
    )
    return True

def main():
    manifest = json.load(open(os.path.join(DATA, "manifest.json")))
    live = manifest["live"]

    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    con.execute("CREATE VIRTUAL TABLE kb USING fts5(title, name, kind, header, body, tokenize='unicode61 remove_diacritics 2')")
    con.execute(META_TABLE)

    total = 0
    # character kits (live)
    kits_dir = os.path.join(DATA, "kits", live, "en")
    for fn in sorted(os.listdir(kits_dir)):
        cid = fn[:-5]
        kit = json.load(open(os.path.join(kits_dir, fn)))
        idx_entry = {}
        idx_path = os.path.join(DATA, "character_index.json")
        if os.path.exists(idx_path):
            idx_entry = json.load(open(idx_path)).get(cid, {})
        for r in rows_from_kit(cid, kit, idx_entry):
            add(con, r, live)
            total += 1

    # beta-only kits (unreleased characters like Danica) — tagged BETA
    beta_ids_path = os.path.join(DATA, "beta_new_ids.json")
    if os.path.exists(beta_ids_path):
        beta_ids = json.load(open(beta_ids_path))
        kdir = os.path.join(DATA, "kits")
        for cid in beta_ids:
            # find the kit under any beta version dir
            for ver in sorted(os.listdir(kdir), reverse=True):
                p = os.path.join(kdir, ver, "en", f"{cid}.json")
                if os.path.exists(p):
                    ver_used = ver
                    kit = json.load(open(p))
                    for r in rows_from_kit(cid, kit, {}):
                        rid = list(r)
                        rid[0] = f"beta:{rid[0]}"
                        rid[2] = "beta"
                        rid[3] = "[BETA — unreleased] " + rid[3]
                        rid[4] = "[BETA — unreleased, subject to change] " + rid[4]
                        add(con, rid, ver_used)
                        total += 1
                    break

    # weapon + artifact + monster indexes
    for kind, fn in [("weapon", "weapon_live.json"), ("artifact", "artifact_live.json")]:
        p = os.path.join(DATA, fn)
        if os.path.exists(p):
            for r in rows_from_index(json.load(open(p)), kind):
                add(con, r, live)
                total += 1

    # ---- Game8 build metadata ----
    g8 = os.path.join(DATA, "game8")

    # character tier list (role -> tier per character)
    p = os.path.join(g8, "char_tiers.json")
    if os.path.exists(p):
        for cname, roles in json.load(open(p)).items():
            parts = ", ".join(f"{role}: {tier}" for role, tier in roles.items())
            body = (f"{cname} Game8 tier ratings (v{live} meta, community opinion, not official): "
                    f"{parts}.")
            add(con, (f"g8:char:{cname}", cname, "tier",
                      f"{cname} | tier list | {parts} | game8 meta", body[:1000]), live)
            total += 1

    # weapon tier list
    p = os.path.join(g8, "weapon_tiers.json")
    if os.path.exists(p):
        for wname, entries in json.load(open(p)).items():
            parts = ", ".join(f"{e['role']}: {e['tier']}" for e in entries)
            body = (f"{wname} Game8 weapon tier ratings (community opinion, not official): {parts}.")
            add(con, (f"g8:weapon:{wname}", wname, "tier",
                      f"{wname} | weapon tier list | {parts} | game8 meta", body[:1000]), live)
            total += 1

    # artifact sets + bonuses
    p = os.path.join(g8, "artifact_sets.json")
    if os.path.exists(p):
        for e in json.load(open(p)):
            nm, bonus = e["name"], e["bonus"]
            add(con, (f"g8:artifact:{nm}", nm, "artifact",
                      f"{nm} | artifact set | set bonus | {bonus[:80]}",
                      f"{nm} artifact set bonus: {bonus}"), live)
            total += 1

    # per-character build recommendations (signature weapon, best weapons/sets)
    p = os.path.join(g8, "char_builds.json")
    if os.path.exists(p):
        for cname, b in json.load(open(p)).items():
            if b.get("signature"):
                body = (f"{cname}'s signature weapon is {b['signature']}. "
                        f"Recommended weapons: {', '.join(b.get('best_weapons', [])[:6])}. "
                        f"(Game8 build guide, community recommendation.)")
                add(con, (f"g8:build:{cname}:weapons", cname, "build",
                          f"{cname} | signature weapon | best weapons | {b['signature']} | game8 build",
                          body[:1200]), live)
                total += 1
            if b.get("best_artifacts"):
                body = (f"{cname} recommended artifact sets (Game8): "
                        f"{', '.join(b['best_artifacts'][:5])}. {b.get('best_artifacts_text', '')[:700]}")
                add(con, (f"g8:build:{cname}:artifacts", cname, "build",
                          f"{cname} | best artifact sets | build | game8",
                          body[:1200]), live)
                total += 1

    # ---- Full weapon details (base ATK, substat, passive with R-values) ----
    PROP_NAMES = {
        "FIGHT_PROP_BASE_ATTACK": "ATK", "FIGHT_PROP_HP": "HP", "FIGHT_PROP_DEFENSE": "DEF",
        "FIGHT_PROP_CHARGE_EFFICIENCY": "Energy Recharge", "FIGHT_PROP_CRITICAL": "CRIT Rate",
        "FIGHT_PROP_CRITICAL_HURT": "CRIT DMG", "FIGHT_PROP_ELEMENT_MASTERY": "Elemental Mastery",
        "FIGHT_PROP_HEAL_ADD": "Healing Bonus", "FIGHT_PROP_PHYSICAL_ADD": "Physical DMG Bonus",
        "FIGHT_PROP_FIRE_ADD_HURT": "Pyro DMG Bonus", "FIGHT_PROP_WATER_ADD_HURT": "Hydro DMG Bonus",
        "FIGHT_PROP_GRASS_ADD_HURT": "Dendro DMG Bonus", "FIGHT_PROP_ELEC_ADD_HURT": "Electro DMG Bonus",
        "FIGHT_PROP_WIND_ADD_HURT": "Anemo DMG Bonus", "FIGHT_PROP_ICE_ADD_HURT": "Cryo DMG Bonus",
        "FIGHT_PROP_ROCK_ADD_HURT": "Geo DMG Bonus",
    }
    wdir = os.path.join(DATA, "weapons", live)
    if os.path.isdir(wdir):
        widx_path = os.path.join(DATA, "weapon_live.json")
        wmeta = json.load(open(widx_path)) if os.path.exists(widx_path) else {}
        for fn in sorted(os.listdir(wdir)):
            wid = fn[:-5]
            w = json.load(open(os.path.join(wdir, fn)))
            meta = wmeta.get(wid, {})
            wname = w.get("name") or meta.get("en", wid)
            rar = {5: "5-star", 4: "4-star", 3: "3-star", 2: "2-star", 1: "1-star"}.get(w.get("rarity"), w.get("rarity"))
            wtype = {"WEAPON_SWORD_ONE_HAND": "Sword", "WEAPON_CATALYST": "Catalyst",
                     "WEAPON_CLAYMORE": "Claymore", "WEAPON_BOW": "Bow",
                     "WEAPON_POLE": "Polearm"}.get(w.get("weapon_type"), w.get("weapon_type", ""))
            # Base ATK: the index 'atk' field IS the canonical in-game lvl-90 ATK
            # (verified: Engulfing 608, Beyond the Chrysalis 674 — matches game UI)
            atk_max = meta.get("atk")
            # Substat at lvl90: stats_modifier.<prop>.base x levels["90"] gives the exact game value
            # (verified: ER 55.1% for Engulfing, CD 44.1% for Beyond the Chrysalis)
            sm = w.get("stats_modifier") or {}
            sub_txt = ""
            for prop_key, prop_data in sm.items():
                if prop_key == "atk" or not isinstance(prop_data, dict):
                    continue
                label = PROP_NAMES.get(prop_key.upper(), prop_key)
                try:
                    val = prop_data.get("base", 0) * float(prop_data.get("levels", {}).get("90", prop_data.get("base", 0)))
                except Exception:
                    val = prop_data.get("base", 0)
                if val:
                    sub_txt = f"{label} {val*100:.1f}%" if val < 1.5 else f"{label} {val:.0f}"
            ref = w.get("refinement") or {}
            ref_parts = []
            for r in ["1", "5"]:
                if r in ref:
                    d = clean(ref[r].get("desc", ""))
                    ref_parts.append(f"R{r}: {d}")
            desc = clean(w.get("desc", ""))
            body = (f"{wname} — {rar} {wtype}. "
                    + (f"Base ATK {atk_max:.0f} at level 90." if atk_max else "")
                    + (f" Substat: {sub_txt}." if sub_txt else "")
                    + (f" Refinement: {' | '.join(ref_parts)}" if ref_parts else "")
                    + (f"\n{desc}" if desc else ""))
            add(con, (f"weapon:full:{wid}", wname, "weapon",
                      f"{wname} | {rar} {wtype} | base ATK | substat {sub_txt} | refinement | stats",
                      body[:1800]), live)
            total += 1

    # ---- KQM character guides (deep theorycrafting) ----
    kqm_dir = os.path.join(DATA, "kqm")
    if os.path.isdir(kqm_dir):
        for fn in sorted(os.listdir(kqm_dir)):
            if not fn.endswith(".json"):
                continue
            g = json.load(open(os.path.join(kqm_dir, fn)))
            title = g.get("title", fn[:-5])
            slug = fn[:-5]
            for j, ch in enumerate(g.get("chunks", [])):
                head = ch.get("heading", "")
                text = ch.get("text", "")
                body = f"{title} — {head} (KeqingMains guide, community theorycrafting)\n{text}"
                add(con, (f"kqm:{slug}:{j}", title, "kqm",
                          f"KQM {title} | {head} | guide combos artifacts teams rotation",
                          body[:2400]), live)
                total += 1

    # ---- Curated general knowledge (build frameworks) ----
    kn_path = os.path.join(DATA, "knowledge")
    if os.path.isdir(kn_path):
        for fn in sorted(os.listdir(kn_path)):
            if not fn.endswith(".json"):
                continue
            kn = json.load(open(os.path.join(kn_path, fn)))
            for j, ch in enumerate(kn.get("chunks", [])):
                add(con, (f"kn:{fn[:-5]}:{j}", "General Building Knowledge", "knowledge",
                          f"general building guide | {ch.get('heading','')} | artifact replacement | stats priority",
                          f"{ch.get('heading','')}\n{ch.get('text','')}"[:2400]), live)
                total += 1

    con.commit()

    # ---- Phase 3.4: ingestion quality checks ----
    issues = {}
    issues["empty_bodies"] = con.execute("SELECT count(*) FROM kb WHERE length(body) < 40").fetchone()[0]
    issues["duplicate_bodies"] = con.execute(
        "SELECT count(*) FROM (SELECT body, count(*) c FROM kb GROUP BY body HAVING c > 1)").fetchone()[0]
    issues["missing_meta"] = con.execute(
        "SELECT count(*) FROM kb WHERE title NOT IN (SELECT chunk_id FROM chunk_meta)").fetchone()[0]
    issues["beta_without_marker"] = con.execute(
        "SELECT count(*) FROM chunk_meta WHERE content_status='beta' AND chunk_id NOT IN "
        "(SELECT title FROM kb WHERE header LIKE '[BETA%')").fetchone()[0]
    n_meta = con.execute("SELECT count(*) FROM chunk_meta").fetchone()[0]

    n = con.execute("SELECT count(*) FROM kb").fetchone()[0]
    print(f"kb.sqlite: {n} chunks (wrote {total}) | meta: {n_meta}")
    print("quality:", issues)

    # persist a data-quality report
    dq = {"generated_at": _now, "chunks": n, "meta_rows": n_meta, **issues}
    json.dump(dq, open(os.path.join(DATA, "data_quality.json"), "w"), indent=1)
    con.close()


if __name__ == "__main__":
    main()
