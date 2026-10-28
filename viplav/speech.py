"""Turning streamed text into speakable sentences."""

import re

# A sentence ends at terminal punctuation (the Devanagari danda included, plus any closing
# quotes/brackets) followed by whitespace, or at a line break. Requiring the whitespace keeps "3.5" and "e.g.x" intact.
_BOUNDARY = re.compile(r"[.!?…।॥]+[\"'”’)\]]*(?=\s)|\n+")
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "approx", "fig", "inc", "ltd", "co", "no", "u.s", "a.m", "p.m", "mt", "jan",
    "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}


class SentenceChunker:
    """Buffers streamed text and releases it a sentence at a time.

    Speaking the first sentence while Claude is still writing the rest is what makes
    the voice feel immediate instead of waiting for the whole reply.
    """

    def __init__(self, min_chars: int = 8, max_chars: int = 240):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.buf = ""

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out = []
        while (cut := self._find_cut()) is not None:
            piece, self.buf = self.buf[:cut].strip(), self.buf[cut:]
            if piece:
                out.append(piece)
        return out

    def flush(self) -> str | None:
        piece, self.buf = self.buf.strip(), ""
        return piece or None

    def _find_cut(self) -> int | None:
        for m in _BOUNDARY.finditer(self.buf):
            if m.group().startswith("\n"):
                return m.end()
            words = self.buf[: m.start()].split()
            last = words[-1].lower() if words else ""
            list_marker = last.isdigit() and m.group() == "." and (len(words) == 1 or words[-2].endswith(":"))
            if last in _ABBREVIATIONS or list_marker or (len(last) == 1 and last.isalpha()):
                continue  # "Dr. Smith", a list marker like "1.", or an initial like "J."
            if len(self.buf[: m.end()].strip()) < self.min_chars:
                continue
            return m.end()
        if len(self.buf) > self.max_chars:
            # No sentence end in sight: break at the last clause boundary, else a space.
            window = self.buf[: self.max_chars]
            for sep in ("; ", ", ", " — ", " "):
                idx = window.rfind(sep)
                if idx > self.max_chars // 3:
                    return idx + len(sep)
            return self.max_chars
        return None


class SpeechCleaner:
    """Strips markup that reads badly aloud. Stateful so code fences spanning chunks are skipped."""

    def __init__(self):
        self.in_code = False
        self.announced_code = False

    def clean(self, text: str) -> str:
        spoken = []
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i > 0:
                self.in_code = not self.in_code
                if self.in_code and not self.announced_code:
                    spoken.append("I've put the code on your screen.")
                    self.announced_code = True
            if not self.in_code:
                spoken.append(part)
        out = " ".join(spoken)
        out = re.sub(r"\[([^\]]+)\]\((?:https?://)?[^)]+\)", r"\1", out)  # [label](url) -> label
        out = re.sub(r"https?://\S+", "the link on screen", out)
        out = re.sub(r"`([^`]*)`", r"\1", out)
        out = re.sub(r"(\*\*|__|\*|~~)", "", out)
        out = re.sub(r"^\s*#{1,6}\s*", "", out, flags=re.M)
        out = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", out, flags=re.M)
        out = re.sub(r"\s*\|\s*", ", ", out)  # stray table pipes
        out = re.sub(r"\s+", " ", out).strip()
        return out if re.search(r"\w", out) else ""
