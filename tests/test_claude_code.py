"""The subscription brain, against a fake `claude` program that replays stream-json."""

import asyncio
import json
import os
import stat
import sys
import textwrap
from dataclasses import replace

import pytest

from viplav.claude_code import BOARD_TOOL, ClaudeCodeBrain, SubscriptionBrainError

from .test_app import settings

FAKE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    from pathlib import Path
    args = sys.argv[1:]
    prompt = sys.stdin.read()
    log = Path(os.environ["FAKE_LOG"])
    log.write_text(log.read_text() + json.dumps({{"args": args, "prompt": prompt, "has_key": "ANTHROPIC_API_KEY" in os.environ}}) + "\\n" if log.exists() else json.dumps({{"args": args, "prompt": prompt, "has_key": "ANTHROPIC_API_KEY" in os.environ}}) + "\\n")
    mode = os.environ.get("FAKE_MODE", "ok")
    def out(m): print(json.dumps(m), flush=True)
    out({{"type": "system", "subtype": "init", "session_id": "sess-1"}})
    if mode == "unauth":
        out({{"type": "result", "is_error": True, "result": "Not logged in. Please run /login", "session_id": "sess-1"}})
        sys.exit(1)
    out({{"type": "stream_event", "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": "Filed. "}}}}, "parent_tool_use_id": None, "session_id": "sess-1"}})
    out({{"type": "stream_event", "event": {{"type": "content_block_start", "content_block": {{"type": "tool_use", "name": "WebSearch"}}}}, "parent_tool_use_id": None}})
    # The board tool call and its result, as Claude Code reports them.
    board = Path(os.environ["FAKE_BOARD"])
    board.write_text(json.dumps({{"threads": [{{"id": "a", "title": "A", "category": "Study", "status": "open", "summary": "s", "next_step": "", "created": "x", "updated": "y"}}]}}))
    out({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "id": "tu1", "name": "{tool}", "input": {{}}}}]}}}})
    out({{"type": "user", "message": {{"content": [{{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}}]}}}})
    out({{"type": "stream_event", "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": "Next?"}}}}, "parent_tool_use_id": None}})
    out({{"type": "result", "is_error": False, "result": "Filed. Next?", "session_id": "sess-1"}})
''')


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    path = tmp_path / "claude"
    path.write_text(FAKE.format(python=sys.executable, tool=BOARD_TOOL))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("FAKE_BOARD", str(tmp_path / "board.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-claude")
    return path


def run(brain, text):
    async def go():
        return [x async for x in brain.respond(text)]
    return asyncio.run(go())


def calls(tmp_path):
    return [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]


def test_streams_text_status_and_board_then_resumes(tmp_path, fake_claude):
    brain = ClaudeCodeBrain(settings(tmp_path), claude_bin=str(fake_claude))
    events = run(brain, "three things")
    assert events[0] == ("text", "Filed. ")
    assert events[1] == ("status", "Searching the web…")
    assert events[2][0] == "board" and events[2][1]["threads"][0]["category"] == "Study"
    assert events[3] == ("text", "Next?")
    assert brain.session_id == "sess-1"
    run(brain, "and another")
    first, second = calls(tmp_path)
    assert first["prompt"] == "three things" and not first["has_key"]  # plan login, never the API key
    args = first["args"]
    assert args[args.index("--system-prompt") + 1].startswith("You are VIPLAV")
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert BOARD_TOOL in args[args.index("--allowedTools") + 1]
    assert "--resume" not in args and second["args"][second["args"].index("--resume") + 1] == "sess-1"


def test_reset_starts_a_fresh_conversation(tmp_path, fake_claude):
    brain = ClaudeCodeBrain(settings(tmp_path), claude_bin=str(fake_claude))
    run(brain, "one")
    brain.reset()
    run(brain, "two")
    assert "--resume" not in calls(tmp_path)[1]["args"]


def test_not_signed_in_gives_a_plain_message(tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "unauth")
    brain = ClaudeCodeBrain(settings(tmp_path), claude_bin=str(fake_claude))
    with pytest.raises(SubscriptionBrainError, match="isn't signed in"):
        run(brain, "hi")


def test_missing_claude_program_is_explained(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SubscriptionBrainError, match="isn't installed"):
        ClaudeCodeBrain(settings(tmp_path))
