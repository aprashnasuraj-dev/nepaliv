"""Nepali lyrics generation.

Strategy (no paid API, no GPU):
  1. Free-tier hosted LLMs through ONE OpenAI-compatible client, tried in
     order: Gemini (best Nepali of the free options in our tests), Groq,
     OpenRouter `:free` models, then an optional self-hosted llama.cpp server.
  2. Strict JSON output + our own validator (Devanagari only, syllable
     counts per line, line counts). Failures are fed back once for repair.
  3. Lyric-variant cache: the same normalised request keeps up to N variants.
     When the pool is full we serve from it -> free-tier quota stays healthy
     even if a "Happy Dashain" prompt goes viral.
  4. Offline template composer as the last resort, so the feature NEVER
     fails (good to have for demos and quota outages).

Honest note: small CPU-runnable models (Qwen2.5-3B/7B GGUF) write weak,
often Hindi-flavoured Nepali. Use the local LLM only as a fallback.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata

import httpx
import numpy as np

from ..config import get_settings
from ..kv import kv
from .nepali_text import count_syllables, devanagari_ratio, normalize, rhymes

log = logging.getLogger(__name__)

MIN_SYL, MAX_SYL = 5, 16
VARIANT_POOL = 6

SYSTEM_PROMPT = """You are a celebrated Nepali lyricist (गीतकार) who writes singable songs
in the tradition of Nepali lok geet and adhunik geet.

Rules:
- Write ONLY in Nepali, Devanagari script. No English words, no Hindi words, no digits, no emojis.
- Simple, warm, conversational Nepali that ordinary listeners understand.
- Each line must be singable: 8 to 14 aksharas (अक्षर), never more than 16.
- Prefer line-end rhymes (अनुप्रास/तुकबन्दी): line 2 and line 4 of each section should rhyme.
- Use concrete Nepali imagery where it fits: हिमाल, खोला, चौतारी, बतास, पहाड, गाउँ, साँझ, जून, माया.
- The chorus (स्थायी) must be catchy and contain the emotional hook; it can repeat a phrase.
- If a person's name is given, use it naturally (in Devanagari) at least once in the chorus.
- Output ONLY valid JSON, no markdown, matching exactly:
{"title": "...", "sections": [{"type": "verse", "lines": ["...","...","...","..."]},
                              {"type": "chorus", "lines": ["...","...","...","..."]}]}"""


def _structure(length: str) -> list[str]:
    return ["verse", "chorus", "verse"] if length == "full" else ["verse", "chorus"]


def _user_prompt(req: dict) -> str:
    parts = [f"गीतको विषय / Song idea: {req.get('prompt') or 'माया'}"]
    if req.get("occasion"):
        parts.append(f"Occasion: {req['occasion']}")
    if req.get("mood"):
        parts.append(f"Mood: {req['mood']}")
    if req.get("dedicate_to"):
        parts.append(f"Dedicated to (use this name, write it in Devanagari): {req['dedicate_to']}")
    parts.append(f"Musical style: {req.get('style', 'adhunik')}")
    secs = _structure(req.get("length", "short"))
    parts.append(f"Sections in order: {', '.join(secs)} (each exactly 4 lines).")
    return "\n".join(parts)


# ---- LLM chain ----------------------------------------------------------------
def _providers() -> list[dict]:
    s = get_settings()
    table = {
        "gemini": dict(base=s.gemini_base_url, key=s.gemini_api_key, model=s.gemini_model, json_mode=True),
        "groq": dict(base=s.groq_base_url, key=s.groq_api_key, model=s.groq_model, json_mode=True),
        "openrouter": dict(base=s.openrouter_base_url, key=s.openrouter_api_key, model=s.openrouter_model, json_mode=False),
        "local": dict(base=s.local_llm_base_url, key="local", model=s.local_llm_model, json_mode=False),
    }
    out = []
    for name in [p.strip() for p in s.llm_providers.split(",") if p.strip()]:
        p = table.get(name)
        if p and p["base"] and p["key"]:
            out.append({"name": name, **p})
    return out


def _chat(provider: dict, messages: list[dict], temperature: float) -> str:
    body = {"model": provider["model"], "messages": messages, "temperature": temperature, "max_tokens": 1200}
    if provider["json_mode"]:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"}
    if provider["name"] == "openrouter":
        headers["X-Title"] = "Nepali Song Generator"
    with httpx.Client(timeout=get_settings().llm_timeout_s) as c:
        r = c.post(provider["base"].rstrip("/") + "/chat/completions", json=body, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def validate(data: dict, length: str) -> tuple[dict | None, list[str]]:
    """Return (clean_lyrics, problems). Clean lines keep commas for display."""
    problems: list[str] = []
    want = _structure(length)
    secs = data.get("sections") or []
    clean_secs = []
    for i, typ in enumerate(want):
        sec = secs[i] if i < len(secs) else None
        if not sec or not isinstance(sec.get("lines"), list):
            problems.append(f"section {i + 1} ({typ}) missing")
            continue
        lines = []
        for ln in sec["lines"][:4]:
            ln = unicodedata.normalize("NFC", str(ln)).strip()
            ln = re.sub(r"[A-Za-z0-9\"“”'*#]+", "", ln).strip(" ,।")
            if devanagari_ratio(ln) < 0.95 or not normalize(ln):
                problems.append(f"line not in Devanagari Nepali: {ln!r}")
                continue
            n = count_syllables(ln)
            if n < MIN_SYL or n > MAX_SYL:
                problems.append(f"line has {n} sung syllables (want {MIN_SYL}-{MAX_SYL}): {ln}")
                if n > MAX_SYL + 4 or n < 3:
                    continue
            lines.append(ln)
        if len(lines) < 4:
            problems.append(f"{typ} needs 4 good lines, got {len(lines)}")
        clean_secs.append({"type": typ, "lines": lines})
    title = re.sub(r"[A-Za-z0-9\"]+", "", str(data.get("title", ""))).strip()
    ok = len(clean_secs) == len(want) and all(len(s["lines"]) >= 3 for s in clean_secs)
    if not title and clean_secs and clean_secs[min(1, len(clean_secs) - 1)]["lines"]:
        title = clean_secs[min(1, len(clean_secs) - 1)]["lines"][0][:24]
    return ({"title": title or "मेरो गीत", "sections": clean_secs} if ok else None), problems


def rhyme_score(lyrics: dict) -> float:
    pairs = hits = 0
    for s in lyrics["sections"]:
        ls = s["lines"]
        for a, b in ((0, 1), (1, 3), (2, 3)):
            if b < len(ls):
                pairs += 1
                hits += rhymes(ls[a], ls[b])
    return hits / max(1, pairs)


def _llm_lyrics(req: dict, seed: int) -> dict | None:
    length = req.get("length", "short")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": _user_prompt(req)}]
    for prov in _providers():
        try:
            for attempt in range(2):
                raw = _chat(prov, messages, temperature=0.9 if attempt == 0 else 0.6)
                lyrics, problems = validate(_extract_json(raw), length)
                if lyrics and len(problems) <= 2:
                    lyrics["source"] = prov["name"]
                    return lyrics
                messages = messages + [{"role": "assistant", "content": raw},
                                       {"role": "user", "content": "Please fix these problems and return the full JSON again:\n- "
                                        + "\n- ".join(problems[:8])}]
        except Exception as e:                                         # quota, timeout, bad JSON...
            log.warning("lyrics provider %s failed: %s", prov["name"], e)
    return None


# ---- public API ----------------------------------------------------------------
def lyrics_cache_key(req: dict) -> str:
    sig = json.dumps({k: (req.get(k) or "").strip().lower() if isinstance(req.get(k), str) else req.get(k)
                      for k in ("prompt", "occasion", "mood", "dedicate_to", "length", "style")},
                     sort_keys=True, ensure_ascii=False)
    return "lyr:" + hashlib.sha1(sig.encode()).hexdigest()[:24]


def generate_lyrics(req: dict, seed: int) -> dict:
    key = lyrics_cache_key(req)
    pool = kv().lrange(key)
    if len(pool) >= VARIANT_POOL:                       # quota saver: reuse a cached variant
        pick = dict(pool[seed % len(pool)])
        pick["source"] = "cache"
        return pick
    lyrics = _llm_lyrics(req, seed)
    if lyrics:
        kv().lpush_trim(key, lyrics, VARIANT_POOL, ttl=30 * 24 * 3600)
        return lyrics
    if pool:
        return {**pool[seed % len(pool)], "source": "cache"}
    return template_lyrics(req, seed)


# ---- offline template composer ---------------------------------------------------
BANK: dict[str, dict[str, list[str]]] = {
    "love": {
        "verse": ["हिमालको हिउँजस्तै सेतो तिम्रो माया", "खोलाको पानीझैँ बगिरहन्छ यो मन",
                  "चौतारीमा बसी सम्झन्छु तिमीलाई", "बतासले ल्याउँछ तिम्रो मीठो बोली",
                  "साँझको जूनले सोध्छ तिम्रै कुरा", "आँखाभरि सजाएँ तिम्रै सपना"],
        "chorus": ["माया लाग्छ तिमीलाई, साँचो माया लाग्छ", "तिमीबिना अधुरो छ मेरो यो जीवन",
                   "मुटुभरि राखेँ {name} तिम्रो नाम", "सधैँ सँगै हिँडौँ, यो जुनी र त्यो जुनी"],
    },
    "birthday": {
        "verse": ["आज तिम्रो जन्मदिन, खुसी छायो घरमा", "फूलहरू फुले, उज्यालो भयो आँगनमा",
                  "बत्ती बल्यो, गीत गायौँ सँगसँगै", "हाँसोले भरियोस् तिम्रो हरेक बिहानी",
                  "सपना सबै पूरा होऊन् तिम्रा", "साथीहरू आए शुभकामना बोकेर"],
        "chorus": ["जन्मदिनको शुभकामना {name}लाई", "खुसी रहनु सधैँ, हाँसिरहनु सधैँ",
                   "सय वर्ष बाँच्नु, फूलझैँ फुलिरहनु", "हाम्रो माया सधैँ तिम्रै साथमा"],
    },
    "festival": {
        "verse": ["दसैँ आयो घरघरमा खुसी छायो", "रातो टीका, जमरा शिरमा सजायो",
                  "तिहारको दियो बल्यो आँगनभरि", "दाजुभाइ दिदीबहिनी भेला भयौँ",
                  "पिङ खेल्दै गाउँभरि रमाइलो भयो", "आमाको हातको मीठो खाना खायौँ"],
        "chorus": ["आयो आयो चाड हाम्रो, खुसी ल्यायो", "मिलीजुली मनाऔँ, माया बाँडौँ",
                   "बाजा बज्यो, नाच्यौँ सबै सँगै", "यो चाड सधैँ उज्यालो बनोस्"],
    },
    "patriotic": {
        "verse": ["हिमालजस्तै अटल छ हाम्रो मन", "पसिनाले सिँचौँ यो प्यारो माटो",
                  "सपनाहरू बोकेर अघि बढौँ", "बुद्धको देशमा शान्ति फुलाऔँ",
                  "पहाड, तराई, हिमाल एउटै घर", "युवाको हातमा भोलिको उज्यालो"],
        "chorus": ["हामी नेपाली, एउटै हाम्रो मन", "जहाँ गए पनि मुटुमा नेपाल",
                   "माटोको माया कहिल्यै नभुलौँ", "रातो चन्द्र सूर्य, हाम्रो शान"],
    },
    "sad": {
        "verse": ["परदेशको बाटोमा एक्लै छु म", "आँसुले भिजेको छ यो सिरानी",
                  "गाउँको याद आउँछ साँझपख", "आमाको काख सम्झी रुन्छ मन",
                  "पत्र लेख्छु, शब्द हराउँछन्", "जूनको उज्यालोमा तिम्रै अनुहार"],
        "chorus": ["कहिले फर्किन्छु म आफ्नै घर", "बिर्सन सकिनँ {name} तिम्रो माया",
                   "दुखेको मुटुलाई कसले बुझ्छ", "फेरि भेट होला, आशा बाँकी छ"],
    },
    "devotional": {
        "verse": ["बिहानै उठी दियो बालौँ", "मन्दिरको घण्टी बज्यो मधुर",
                  "फूल चढाऔँ भक्तिभावले", "सबैको भलो होस्, यही प्रार्थना",
                  "मनको अँध्यारो हटाइदेऊ", "शान्ति र माया छरिदेऊ"],
        "chorus": ["हे प्रभु, तिम्रै शरणमा छु म", "जय होस् तिम्रो, जय होस्",
                   "भक्तिको बाटो देखाइदेऊ", "सधैँ साथ देऊ हे भगवान"],
    },
    "lullaby": {
        "verse": ["निदाऊ नानी, जून आयो आकाशमा", "ताराहरू बसे तिम्रो सिरानीमा",
                  "चरीले गायो मीठो लोरी", "आमाको काख न्यानो र प्यारो",
                  "सपनामा फूलबारी डुल्नु", "बिहानी घामले ल्याउँछ खुसी"],
        "chorus": ["सुत {name} सुत, निदाऊ मेरो बाबु", "लोरी लोरी लोरी, मीठो निद्रा",
                   "आमा छिन् नजिकै, नडराऊ है", "भोलि फेरि खेलौँला सँगै"],
    },
    "friendship": {
        "verse": ["बाल्यकालका ती दिनहरू याद छ", "चौरमा दौडिँदै खेलेका हामी",
                  "दुःखमा पनि हाँस्यौँ सँगसँगै", "बाटो फरक भए पनि मन एउटै",
                  "चिया पसलका ती गफहरू", "सम्झनाको पोको बोकेर हिँड्छु"],
        "chorus": ["साथी हो साथी, सधैँ साथ दिने", "तिमीजस्तो साथी कहाँ पाउँ म",
                   "जिन्दगीको गीतमा {name} तिम्रै नाम", "यो मित्रता कहिल्यै नटुटोस्"],
    },
}

TOPIC_WORDS = {
    "birthday": ["birthday", "जन्मदिन", "janmadin"],
    "festival": ["dashain", "tihar", "दसैँ", "दशैं", "तिहार", "festival", "चाड", "holi", "होली", "teej", "तीज"],
    "patriotic": ["nepal", "desh", "देश", "नेपाल", "patriot", "राष्ट्र"],
    "sad": ["sad", "pardesh", "परदेश", "बिछोड", "miss", "दुःख", "breakup", "abroad"],
    "devotional": ["bhajan", "भजन", "god", "भगवान", "prayer", "प्रार्थना", "temple"],
    "lullaby": ["lori", "लोरी", "lullaby", "baby", "नानी", "sleep"],
    "friendship": ["friend", "साथी", "dost", "मित्र"],
}


def detect_topic(req: dict) -> str:
    text = " ".join(str(req.get(k) or "") for k in ("prompt", "occasion", "mood", "style")).lower()
    for topic, words in TOPIC_WORDS.items():
        if any(w in text for w in words):
            return topic
    return "love"


def template_lyrics(req: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    topic = detect_topic(req)
    bank = BANK[topic]
    name = (req.get("dedicate_to") or "").strip()
    if name and devanagari_ratio(name) < 0.9:        # Latin names can't be sung by a Nepali TTS reliably
        name = ""

    def fill(line: str) -> str:
        if "{name}" in line:
            line = line.replace("{name}लाई", f"{name}लाई" if name else "तिमीलाई").replace("{name} ", f"{name} " if name else "")
            line = line.replace("{name}", name)
        return re.sub(r"\s+", " ", line).strip()

    sections = []
    used: set[str] = set()
    for typ in _structure(req.get("length", "short")):
        if typ == "chorus":
            lines = [fill(l) for l in bank["chorus"]]
        else:
            fresh = [l for l in bank["verse"] if l not in used]
            if len(fresh) >= 4:
                idx = sorted(rng.choice(len(fresh), size=4, replace=False))
                lines = [fresh[i] for i in idx]
            else:                                    # 2nd verse with a small bank: new lines + reprise
                reprise = [l for l in bank["verse"] if l in used]
                lines = fresh + [reprise[i] for i in sorted(rng.choice(len(reprise), size=4 - len(fresh), replace=False))]
            used.update(lines)
        sections.append({"type": typ, "lines": lines})
    title = {"love": "तिम्रो माया", "birthday": "जन्मदिनको गीत", "festival": "चाडको रमझम",
             "patriotic": "हाम्रो नेपाल", "sad": "परदेशको याद", "devotional": "भक्ति गीत",
             "lullaby": "निदाऊ नानी", "friendship": "साथी"}[topic]
    return {"title": title, "sections": sections, "source": "template"}


def clean_user_lyrics(lyrics: dict) -> dict:
    """Light validation for user-edited lyrics: keep singable Devanagari lines only."""
    sections = []
    for sec in lyrics.get("sections", []):
        lines = []
        for ln in sec.get("lines", []):
            ln = unicodedata.normalize("NFC", str(ln)).strip()
            if ln and devanagari_ratio(ln) >= 0.9 and 1 <= count_syllables(ln) <= 24:
                lines.append(ln)
        if lines:
            sections.append({"type": sec.get("type", "verse"), "lines": lines})
    if not sections:
        raise ValueError("lyrics must contain Nepali (Devanagari) lines")
    return {"title": lyrics.get("title") or "मेरो गीत", "sections": sections, "source": "user"}
