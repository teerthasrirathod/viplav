import asyncio

from fastapi.testclient import TestClient

from viplav.app import create_app
from viplav.brain import INTERRUPTED_NOTE, Brain
from viplav.config import load_settings
from viplav.engines.tts import BrowserTTS, VoiceRouter


class FakeBrain(Brain):
    def __init__(self, settings, delay=0.0):
        self.settings = settings
        self.history = []
        self.delay = delay

    async def respond(self, user_text):
        yield "status", "Searching the web…"
        for piece in ["Hello there. ", "It is ", "sunny today."]:
            await asyncio.sleep(self.delay)
            yield "text", piece


class FakeTTS(BrowserTTS):
    name = "fake"
    languages = {"en", "hi"}

    async def synthesize(self, text, lang):
        return f"AUDIO[{lang}:{text}]".encode(), "audio/wav"


def fake_voice():
    return VoiceRouter([FakeTTS(), BrowserTTS()])


def settings(tmp_path):
    from dataclasses import replace

    return replace(load_settings(), transcripts_dir=tmp_path / "tx", recordings_dir=tmp_path / "rec", access_token="")


def collect_turn(ws):
    msgs = []
    while True:
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["type"] in ("turn_end", "error"):
            return msgs


def test_full_turn_streams_text_and_ordered_speech(tmp_path):
    app = create_app(settings(tmp_path), brain_factory=FakeBrain, voice=fake_voice())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["voices"] == {"en": "fake", "hi": "fake", "te": "browser"}
        assert [l["code"] for l in hello["languages"]] == ["en", "hi", "te"]
        ws.send_json({"type": "user_text", "text": "how's the weather"})
        msgs = collect_turn(ws)

    types = [m["type"] for m in msgs]
    assert types[0] == "state" and msgs[0]["state"] == "thinking"
    assert {"type": "status", "text": "Searching the web…"} in msgs
    speech = [m for m in msgs if m["type"] == "speech"]
    assert [s["text"] for s in speech] == ["Hello there.", "It is sunny today."]
    assert [s["seq"] for s in speech] == [0, 1]
    assert all(s["audio"] and s["mime"] == "audio/wav" and s["lang"] == "en" for s in speech)
    assert "".join(m["text"] for m in msgs if m["type"] == "text_delta") == "Hello there. It is sunny today."
    log = next((tmp_path / "tx").glob("*.md")).read_text()
    assert "how's the weather" in log and "It is sunny today." in log


def test_access_token_is_enforced(tmp_path):
    from dataclasses import replace

    app = create_app(replace(settings(tmp_path), access_token="s3cret"), brain_factory=FakeBrain, voice=fake_voice())
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
            raise AssertionError("connection should have been refused")
        except Exception as exc:
            assert "4401" in str(exc) or "WebSocketDisconnect" in type(exc).__name__
        with client.websocket_connect("/ws?token=s3cret") as ws:
            assert ws.receive_json()["type"] == "hello"


def test_index_served(tmp_path):
    app = create_app(settings(tmp_path), brain_factory=FakeBrain, voice=fake_voice())
    with TestClient(app) as client:
        assert "<title>VIPLAV</title>" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200


# ---- Brain against a fake Anthropic stream (no network) ----

class _Block:
    def __init__(self, type, name=None):
        self.type, self.name = type, name


class _Event:
    def __init__(self, type, text=None, content_block=None):
        self.type, self.text, self.content_block = type, text, content_block


class _Message:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


class _Stream:
    def __init__(self, events, message, hang=False):
        self.events, self.message, self.hang = events, message, hang

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for e in self.events:
            yield e
        if self.hang:
            await asyncio.sleep(3600)

    async def get_final_message(self):
        return self.message


class _Client:
    def __init__(self, streams):
        self.calls = []
        self._streams = iter(streams)
        outer = self

        class Messages:
            def stream(self, **kw):
                outer.calls.append({**kw, "messages": list(kw["messages"])})
                return next(outer._streams)

        class Beta:
            messages = Messages()

        self.beta = Beta()


def run(coro):
    return asyncio.run(coro)


def test_brain_request_shape_and_history(tmp_path):
    content = [{"type": "thinking", "thinking": "", "signature": "x"}, {"type": "text", "text": "Hi!"}]
    client = _Client([_Stream([_Event("text", text="Hi!")], _Message("end_turn", content))])
    brain = Brain(settings(tmp_path), client=client)

    async def go():
        return [x async for x in brain.respond("hello")]

    assert run(go()) == [("text", "Hi!")]
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["tools"][0]["type"] == "web_search_20260209"
    assert "temperature" not in call
    assert brain.history == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": content}]


def test_brain_resumes_pause_turn_and_reports_tool_status(tmp_path):
    first = _Stream([_Event("content_block_start", content_block=_Block("server_tool_use", "web_search"))],
                    _Message("pause_turn", ["paused"]))
    second = _Stream([_Event("text", text="Found it.")], _Message("end_turn", ["done"]))
    client = _Client([first, second])
    brain = Brain(settings(tmp_path), client=client)

    async def go():
        return [x async for x in brain.respond("search")]

    assert run(go()) == [("status", "Searching the web…"), ("text", "Found it.")]
    assert [m["role"] for m in brain.history] == ["user", "assistant", "assistant"]
    assert client.calls[1]["messages"][-1] == {"role": "assistant", "content": ["paused"]}


def test_brain_records_partial_reply_when_interrupted(tmp_path):
    client = _Client([
        _Stream([_Event("text", text="Let me think")], _Message("end_turn", []), hang=True),
        _Stream([], _Message("end_turn", []), hang=True),
    ])
    brain = Brain(settings(tmp_path), client=client)

    async def consume():
        async for _ in brain.respond("q"):
            pass

    async def go(after):
        task = asyncio.create_task(consume())
        await asyncio.sleep(after)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run(go(0.05))
    assert brain.history[-1] == {"role": "assistant", "content": "Let me think …"}
    run(go(0.05))
    assert brain.history[-1] == {"role": "assistant", "content": INTERRUPTED_NOTE}
    assert [m["role"] for m in brain.history] == ["user", "assistant", "user", "assistant"]


def test_brain_handles_refusal(tmp_path):
    client = _Client([_Stream([], _Message("refusal", []))])
    brain = Brain(settings(tmp_path), client=client)

    async def go():
        return [x async for x in brain.respond("q")]

    assert run(go())[-1][0] == "text"
    assert brain.history[-1]["role"] == "assistant"


class MixedBrain(FakeBrain):
    async def respond(self, user_text):
        yield "text", "Of course. यह बहुत आसान है, मैं समझाता हूँ. "
        yield "text", "తెలుగులో కూడా చెప్పగలను. "


def test_mixed_language_reply_is_voiced_per_language(tmp_path):
    app = create_app(settings(tmp_path), brain_factory=MixedBrain, voice=fake_voice())
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "explain"})
        speech = [m for m in collect_turn(ws) if m["type"] == "speech"]
    assert [(s["lang"], s["text"]) for s in speech] == [
        ("en", "Of course."),
        ("hi", "यह बहुत आसान है, मैं समझाता हूँ."),
        ("te", "తెలుగులో కూడా చెప్పగలను."),
    ]
    # English and Hindi got the local voice; Telugu falls back to the browser.
    assert [bool(s["audio"]) for s in speech] == [True, True, False]


class FakeSTT:
    name = "whisper"

    def __init__(self):
        self.calls = []

    async def transcribe(self, pcm16, hint=None):
        self.calls.append((len(pcm16), hint))
        return "नमस्ते", "hi"


def test_whisper_path_transcribes_then_answers(tmp_path):
    stt = FakeSTT()
    app = create_app(settings(tmp_path), brain_factory=FakeBrain, voice=fake_voice(), stt=stt)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["stt"] == "whisper"
        ws.send_json({"type": "set_language", "lang": "hi"})
        ws.send_bytes(b"\x00\x01" * 8000)
        assert ws.receive_json() == {"type": "transcript", "text": "नमस्ते", "lang": "hi"}
        msgs = collect_turn(ws)
    assert stt.calls == [(16000, "hi")]
    assert msgs[-1]["type"] == "turn_end"


def _wav(seconds=1.0):
    import io, wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def test_recorder_saves_clip_and_metadata(tmp_path):
    import base64

    app = create_app(settings(tmp_path), brain_factory=FakeBrain, voice=fake_voice())
    with TestClient(app) as client:
        assert "Lambadi" in client.get("/record").text
        res = client.post("/api/recordings", json={
            "lang": "lmn", "text": "  तू कसो छ ?  ", "speaker": "te ertha!", "audio": base64.b64encode(_wav(2)).decode(),
        })
        assert res.status_code == 200, res.text
        assert res.json()["stats"] == {"lmn": {"clips": 1, "minutes": 0.0}}
        bad = client.post("/api/recordings", json={"lang": "lmn", "text": "x", "audio": base64.b64encode(b"nope").decode()})
        assert bad.status_code == 400
    folder = tmp_path / "rec" / "lmn"
    clip_id, text, speaker = (folder / "metadata.csv").read_text(encoding="utf-8").strip().split("|")
    assert text == "तू कसो छ ?" and speaker == "teertha"
    assert (folder / "wavs" / f"{clip_id}.wav").read_bytes().startswith(b"RIFF")
