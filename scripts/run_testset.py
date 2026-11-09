#!/usr/bin/env python3
"""Run the 40-question Genshin RAG test set against the bot engine and score with an LLM judge.
Output: data/test_results.jsonl"""
import json
import os
import re
import sys
import time
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bot"))
import rag  # noqa: E402

OUT = os.path.abspath(os.path.join(HERE, "..", "data", "test_results.jsonl"))
KEY = ""
for line in open(os.path.expanduser("~/genshin-bot/bot.env")):
    if line.startswith("GENSHIN_BOT_LLM_KEY="):
        KEY = line.split("=", 1)[1].strip()

TESTS = [
    ("Q1", "What is the best Artifact set for a Main DPS Hu Tao?",
     "4pc Crimson Witch of Flames (traditional/strong) or 4pc Shimenawa's Reminiscence (competitive); depends on reactions/charged attacks/energy"),
    ("Q2", "Which main stats should I use on Hu Tao's Sands, Goblet, and Circlet?",
     "HP% or EM Sands, Pyro DMG Goblet, CRIT Rate/DMG Circlet; Sands depends on team/weapon/EM"),
    ("Q3", "Is Staff of Homa better than Dragon's Bane for Hu Tao?",
     "Homa generally strongest (CRIT DMG, HP bonus, ATK scaling); Dragon's Bane competitive in Vaporize (EM + dmg vs Hydro/Pyro-affected)"),
    ("Q4", "What is the recommended Artifact set for a support Bennett?",
     "4pc Noblesse Oblige: boosts Burst dmg + team ATK buff; his buff scales with Base ATK"),
    ("Q5", "Which stats should I prioritize when building a shield-focused Zhongli?",
     "HP% primary (Sands/Goblet/Circlet HP%); shield strength also depends on talent level"),
    ("Q6", "What is the best Artifact set for a reaction-focused Kuki Shinobu in Hyperbloom?",
     "4pc Flower of Paradise Lost or 4pc Gilded Dreams; prioritize EM (Hyperbloom scales with level+EM)"),
    ("Q7", "Should I build ATK or Elemental Mastery on a Hyperbloom Raiden Shogun?",
     "EM preferred for Hyperbloom trigger; damage based on level+EM not ATK/CRIT"),
    ("Q8", "What is the recommended weapon and Artifact set for a support Xingqiu?",
     "Sacrificial Sword (ER + skill usage); 4pc Emblem of Severed Fate (Burst dmg from ER)"),
    ("Q9", "Which stats should I prioritize when building Neuvillette?",
     "HP%, Hydro DMG, CRIT; Charged Attack scales with HP — ATK not useful"),
    ("Q10", "What is the recommended Artifact set for a Freeze support Shenhe?",
     "4pc Noblesse Oblige strong; her buffing scales with ATK; ATK% mains + ER"),
    ("Q11", "Is Durin a good teammate for Hu Tao?",
     "Needs kit-based evaluation: Pyro application/off-field/buffs without breaking Vaporize; should NOT assume Pyro+Pyro = synergy"),
    ("Q12", "Is Xingqiu or Yelan better for Hu Tao?",
     "Both excellent: Xingqiu = Hydro application + defensive; Yelan = off-field dmg + dmg bonus; depends on needs"),
    ("Q13", "Can Furina work well with Hu Tao without a dedicated healer?",
     "Can work, but Fanfare/HP-drain means team-wide healing helps; Hu Tao self-heal may not suffice"),
    ("Q14", "Why is Kazuha considered a strong support for elemental DPS characters?",
     "CC + Elemental DMG Bonus passive + 4pc VV RES shred; depends on swirling the element"),
    ("Q15", "Is Nahida a good teammate for Alhaitham?",
     "Yes: Dendro application, Dendro DMG support, EM buffs for Spread teams"),
    ("Q16", "Can Raiden Shogun and Xiangling work together in the same team?",
     "Yes — Raiden National (with Xingqiu + Bennett): energy support + damage + reactions"),
    ("Q17", "Is Zhongli a good support for Xiao?",
     "Yes: strong shield, interruption resistance, RES shred — great for plunge DPS"),
    ("Q18", "Why is Fischl considered a strong off-field Electro DPS?",
     "Oz consistent off-field Electro; A4 adds damage on Electro reactions; great in Aggravate"),
    ("Q19", "Is Bennett a good teammate for Neuvillette?",
     "Generally no: Neuvillette scales with HP, Bennett's ATK buff doesn't help his damage; healing still useful"),
    ("Q20", "Why is a Dendro character necessary in a standard Hyperbloom team?",
     "Dendro+Hydro = Bloom cores; Electro on cores = Hyperbloom; without Dendro no cores"),
    ("Q21", "Who is a better Hyperbloom trigger, Kuki Shinobu or Fischl?",
     "Kuki: skill hits cores consistently + healing; Fischl targeting less reliable"),
    ("Q22", "Which is better for Alhaitham, 4-piece Gilded Dreams or 4-piece Deepwood Memories?",
     "Gilded = personal dmg; Deepwood = team Dendro RES shred; if teammate has Deepwood, Gilded preferred"),
    ("Q23", "Should I use an Elemental Mastery or ATK% Sands on Aggravate Keqing?",
     "Both viable; ATK% often competitive; EM more valuable in Aggravate; depends on full build"),
    ("Q24", "Is 4-piece Emblem of Severed Fate better than 2-piece Hydro DMG + 2-piece ATK for Yelan?",
     "4pc Emblem generally strong: Burst dmg scales with ER + rotation comfort"),
    ("Q25", "Which is better for a DPS character, a 20% ATK bonus or a 15% Elemental DMG Bonus?",
     "No universal answer; depends on scaling/multipliers/team — needs calc"),
    ("Q26", "Why might a character with a lower CRIT ratio deal more damage than one with a higher CRIT ratio?",
     "Total dmg depends on base stats, scaling, dmg bonus, reactions, talents, RES, buffs, uptime"),
    ("Q27", "Should I prioritize CRIT Rate or CRIT DMG when optimizing a DPS build?",
     "Both matter; balanced ~1:2 ratio; optimum depends on character/buffs"),
    ("Q28", "Is a 5-star weapon always better than a 4-star weapon for a character?",
     "No: 4-star passives/stats can synergize better; depends on role/team/refinement"),
    ("Q29", "Why can a character's best Artifact set change depending on the team?",
     "Set value depends on role, dmg distribution, reactions, team buffs, overlap with teammates"),
    ("Q30", "How should I decide whether to replace a character's current Artifact with a new one?",
     "Compare stats/sets/total dmg contribution, not single CRIT substats; consider ER/EM/team needs"),
    ("Q31", "I want to build a Hu Tao, Xingqiu, Yelan, and Zhongli team. Which Artifact sets and stats should I prioritize for each character?",
     "Hu Tao: CWoF/Shim + HP/EM sands, Pyro goblet, CRIT circlet; XQ: Emblem+ER; Yelan: Emblem+HP/Hydro/CRIT; Zhongli: Tenacity/HP"),
    ("Q32", "I have Raiden Shogun, Xiangling, Xingqiu, and Bennett. Explain how their roles, reactions, and Artifact sets work together.",
     "Raiden National: XL+XQ off-field Vaporize; Raiden energy+damage; Bennett heal+ATK; Emblem for Raiden/XL/XQ; Noblesse Bennett"),
    ("Q33", "I want to build a Hyperbloom team with Nahida, Xingqiu, and Kuki Shinobu. What should the fourth character do, and how should I build the first three?",
     "4th: Hydro/Dendro application, buffs, CC or defense; Nahida Dendro+EM; XQ ER+off-field; Kuki EM+level"),
    ("Q34", "My Neuvillette deals low damage despite having good CRIT stats. What should I check first?",
     "Check HP, Hydro DMG, talent level, weapon, team reactions for his passive; ATK build inefficient"),
    ("Q35", "I am building an Aggravate team with Keqing, Fischl, Nahida, and Kazuha. Explain the synergy and recommend the main Artifact sets.",
     "Nahida Dendro app; Keqing+Fischl Electro; Kazuha CC+EM buff+VV shred; Keqing Thundering Fury; Fischl Golden Troupe; Nahida Deepwood; Kazuha VV"),
    ("Q36", "What is the exact DPS increase of Hu Tao when using Staff of Homa instead of Dragon's Bane at R1?",
     "Cannot determine exactly — needs full build/team/enemy/rotation; requires damage calc"),
    ("Q37", "What is the best Artifact set for a character that does not exist in your knowledge base?",
     "Should say it lacks info about this character; ask for name/kit or updated database — MUST NOT hallucinate"),
    ("Q38", "Does Hu Tao's Elemental Skill increase her Elemental Mastery?",
     "No: converts ATK based on Max HP + Pyro infusion; does not increase EM directly"),
    ("Q39", "What is the exact damage multiplier of a character's Elemental Burst at Talent Level 13?",
     "Depends on the character — needs the name; without it cannot answer"),
    ("Q40", "Is this Artifact better than my current one?",
     "Needs to see both artifacts + character; compare mains/subs/set/requirements"),
]

JUDGE_PROMPT = """You are an impartial evaluator for a Genshin Impact RAG assistant.
Score the ASSISTANT ANSWER against the EXPECTED ANSWER on 4 metrics (1-5 each):
- retrieval: did the retrieved context support answering? (proxy: does the answer use specific, correct game facts)
- faithfulness: is every claim supported/grounded, no fabricated game data?
- relevance: does it directly answer the question asked?
- completeness: does it cover the key points in the expected answer?
Expected answers are references, not verbatim requirements; different phrasing is fine.
Reply ONLY with JSON: {{"retrieval": n, "faithfulness": n, "relevance": n, "completeness": n, "note": "one short sentence"}}

QUESTION: {q}
EXPECTED (reference): {exp}
ASSISTANT ANSWER: {ans}"""


def judge(q, exp, ans):
    try:
        r = httpx.post(
            "https://api.avalai.ir/v1/chat/completions",
            headers={"Authorization": f"Bearer {KEY}"},
            json={
                "model": "glm-5.3-flash",
                "messages": [{"role": "user", "content": JUDGE_PROMPT.format(q=q, exp=exp, ans=ans[:3500])}],
                "temperature": 0,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            # reasoning model may have burned budget
            rc = msg.get("reasoning_content") or ""
            m = re.search(r"\{.*\}", rc, re.S)
        if m:
            return json.loads(m.group(0))
        return {"error": "no json", "raw": (msg.get("content") or "")[:100]}
    except Exception as e:
        return {"error": str(e)[:120]}


def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    with open(OUT, "w") as f:
        for qid, q, exp in TESTS:
            if only and qid not in only:
                continue
            t0 = time.time()
            try:
                ans, hits = rag.answer(q, api_key=KEY)
            except Exception as e:
                ans, hits = f"ENGINE ERROR: {e}", []
            dt = time.time() - t0
            s = judge(q, exp, ans)
            rec = {
                "id": qid, "question": q, "answer": ans,
                "sources": list(dict.fromkeys(h["name"] for h in hits))[:8],
                "latency_s": round(dt, 1),
                "scores": {k: s.get(k) for k in ("retrieval", "faithfulness", "relevance", "completeness")},
                "note": s.get("note", s.get("error", "")),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            sc = rec["scores"]
            print(f"{qid} ({dt:.0f}s) R:{sc.get('retrieval')} F:{sc.get('faithfulness')} "
                  f"Rel:{sc.get('relevance')} C:{sc.get('completeness')} | {rec['note'][:70]}")
            time.sleep(1.5)
    print("DONE ->", OUT)


if __name__ == "__main__":
    main()
