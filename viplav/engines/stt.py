"""Listening engines (speech to text). Both are free.

    browser   the browser's own recognizer (Chrome, Edge, Safari). Zero setup. It needs one
              language picked at a time, and audio goes to the browser maker's servers.
    whisper   OpenAI Whisper via faster-whisper (MIT), running on your machine. It detects
              the language on its own and copes better with mixed speech. It needs a
              one-time model download, and the browser sends it your recorded audio.
"""

import asyncio
import logging

log = logging.getLogger("viplav.stt")

# Codes Whisper reports, mapped to VIPLAV's. Whisper has no Lambadi; it usually hears it as Hindi.
_WHISPER_LANGS = {"en": "en", "hi": "hi", "te": "te", "ur": "hi", "mr": "hi"}


class WhisperSTT:
    name = "whisper"
    sample_rate = 16000

    def __init__(self, model: str = "large-v3-turbo", allowed: set[str] | None = None):
        self.model_name = model
        self.allowed = allowed or {"en", "hi", "te"}
        self._model = None
        self._lock = asyncio.Lock()

    def _load(self):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(self.model_name, device="auto", compute_type="int8")

    def _run(self, pcm16: bytes, hint: str | None) -> tuple[str, str]:
        import numpy as np

        audio = np.frombuffer(pcm16, dtype="<i2").astype("float32") / 32768.0
        language = hint if hint in self.allowed else None
        if language is None:
            # Detect the language, but only choose among the user's languages. That stops
            # code-mixed Hindi from being transcribed as Urdu, or English as Welsh.
            _, _, probs = self._model.detect_language(audio)
            ranked = [code for code, _ in sorted(probs, key=lambda p: -p[1]) if _WHISPER_LANGS.get(code) in self.allowed]
            language = ranked[0] if ranked else None
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, _WHISPER_LANGS.get(info.language, "en")

    async def transcribe(self, pcm16: bytes, hint: str | None = None) -> tuple[str, str]:
        async with self._lock:
            if self._model is None:
                await asyncio.to_thread(self._load)
            return await asyncio.to_thread(self._run, pcm16, hint)

    async def warm_up(self):
        async with self._lock:
            if self._model is None:
                await asyncio.to_thread(self._load)
