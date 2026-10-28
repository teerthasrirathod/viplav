# Publishing VIPLAV as an open-source project

This folder is already laid out as an open-source project:

- an MIT licence
- an installable Python package (`pyproject.toml`, with the `viplav` command)
- tests and a GitHub Actions workflow that runs them on every push
- a README, contribution guide and docs
- a plugin interface for voice and listening engines

What's left is putting it on GitHub and inviting people in.

## 1. Put it on GitHub

1. On github.com, click **New repository**. Name it `viplav`, make it **Public**, and leave it empty: no README, licence or .gitignore, since the project already has them.
2. In this folder, run:
   ```bash
   git remote add origin https://github.com/<your-username>/viplav.git
   git push -u origin main
   ```
3. On the repository page, add a description and topics: `voice-assistant`, `multilingual`, `indic`, `lambadi`, `speech`, `claude`, `text-to-speech`, `speech-recognition`. Topics are how people find projects.
4. Check the **Actions** tab. The tests should go green within a few minutes.

## 2. Make it easy to join

- **Issues.** Open a few issues yourself, labelled `good first issue`, for small, clear tasks. Some ideas:
  - add Tamil
  - try Kokoro's other Hindi voices
  - a dark/light theme toggle
  - an Android how-to
- **Discussions.** Turn them on (in Settings) for questions and ideas, so the issues stay for actual work.
- **A release.** Tag a version when it's usable: `git tag v0.1.0 && git push --tags`, then **Releases → Draft a new release**. People trust projects that have releases.
- **A demo.** A 30-second screen recording of VIPLAV talking in mixed Hindi/Telugu/English, shown at the top of the README, does more than any amount of text.

## 3. How "plugin" works here

Anyone can add a voice or a listening engine without touching the rest of VIPLAV. They write one class in `viplav/engines/tts.py` (or `stt.py`) with:

- a `name`
- a set of `languages`
- an async `synthesize(text, lang)` (or `transcribe(pcm16, hint)`)

Then they register it in `ENGINES`. That's how a future Lambadi voice will arrive: as one more class that loads `mms-tts-lmn`. CONTRIBUTING.md walks through it.

Later, if people want to use VIPLAV's engines inside their own apps, the `viplav` package can be published to PyPI (`pip install viplav`). The engines are already importable on their own (`from viplav.engines.tts import KokoroTTS`).

## 4. The Lambadi dataset as its own project

When you have recordings from people who agreed to share them, publish the dataset separately on Hugging Face:

1. Run `python tools/export_dataset.py lmn`.
2. Upload `dist/lmn-dataset` as a dataset.
3. Choose CC-BY-4.0, and write a dataset card covering who recorded, how consent was given, the spelling convention, and the regions and dialects included.

That dataset may matter more than the app itself, because it's the piece no one has built yet.

## 5. Things to keep out of the repository

These are already in `.gitignore`. Double-check before every push:

- `.env`: your API key. If it's ever pushed, revoke the key at console.anthropic.com at once.
- `data/profile.md`, `data/transcripts/` and `data/recordings/`: your personal notes, your conversations and people's voices. Publish voices only deliberately, and only with consent.
