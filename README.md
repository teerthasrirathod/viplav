# VIPLAV

**A voice companion that speaks your languages, including the way you mix them.**

You talk, VIPLAV talks back, through an animated face in your browser. It's built for people who think in more than one language: it answers in the mix you used (English, Hindi, Telugu, Lambadi), writes each language in its own script, and gives each language its own voice, even inside a single sentence.

- **The mind is Claude**, with web search. By default it uses the Claude plan you already have, through the official Claude Code program, so it costs nothing extra.
- **The ears and the voice are free.** They work in the browser with zero setup, or with open-source models running on your own machine. There are no speech API keys and no extra subscriptions.

Low cost is the project's first rule: see [docs/COST.md](docs/COST.md).

```
 you speak ──► ears ──► Claude ──► sentence by sentence, split by language ──► voice ──► face
              browser   (the mind)   "Of course." | "यह आसान है।" | "చెప్తాను."        browser
              Whisper                                                       Kokoro · MMS · Indic Parler
```

## Quick start

**New to this? Follow the step-by-step guide: [docs/SETUP.md](docs/SETUP.md)** (Mac, Windows, Linux).

You need Python 3.10+, Chrome, Edge or Safari, and [Claude Code](https://code.claude.com) signed in with your Claude plan (run `claude` once and log in).

```bash
git clone https://github.com/<you>/viplav && cd viplav
./run.sh          # the first run creates .env with free defaults
# optional: set VIPLAV_USER_NAME and VIPLAV_LANGUAGES in .env
./run.sh
```

Open http://127.0.0.1:8765, pick the language you'll speak, tap **Tap to talk** (or press Space), and talk. Headphones help. To tell VIPLAV about yourself, copy `data/profile.example.md` to `data/profile.md`. Conversations are saved as text in `data/transcripts/`.

To use it from a phone or tablet, see [docs/PHONE.md](docs/PHONE.md).

## A long thinking session

VIPLAV is built for long sessions of thinking out loud, jumping between many things at once.

- **The board.** As you talk, VIPLAV files every topic as a thread on the **Board** (beside the face, or below it on a phone):
  - a title and a category (Projects, Company, Study, Family, and so on)
  - a status: open, exploring, decided, to do, waiting, parked or done
  - a one-line summary and the next step

  Dump ten things in one breath and it files all ten, groups them, and then talks through them with you. Jump back to one an hour later and it picks the thread up from where you left it.
- **It carries over.** The board is saved after every change (`data/board.json`, plus readable notes in `data/board.md`) and read back at the start of the next session. **New chat** clears the conversation but keeps the board. To finish or delete threads, just say so.
- **Things to say:**
  - "Put these on the board…"
  - "What's open?"
  - "Park the company name for now."
  - "We decided X, mark it."
  - "Summarise where everything stands."
- **Cost.** With the default subscription brain, a long session costs nothing extra; it uses your plan's usage limits. To make them last (lower effort, Sonnet, New chat when you change subject), see [docs/COST.md](docs/COST.md). If you hit a limit, VIPLAV tells you, and works again when it resets.
- **Comfort.**
  - Use headphones, so VIPLAV doesn't hear itself.
  - Keep **Transcript** open if you like to see the words.
  - If the browser recognizer mishears you often, try the language picker, or local Whisper later.

## Free voices and ears

| | Engine | Languages | Runs on | Licence |
|---|---|---|---|---|
| Voice | `browser` (default) | whatever your device has | anything | — |
| Voice | `kokoro` | English, Hindi | a laptop CPU, faster than real time | Apache-2.0 |
| Voice | `mms` | English, Hindi, Telugu | any CPU, very light | CC-BY-NC-4.0 (not for commercial use) |
| Voice | `indic-parler` | English, Hindi, Telugu + 18 Indian languages | a GPU or Apple Silicon | Apache-2.0 |
| Ears | `browser` (default) | one language at a time, chosen in the app | anything (audio goes to the browser maker) | — |
| Ears | `whisper` | detects the language; handles mixing better | a laptop CPU (slower) or a Mac (fine) | MIT |

The best free setup today, once you can run models: `VIPLAV_TTS=kokoro,mms` and `VIPLAV_STT=whisper`. `./run.sh` installs whatever your `.env` asks for. Each model downloads once (between a few hundred MB and about 1.6 GB) and then works offline.

Tested on a 4-core CPU with no GPU:

- Kokoro made 3.8 s of English speech in 1.6 s.
- MMS made 4.1 s of Telugu in 0.6 s.
- Whisper `large-v3-turbo` transcribed a 4 s sentence in about 4.5 s. It got Hindi exactly right, and Telugu right in Telugu script.
- The smaller `small` model was faster, but it wrote Telugu in Devanagari letters.

## Languages, and why the script matters

Ask VIPLAV something in Hinglish and it answers in Hinglish. It writes `Yes, ये बिल्कुल सही है` rather than `Yes, ye bilkul sahi hai`. That way the English part gets an English voice and the Hindi part a Hindi voice. Romanised Hindi can only be read with one accent. Short borrowed words (a "Python" inside a Hindi sentence) stay with the sentence around them, so the speech doesn't sound choppy.

**Lambadi (Gor Boli)** has no speech models anywhere yet. No recognizer, no voice, no public dataset. Meta's MMS can only tell that someone is speaking it. VIPLAV writes Lambadi in Devanagari (or Telugu script, by setting) and voices it with the Hindi (or Telugu) voice for now. The **Record** page (`/record`) exists to change that: it collects sentence-and-recording pairs in exactly the format that model-training tools expect. See [docs/LANGUAGES.md](docs/LANGUAGES.md) for the research and the plan.

## How it stays fast

Claude's reply is cut into sentences while it's still being written. Each sentence goes to the voice right away and plays as soon as the one before it ends. You can interrupt by talking over it, and Esc always stops it. The system prompt (`viplav/brain.py`, `viplav/languages.py`) is written for the ear: answer first, no lists or markdown, length matched to the question, and code shown on screen instead of read out.

## Code map

| Path | What's there |
|---|---|
| `viplav/claude_code.py` | The default brain: your Claude plan, through the `claude` program |
| `viplav/brain.py` | The voice prompt, and the optional pay-per-use API brain |
| `viplav/mcp_board.py` | The board tool, served to Claude Code over MCP |
| `viplav/board.py` | The thinking board: threads, categories, saving, and the `update_board` tool |
| `viplav/languages.py` | Language settings, the multilingual prompt, splitting text by script |
| `viplav/engines/tts.py`, `stt.py` | Voice and listening engines (plugins: one class each) |
| `viplav/speech.py` | Sentence splitting and cleaning text for speech |
| `viplav/app.py` | Web server, WebSocket protocol (documented at the top), recorder API |
| `web/` | The face, mic handling, playback and the recorder. Plain JS, no build step |

Run the tests with `pip install -e ".[dev]" && python -m pytest -q`. They need no API keys.

## Contributing

Adding an engine, a language, or Lambadi recordings: see [CONTRIBUTING.md](CONTRIBUTING.md). To publish your own copy, see [docs/OPEN_SOURCE.md](docs/OPEN_SOURCE.md).

MIT licensed. Model licences are listed in the table above.
