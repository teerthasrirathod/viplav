"""Web server: serves the face, runs voice turns over a WebSocket, and stores voice recordings.

WebSocket protocol (JSON text frames, plus binary audio frames when VIPLAV_STT=whisper)
  client -> server  {"type": "user_text", "text": ...}       a finished utterance
                    {"type": "set_language", "lang": ...}    "auto" or a language code: a hint for listening
                    <binary>                                 one utterance as 16 kHz mono 16-bit PCM
                    {"type": "interrupt"}                    stop talking now
                    {"type": "reset"}                        start a fresh conversation
  server -> client  {"type": "hello", "voices": {lang: engine}, "stt": ..., "languages": [...], ...}
                    {"type": "transcript", "text": ..., "lang": ...}   what Whisper heard
                    {"type": "state", "state": "thinking"|"speaking"|"idle"}
                    {"type": "status", "text": ...}          e.g. "Searching the web…"
                    {"type": "text_delta", "turn": n, "text": ...}
                    {"type": "speech", "turn": n, "seq": i, "text": ..., "lang": ..., "audio": b64|null, "mime": ...}
                    {"type": "turn_end", "turn": n}
                    {"type": "error", "message": ...}
"""

import asyncio
import base64
import contextlib
import datetime as dt
import json
import logging
import re
import uuid
from collections.abc import Callable
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .brain import Brain
from .config import ROOT, Settings, load_settings
from .engines.stt import WhisperSTT
from .engines.tts import VoiceRouter
from .languages import LANGUAGES, split_by_language
from .speech import SentenceChunker, SpeechCleaner

log = logging.getLogger("viplav")
WEB_DIR = ROOT / "web"
MAX_UTTERANCE_BYTES = 16000 * 2 * 60  # one minute of 16 kHz 16-bit audio


class Transcript:
    """Plain-text log of each conversation, so you can reread what was said."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.md"

    def add(self, who: str, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"**{who}** ({dt.datetime.now():%H:%M:%S}): {text.strip()}\n\n")


class VoiceSession:
    def __init__(self, ws: WebSocket, brain: Brain, voice: VoiceRouter, stt, transcript: Transcript | None):
        self.ws = ws
        self.brain = brain
        self.voice = voice
        self.stt = stt
        self.transcript = transcript
        self.lang_hint: str | None = None
        self.turn_id = 0
        self.turn_task: asyncio.Task | None = None
        # Utterances wait here and are transcribed one at a time: a running transcription
        # can't be stopped part-way, so overlapping ones would only slow each other down.
        self.heard: asyncio.Queue[bytes] = asyncio.Queue()
        self.listen_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()

    async def send(self, **msg) -> None:
        async with self._send_lock:
            await self.ws.send_text(json.dumps(msg, ensure_ascii=False))

    async def cancel_turn(self) -> None:
        task, self.turn_task = self.turn_task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def start_turn(self, text: str) -> None:
        await self.cancel_turn()
        self.turn_id += 1
        self.turn_task = asyncio.create_task(self.run_turn(self.turn_id, text))

    async def listen(self) -> None:
        """Transcribe each utterance with Whisper, in order, and answer it."""
        while True:
            pcm16 = await self.heard.get()
            try:
                text, lang = await self.stt.transcribe(pcm16, self.lang_hint)
            except Exception as exc:
                log.exception("transcription failed")
                await self.send(type="error", message=f"Couldn't transcribe that: {exc}")
                continue
            await self.send(type="transcript", text=text, lang=lang)
            if text:
                await self.start_turn(text)

    async def run_turn(self, turn: int, text: str) -> None:
        if self.transcript:
            self.transcript.add("You", text)
        chunker, cleaner = SentenceChunker(), SpeechCleaner()
        queue: asyncio.Queue = asyncio.Queue()
        synth_tasks: list[asyncio.Task] = []
        full_reply: list[str] = []

        def enqueue(sentence: str) -> None:
            spoken = cleaner.clean(sentence)
            # A mixed-language sentence is voiced in parts, each by its own language's voice.
            for lang, piece in split_by_language(spoken):
                # Start synthesis right away; the speaker below still delivers in order.
                task = asyncio.create_task(self.voice.synthesize(piece, lang))
                synth_tasks.append(task)
                queue.put_nowait((piece, lang, task))

        async def speaker() -> None:
            seq = 0
            while (item := await queue.get()) is not None:
                piece, lang, task = item
                result = await task
                audio, mime = result if result else (None, None)
                if seq == 0:
                    await self.send(type="state", state="speaking")
                await self.send(
                    type="speech",
                    turn=turn,
                    seq=seq,
                    text=piece,
                    lang=lang,
                    audio=base64.b64encode(audio).decode() if audio else None,
                    mime=mime,
                )
                seq += 1

        speaker_task = asyncio.create_task(speaker())
        try:
            await self.send(type="state", state="thinking")
            async for kind, payload in self.brain.respond(text):
                if kind == "status":
                    await self.send(type="status", text=payload)
                    continue
                full_reply.append(payload)
                await self.send(type="text_delta", turn=turn, text=payload)
                for sentence in chunker.feed(payload):
                    enqueue(sentence)
            if tail := chunker.flush():
                enqueue(tail)
            queue.put_nowait(None)
            await speaker_task
            await self.send(type="turn_end", turn=turn)
        except asyncio.CancelledError:
            raise
        except anthropic.AuthenticationError:
            await self.send(type="error", message="Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.")
        except anthropic.APIStatusError as exc:
            log.exception("Claude API error")
            await self.send(type="error", message=f"Claude API error {exc.status_code}: {exc.message}")
        except anthropic.APIConnectionError:
            log.exception("Claude connection error")
            await self.send(type="error", message="I couldn't reach Claude. Check your connection.")
        except Exception as exc:
            log.exception("turn failed")
            await self.send(type="error", message=f"Something went wrong: {exc}")
        finally:
            for task in (speaker_task, *synth_tasks):
                task.cancel()
            if self.transcript and full_reply:
                self.transcript.add("VIPLAV", "".join(full_reply))

    async def run(self) -> None:
        settings = self.brain.settings
        await self.send(
            type="hello",
            voices=self.voice.plan(),
            stt=self.stt.name if self.stt else "browser",
            languages=[{"code": lang.code, "name": lang.name, "locale": lang.locale} for lang in settings.languages],
            user=settings.user_name,
        )
        try:
            while True:
                frame = await self.ws.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                if frame.get("bytes") is not None:
                    audio = frame["bytes"]
                    if self.stt and 0 < len(audio) <= MAX_UTTERANCE_BYTES:
                        await self.cancel_turn()
                        if self.listen_task is None:
                            self.listen_task = asyncio.create_task(self.listen())
                        self.heard.put_nowait(audio)
                    continue
                msg = json.loads(frame.get("text") or "{}")
                kind = msg.get("type")
                if kind == "user_text" and (text := str(msg.get("text", "")).strip()):
                    await self.start_turn(text)
                elif kind == "set_language":
                    lang = msg.get("lang")
                    self.lang_hint = lang if lang in LANGUAGES else None
                elif kind == "interrupt":
                    await self.cancel_turn()
                    await self.send(type="state", state="idle")
                elif kind == "reset":
                    await self.cancel_turn()
                    self.brain.reset()
                    await self.send(type="state", state="idle")
        except WebSocketDisconnect:
            pass
        finally:
            if self.listen_task:
                self.listen_task.cancel()
            await self.cancel_turn()


class RecordingStore:
    """Saves voice recordings in the layout speech-model training tools expect.

    data/recordings/<lang>/wavs/<id>.wav, plus metadata.csv with one line per clip:
    id|text|speaker. This is how a Lambadi dataset gets built, one sentence at a time.
    """

    def __init__(self, root: Path):
        self.root = root

    def save(self, lang: str, text: str, speaker: str, wav: bytes) -> str:
        if lang not in LANGUAGES:
            raise ValueError("unknown language")
        if not wav.startswith(b"RIFF"):
            raise ValueError("audio must be WAV")
        text = " ".join(text.split())
        speaker = re.sub(r"[^\w-]", "", speaker)[:40] or "anonymous"
        if not text or "|" in text:
            raise ValueError("text must be non-empty and contain no '|'")
        folder = self.root / lang
        (folder / "wavs").mkdir(parents=True, exist_ok=True)
        clip_id = f"{lang}_{dt.datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}"
        (folder / "wavs" / f"{clip_id}.wav").write_bytes(wav)
        with (folder / "metadata.csv").open("a", encoding="utf-8") as f:
            f.write(f"{clip_id}|{text}|{speaker}\n")
        return clip_id

    def stats(self) -> dict:
        out = {}
        for meta in sorted(self.root.glob("*/metadata.csv")):
            lines = [l for l in meta.read_text(encoding="utf-8").splitlines() if l.strip()]
            seconds = sum(max(0, p.stat().st_size - 44) / 32000 for p in (meta.parent / "wavs").glob("*.wav"))
            out[meta.parent.name] = {"clips": len(lines), "minutes": round(seconds / 60, 1)}
        return out


def create_app(
    settings: Settings | None = None,
    brain_factory: Callable[[Settings], Brain] | None = None,
    voice: VoiceRouter | None = None,
    stt=None,
) -> FastAPI:
    settings = settings or load_settings()
    brain_factory = brain_factory or Brain
    voice = voice or VoiceRouter.from_spec(settings.tts)
    if stt is None and settings.stt == "whisper":
        stt = WhisperSTT(settings.whisper_model, allowed={lang.voice_lang for lang in settings.languages})
    recordings = RecordingStore(settings.recordings_dir)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        # Load local models before the first conversation rather than during it.
        warm = [asyncio.create_task(voice.warm_up())]
        if stt and hasattr(stt, "warm_up"):
            warm.append(asyncio.create_task(stt.warm_up()))
        yield
        for task in warm:
            task.cancel()
        await voice.aclose()

    app = FastAPI(title="VIPLAV", lifespan=lifespan)

    def authorized(token: str | None) -> bool:
        return not settings.access_token or token == settings.access_token

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/record")
    async def record_page():
        return FileResponse(WEB_DIR / "record.html")

    @app.post("/api/recordings")
    async def save_recording(request: Request):
        if not authorized(request.query_params.get("token")):
            raise HTTPException(401)
        body = await request.json()
        try:
            wav = base64.b64decode(body.get("audio", ""), validate=True)
            clip_id = recordings.save(body.get("lang", ""), body.get("text", ""), body.get("speaker", ""), wav)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": clip_id, "stats": recordings.stats()}

    @app.get("/api/recordings/stats")
    async def recording_stats(request: Request):
        if not authorized(request.query_params.get("token")):
            raise HTTPException(401)
        return recordings.stats()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        if not authorized(ws.query_params.get("token")):
            await ws.close(code=4401)
            return
        await ws.accept()
        transcript = Transcript(settings.transcripts_dir) if settings.transcripts_dir else None
        await VoiceSession(ws, brain_factory(settings), voice, stt, transcript).run()

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    log.info("Mind: %s (effort %s)", settings.model, settings.effort)
    log.info("Languages: %s", ", ".join(lang.name for lang in settings.languages))
    log.info("Voice: %s, listening: %s", settings.tts, settings.stt)
    log.info("Open http://%s:%d in Chrome, Edge or Safari", settings.host, settings.port)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
