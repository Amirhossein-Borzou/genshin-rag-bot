"""Chitchat gate (zero tokens): rule-based filter for non-game messages.

Checks, in order of cheapness:
  1. Genshin/game signal words (en + fa glossary terms) -> game message.
  2. A known entity name (character/weapon, from the same index rag.py loads) -> game.
  3. Otherwise, a short message with NO game signal and NO question-mark game
     phrasing is chitchat -> the handler answers with CHITCHAT_REPLY and never
     calls the LLM.

Conservative by design: anything ambiguous (medium/long messages, any game-ish
word, any entity) falls through to the normal RAG path. False "game" verdicts
just cost what the bot already cost before this gate existed.
"""
import re

# Broad game-signal vocabulary: if ANY of these appear, it's a game question.
GAME_WORDS = {
    # generic game/data words the KB serves
    "genshin", "impact", "hoYoLAB", "mihoyo", "hoyoverse", "teyvat",
    "character", "weapon", "artifact", "constellation", "refinement",
    "ascension", "talent", "passive", "burst", "skill", "attack", "norma",
    "crit", "dmg", "damage", "heal", "shield", "buff", "debuff", "element",
    "pyro", "hydro", "electro", "cryo", "anemo", "geo", "dendro", "physical",
    "er", "em", "cd", "cr", "hp", "def", "atk", "energy", "recharge",
    "build", "team", "comp", "rotation", "combo", "playable", "banner",
    "gacha", "pull", "pity", "primogem", "resin", "domain", "spiral",
    "abyss", "event", "quest", "story", "lore", "region", "stat", "stats",
    "substat", "scaling", "scale", "material", "materials", "prefarm",
    "farm", "farming", "drop", "boss", "weekly", "weaponfit", "sig",
    "signature", "bis", "best", "better", "good", "vs", "compare", "worth",
    "c0", "c1", "c2", "c3", "c4", "c5", "c6", "r1", "r2", "r3", "r4", "r5",
    "kit", "melt", "vaporize", "freeze", "superconduct", "swirl", "electro-charged",
    "crystallize", "quicken", "spread", "aggravate", "bloom", "hyperbloom",
    "burgeon", "burning", "lunar", "reaction", "uptime", "er",
    "nanoka", "game8", "keqingmains", "kqm", "leak", "leaks", "beta", "live",
    "update", "updated", "version", "patch", "5.0", "6.0", "7.0",
    # common question stems that in this bot's context mean game stuff
}

# English question words that appear in genuine chitchat — a bare presence of
# "who/what/how" alone must NOT save a message, so question stems above are
# only consulted together with an entity/game word via the two-signal rule.

# English words that signal the message is (probably) NOT a game question.
# Kept small and safe: only strong conversational markers.
CHAT_MARKERS = {
    "thanks", "thank", "thx", "ty", "lol", "haha", "hahaha", "ok", "okay",
    "cool", "nice", "great", "awesome", "goodbye", "bye", "hi", "hello", "hey",
    "sup", "yo", "morning", "evening", "night", "please", "sorry", "okh",
    "sure", "yeah", "yep", "nope", "nah", "maybe", "idk", "hmm", "hmmm",
    "yourself", "myself", "chatting", "chat", "talk", "talking", "joke",
    "joking", "kidding", "funny", "love", "like", "hate", "feel", "feeling",
    "bored", "tired", "hungry", "sleepy", "happy", "sad", "angry",
}

CHAT_MARKERS_FA = {
    "سلام", "درود", "خداحافظ", "خداحافظ", "مرسی", "ممنون", "لطفا", "ببخشید",
    "چطوری", "چه خبر", "خبر", "اوکی", "اوح", "اوه", "وای", "اخ", "آخ",
    "هها", "خخ", "لول", "عالی", "خوبم", "خوب", "بد", "خسته", "شاد", "ناراحت",
    "دوست", "عشق", "بیا", "برو", "بیا", "شوخی", "جدی", "راستی",
}

CHAT_MARKERS.update(CHAT_MARKERS_FA)

# meta/conversation markers: words about the bot or the conversation itself.
# Only consulted AFTER the game-signal check fails, so "is this bot updated
# for 6.0" (has game words) still goes to RAG while "how reliable are your
# answers" (no game signal) gets gated.
META_MARKERS = {
    "answer", "answers", "answerd", "reliable", "reliably", "reliability",
    "accurate", "accuracy", "accurately", "trust", "trustworthy", "certain",
    "wrong", "mistake", "mistakes", "error", "errors", "hear", "heard",
    "listen", "opinion", "honest", "feedback", "bot", "bots", "ai",
    "you", "your", "youre", "ur", "u", "yourself", "anyone", "someone",
    "thinking", "think", "thought", "know", "knows", "real", "really",
    "curious", "wonder", "wondering", "mean", "means", "sure", "works",
    "work", "working", "actually", "just", "still", "even", "want",
    "wanted", "needs", "need", "anything", "everything", "somehow",
}

# min length before a message can even be considered chitchat (1-2 chars are
# always chitchat, longer needs the no-signal rule)
MIN_CHitchat_LEN = 2

CHITCHAT_REPLY = (
    "⚔️ I'm a Genshin Impact data bot — I answer from live game data "
    "(characters, weapons, artifacts, builds, materials).\n\n"
    "Try asking something like:\n"
    "• What does Ayaka's burst do?\n"
    "• Nahida ascension materials\n"
    "• Is Vesna's sig good for Zibai C0?"
)

_PUNCT_RE = re.compile(r"[\s!.,?\-—:;\"'()\[\]]+")


def _tokens(text):
    return [t for t in re.findall(r"[a-zA-Z\u0600-\u06FF0-9']+", text.lower()) if t]


def is_chitchat(question):
    """True when the message has NO game signal and reads as conversation.

    Two-strike rule: a message is chitchat only if
      (a) no GAME_WORD token, no glossary-term substring, no known entity name,
      (b) it is short (<= 12 tokens) OR every token is a chat marker / filler,
      (c) it contains at least one chat marker OR is a bare greeting/question
          fragment (<= 4 tokens).
    Anything else goes to the RAG pipeline (which already refuses gracefully).
    """
    q = question.strip()
    if not q:
        return False  # empty: let the handler ignore it
    try:
        import rag  # works both as package module and as plain script sibling
    except ImportError:
        from . import rag  # late import to reuse its loaded indexes

    ql = q.lower()

    # 1. hard game signals
    toks = _tokens(q)
    if not toks:
        # punctuation/emoji-only or pure non-Latin/non-Arabic-script text
        # (e.g. Russian, emoji) — treat short ones as chitchat, long as game-ish
        stripped = _PUNCT_RE.sub("", ql)
        return len(stripped) < MIN_CHitchat_LEN * 3
    if any(t in GAME_WORDS for t in toks):
        return False
    # glossary terms (Persian) — rag.GLOSSARY keys, normalized digits
    qn = q.translate(rag.PERSIAN_DIGITS)
    for k in rag.GLOSSARY:
        if k in qn:
            return False
    # known entity names (character/weapon) — includes Persian names via glossary above
    for nm in rag._KNOWN_NAMES:
        if len(nm) > 2 and nm in ql:
            return False

    # 2. conversation signals
    n = len(toks)
    marker_hits = sum(1 for t in toks if t in CHAT_MARKERS)
    meta_hits = sum(1 for t in toks if t in META_MARKERS)
    if n <= 12 and marker_hits >= 1:
        return True
    if n <= 16 and meta_hits >= 1:
        # conversation about the bot/reliability/etc. with zero game signal
        return True
    if n <= 4:
        # very short message with no game signal at all ("?", "...", "salaaam")
        return True
    return False
