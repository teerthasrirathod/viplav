"""The user's languages, and splitting mixed-language text so each part gets the right voice.

VIPLAV writes each language in its own script, even mid-sentence: Hindi in Devanagari,
Telugu in Telugu script, English in Latin letters. That's what lets a voice engine
pronounce a mixed sentence properly. "Yes, ये बिल्कुल सही है" can be voiced as English
then Hindi, whereas "Yes, ye bilkul sahi hai" can only be read with one accent.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # short id used across VIPLAV
    name: str  # how the prompt and UI refer to it
    locale: str  # BCP-47 tag for browser speech recognition and voices
    script: str  # script VIPLAV writes it in
    voice_lang: str  # which language's voice reads it aloud


LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "en-IN", "Latin", "en"),
    "hi": Language("hi", "Hindi", "hi-IN", "Devanagari", "hi"),
    "te": Language("te", "Telugu", "te-IN", "Telugu", "te"),
    # Lambadi (Gor Boli) has no standard script and no speech models yet (see
    # docs/LANGUAGES.md). It's written in Devanagari or Telugu script, and voiced by
    # that script's language until a Lambadi voice exists.
    "lmn": Language("lmn", "Lambadi (Gor Boli)", "hi-IN", "Devanagari", "hi"),
}

_SCRIPT_LANG = {"Devanagari": "hi", "Telugu": "te", "Latin": "en"}


def parse_languages(spec: str, lambadi_script: str = "Devanagari") -> list[Language]:
    """Parse "en,hi,te,lmn" into Language entries, in the order given."""
    out = []
    for code in (c.strip().lower() for c in spec.split(",")):
        if code not in LANGUAGES:
            raise ValueError(f"Unknown language {code!r}; choose from {', '.join(LANGUAGES)}")
        lang = LANGUAGES[code]
        if code == "lmn":
            script = lambadi_script.capitalize()
            if script not in ("Devanagari", "Telugu"):
                raise ValueError("Lambadi script must be Devanagari or Telugu")
            lang = Language("lmn", lang.name, "te-IN" if script == "Telugu" else "hi-IN", script, _SCRIPT_LANG[script])
        out.append(lang)
    return out


def script_of(ch: str) -> str | None:
    """The script a character belongs to, or None for digits, punctuation and spaces."""
    cp = ord(ch)
    if 0x0900 <= cp <= 0x097F or 0xA8E0 <= cp <= 0xA8FF:
        return "Devanagari"
    if 0x0C00 <= cp <= 0x0C7F:
        return "Telugu"
    if ch.isascii() and ch.isalpha() or 0x00C0 <= cp <= 0x024F:
        return "Latin"
    return None


def split_by_language(text: str, min_words: int = 3) -> list[tuple[str, str]]:
    """Split text into (voice_lang, piece) runs by script.

    A short run, under `min_words` words (an English term like "Python" inside a
    Hindi sentence), stays with its neighbours. Voices handle the odd foreign word
    well, and breaking a sentence into tiny clips sounds choppy.
    """
    runs: list[list] = []  # [lang, text]
    pending = ""  # neutral characters waiting for the next run
    for ch in text:
        script = script_of(ch)
        if script is None:
            if runs:
                runs[-1][1] += ch
            else:
                pending += ch
            continue
        lang = _SCRIPT_LANG[script]
        if runs and runs[-1][0] == lang:
            runs[-1][1] += ch
        else:
            # Trailing spaces/punctuation belong with the next run, not the previous one.
            if runs:
                body = runs[-1][1]
                stripped = body.rstrip(" ")
                runs[-1][1], lead = stripped, body[len(stripped):]
            else:
                lead = ""
            runs.append([lang, pending + lead + ch])
            pending = ""
    if not runs:
        return [("en", text)] if text.strip() else []

    # Fold short runs into the neighbour before them (or after, at the start).
    merged: list[list] = []
    for lang, piece in runs:
        if merged and len(piece.split()) < min_words:
            merged[-1][1] += piece
        elif merged and merged[-1][0] == lang:
            merged[-1][1] += piece
        else:
            merged.append([lang, piece])
    if len(merged) > 1 and len(merged[0][1].split()) < min_words:
        merged[1][1] = merged[0][1] + merged[1][1]
        merged.pop(0)
    return [(lang, piece.strip()) for lang, piece in merged if piece.strip()]


def dominant_language(text: str) -> str:
    """The voice language most of the letters in `text` belong to."""
    counts: dict[str, int] = {}
    for ch in text:
        if script := script_of(ch):
            lang = _SCRIPT_LANG[script]
            counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.get) if counts else "en"


def language_prompt(languages: list[Language]) -> str:
    """The part of the system prompt that tells VIPLAV how to use the user's languages."""
    names = [lang.name for lang in languages]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    lines = [
        f"Languages: the user thinks and speaks in {listed}, and often mixes them within "
        "one sentence. Meet them in their own languages:",
        "- Reply in the mix the user just used. If they switch, switch with them. Don't "
        "move them into English unless they ask.",
        "- When an idea lands better in one of their languages, through a word, a saying "
        "or an everyday comparison from that language, use it. Keep technical terms in "
        "the form people actually say them, which is often English.",
        "- Write every word in its own script, even mid-sentence: "
        + ", ".join(f"{lang.name} in {lang.script}" for lang in languages if lang.code != "lmn")
        + ". For example: \"Yes, ये बिल्कुल सही है.\" Your voice chooses pronunciation from "
        "the script, so Hindi or Telugu typed in Latin letters gets read with an English accent.",
    ]
    if lambadi := next((lang for lang in languages if lang.code == "lmn"), None):
        lines.append(
            f"- Lambadi (Gor Boli) has no standard script; write it in {lambadi.script}. "
            "Your Lambadi may be limited. Use it where you're confident. Otherwise say so "
            "in a few words and use the closest of their other languages. When the user "
            "corrects a Lambadi word, thank them briefly and use their version from then on."
        )
    return "\n".join(lines)
