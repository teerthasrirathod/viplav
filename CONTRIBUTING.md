# Contributing to VIPLAV

Thank you. There are three good ways to help.

## 1. Record your language

Run VIPLAV, open `/record`, and read sentences aloud in Lambadi (or any language you speak). Each clip is saved with its exact text. Read [docs/LANGUAGES.md](docs/LANGUAGES.md#doing-the-recordings-right) first, especially the parts on consent and spelling. Recordings stay on your machine unless you choose to share them.

## 2. Add a voice or listening engine

A voice engine is one class in `viplav/engines/tts.py`:

```python
class MyVoice(_LocalModel):           # _LocalModel loads the model once, off the event loop
    name = "my-voice"                 # what users put in VIPLAV_TTS
    languages = {"hi", "te"}          # VIPLAV's language codes it can speak

    def _load(self):                  # download/load the model (runs once, in a thread)
        ...

    def _run(self, text, lang) -> bytes:   # return WAV bytes for one sentence
        return wav_bytes(samples, sample_rate)
```

Then add it to `ENGINES`, add its packages as an extra in `pyproject.toml`, and add a row to the engine table in the README, including its licence. Listening engines follow the same pattern in `viplav/engines/stt.py`: `transcribe(pcm16, hint) -> (text, lang)`.

## 3. Add a language

Add an entry to `LANGUAGES` in `viplav/languages.py`. If the language has its own script, add the script's Unicode range to `script_of`, so mixed sentences get split correctly. Then add tests to `tests/test_languages.py`.

## Before opening a pull request

```bash
pip install -e ".[dev]"
python -m pytest -q
for f in web/*.js; do node --check "$f"; done
```

- Keep changes focused.
- Match the surrounding style. Plain Python and plain browser JavaScript, with no build step.
- Explain in the PR what you tested, and on what hardware, if a model is involved.
