"""Voice engines (text to speech). All free; the local ones download a model once.

Every engine has the same shape: a `name`, the set of `languages` it can voice, and
`synthesize(text, lang) -> (audio_bytes, mime)`. It returns None to let the browser
speak instead. To add an engine, write one class like these and register it in ENGINES.

    browser       built into Chrome/Edge/Safari. Zero setup, quality depends on the device.
    kokoro        Kokoro-82M (Apache-2.0). Natural English and Hindi; light enough for a laptop CPU.
    mms           Meta MMS-TTS. English, Hindi, Telugu; tiny and fast on any CPU, plainer voice.
                  Licensed CC-BY-NC-4.0: fine for personal use, not for selling.
    indic-parler  AI4Bharat Indic Parler-TTS (Apache-2.0). English, Hindi, Telugu and 18 more
                  Indian languages. Best Indic quality, but heavy: wants a GPU or Apple Silicon.
"""

import asyncio
import io
import logging

log = logging.getLogger("viplav.tts")


def wav_bytes(samples, sample_rate: int) -> bytes:
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.asarray(samples, dtype="float32"), sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class BrowserTTS:
    name = "browser"
    languages = {"en", "hi", "te"}

    async def synthesize(self, text: str, lang: str):
        return None

    async def aclose(self):
        pass


class _LocalModel:
    """Loads its model on first use and runs synthesis off the event loop, one at a time."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._loaded = False

    def _load(self):
        raise NotImplementedError

    def _run(self, text: str, lang: str) -> bytes:
        raise NotImplementedError

    async def synthesize(self, text: str, lang: str):
        async with self._lock:
            if not self._loaded:
                await asyncio.to_thread(self._load)
                self._loaded = True
            return await asyncio.to_thread(self._run, text, lang), "audio/wav"

    async def warm_up(self):
        async with self._lock:
            if not self._loaded:
                await asyncio.to_thread(self._load)
                self._loaded = True

    async def aclose(self):
        pass


class KokoroTTS(_LocalModel):
    name = "kokoro"
    languages = {"en", "hi"}
    _LANG_CODES = {"en": "a", "hi": "h"}  # Kokoro's codes: a = American English, h = Hindi

    def __init__(self, voices: dict[str, str] | None = None, speed: float = 1.0):
        super().__init__()
        self.voices = {"en": "af_heart", "hi": "hf_alpha", **(voices or {})}
        self.speed = speed
        self._pipelines = {}

    def _load(self):
        from kokoro import KPipeline

        for lang, code in self._LANG_CODES.items():
            self._pipelines[lang] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M")

    def _run(self, text: str, lang: str) -> bytes:
        import numpy as np

        pipeline = self._pipelines[lang]
        chunks = [audio for _, _, audio in pipeline(text, voice=self.voices[lang], speed=self.speed)]
        return wav_bytes(np.concatenate([np.asarray(c) for c in chunks]) if chunks else [], 24000)


class MmsTTS(_LocalModel):
    name = "mms"
    languages = {"en", "hi", "te"}
    _MODELS = {"en": "facebook/mms-tts-eng", "hi": "facebook/mms-tts-hin", "te": "facebook/mms-tts-tel"}

    def __init__(self):
        super().__init__()
        self._models = {}

    def _load(self):
        from transformers import AutoTokenizer, VitsModel

        for lang, repo in self._MODELS.items():
            self._models[lang] = (VitsModel.from_pretrained(repo), AutoTokenizer.from_pretrained(repo))

    def _run(self, text: str, lang: str) -> bytes:
        import torch

        model, tokenizer = self._models[lang]
        with torch.no_grad():
            waveform = model(**tokenizer(text, return_tensors="pt")).waveform[0].numpy()
        return wav_bytes(waveform, model.config.sampling_rate)


class IndicParlerTTS(_LocalModel):
    name = "indic-parler"
    languages = {"en", "hi", "te"}
    MODEL = "ai4bharat/indic-parler-tts"

    def __init__(self, speakers: dict[str, str] | None = None):
        super().__init__()
        # The model card's recommended speakers for each language.
        self.speakers = {"en": "Mary", "hi": "Divya", "te": "Lalitha", **(speakers or {})}

    def _load(self):
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        if torch.cuda.is_available():
            self.device = "cuda:0"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(self.MODEL).to(self.device)
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL)
        self.description_tokenizer = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path)

    def _run(self, text: str, lang: str) -> bytes:
        description = (
            f"{self.speakers[lang]}'s voice is warm and expressive, at a natural pace, with a very "
            "close recording that has almost no background noise."
        )
        desc = self.description_tokenizer(description, return_tensors="pt").to(self.device)
        prompt = self.tokenizer(text, return_tensors="pt").to(self.device)
        generation = self.model.generate(
            input_ids=desc.input_ids,
            attention_mask=desc.attention_mask,
            prompt_input_ids=prompt.input_ids,
            prompt_attention_mask=prompt.attention_mask,
        )
        return wav_bytes(generation.cpu().numpy().squeeze(), self.model.config.sampling_rate)


ENGINES = {cls.name: cls for cls in (BrowserTTS, KokoroTTS, MmsTTS, IndicParlerTTS)}


class VoiceRouter:
    """Picks, per language, the first engine in the user's list that can voice it.

    VIPLAV_TTS=kokoro,mms means: Kokoro for English and Hindi, and MMS for Telugu. If an engine fails mid-conversation, that sentence falls back to
    the browser.
    """

    def __init__(self, engines: list):
        self.engines = engines
        self.name = "+".join(e.name for e in engines)

    @classmethod
    def from_spec(cls, spec: str) -> "VoiceRouter":
        engines = []
        for name in (n.strip() for n in spec.split(",") if n.strip()):
            if name not in ENGINES:
                raise ValueError(f"Unknown voice engine {name!r}; choose from {', '.join(ENGINES)}")
            engines.append(ENGINES[name]())
        if not any(isinstance(e, BrowserTTS) for e in engines):
            engines.append(BrowserTTS())  # always have something that can speak
        return cls(engines)

    def engine_for(self, lang: str):
        return next((e for e in self.engines if lang in e.languages), self.engines[-1])

    def plan(self) -> dict[str, str]:
        return {lang: self.engine_for(lang).name for lang in ("en", "hi", "te")}

    async def synthesize(self, text: str, lang: str):
        engine = self.engine_for(lang)
        try:
            return await engine.synthesize(text, lang)
        except Exception as exc:
            log.warning("%s could not voice %r (%s); the browser will speak it", engine.name, text[:40], exc)
            return None

    async def warm_up(self):
        for engine in self.engines:
            if hasattr(engine, "warm_up"):
                try:
                    await engine.warm_up()
                except Exception as exc:
                    log.warning("Couldn't load voice engine %s: %s", engine.name, exc)

    async def aclose(self):
        for engine in self.engines:
            await engine.aclose()
