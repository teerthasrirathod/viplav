"""The subscription brain: VIPLAV's mind runs through the official Claude Code program.

Signed in with your own Claude plan (`claude` then /login, once), this costs nothing
beyond the plan you already pay for. Each turn draws on your plan's usage limits, just
like using Claude Code yourself. Anthropic's terms allow this for your own, ordinary,
individual use of the unmodified `claude` program; see docs/COST.md.

Each turn runs `claude -p` with VIPLAV's voice prompt in place of Claude Code's own, and
only three tools: web search, web fetch, and the thinking board (an MCP server). Earlier
turns are carried with --resume, so Claude Code keeps the conversation.
"""

import asyncio
import contextlib
import json
import logging
import os
import shutil
import signal
import sys
from collections.abc import AsyncIterator

from .board import Board
from .brain import build_system_prompt
from .config import ROOT, Settings

log = logging.getLogger("viplav.claude_code")

BOARD_TOOL = "mcp__viplav__update_board"
_STATUS = {"WebSearch": "Searching the web…", "WebFetch": "Reading a page…"}
_PARENT_SESSION_VARS = (
    "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID", "CLAUDE_EFFORT",
)


class SubscriptionBrainError(RuntimeError):
    pass


class ClaudeCodeBrain:
    """Same interface as brain.Brain: respond() yields ("text"|"status"|"board", payload)."""

    def __init__(self, settings: Settings, claude_bin: str | None = None):
        self.settings = settings
        self.board = Board(settings.board_path)
        self.system = build_system_prompt(settings, self.board)
        self.claude_bin = claude_bin or shutil.which("claude")
        if not self.claude_bin:
            raise SubscriptionBrainError(
                "The `claude` program isn't installed. Install Claude Code (https://code.claude.com), "
                "run `claude` once to sign in with your Claude plan, or set VIPLAV_BRAIN=api."
            )
        self.session_id: str | None = None
        self.workdir = settings.board_path.parent / "brain"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.history: list = []  # unused: Claude Code keeps the conversation

    def reset(self) -> None:
        self.session_id = None

    def command(self) -> list[str]:
        s = self.settings
        mcp = {"mcpServers": {"viplav": {"command": sys.executable, "args": ["-m", "viplav.mcp_board", str(s.board_path)]}}}
        tools = ["WebSearch", "WebFetch"] if s.web_search else []
        cmd = [
            self.claude_bin, "-p",
            "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--system-prompt", self.system,
            "--tools", ",".join(tools),
            "--mcp-config", json.dumps(mcp),
            "--strict-mcp-config",
            "--allowedTools", ",".join([BOARD_TOOL, *tools]),
            # Anything not allowed above is refused, never waits for a prompt.
            "--permission-mode", "dontAsk",
            "--effort", s.effort,
        ]
        if s.subscription_model:
            cmd += ["--model", s.subscription_model]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        return cmd

    def _env(self) -> dict:
        env = dict(os.environ)
        # An API key in the environment would quietly take priority over the plan login.
        env.pop("ANTHROPIC_API_KEY", None)
        # If VIPLAV itself was started from inside a Claude Code session, don't let the
        # brain attach to that session: VIPLAV's conversation is its own.
        for name in _PARENT_SESSION_VARS:
            env.pop(name, None)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        return env

    async def respond(self, user_text: str) -> AsyncIterator[tuple[str, object]]:
        proc = await asyncio.create_subprocess_exec(
            *self.command(),
            cwd=self.workdir,
            env=self._env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
        proc.stdin.write(user_text.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        board_calls: set[str] = set()
        result = None
        try:
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if msg.get("session_id"):
                    self.session_id = msg["session_id"]
                if kind == "stream_event":
                    event = msg.get("event", {})
                    if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                        if msg.get("parent_tool_use_id") is None:
                            yield "text", event["delta"]["text"]
                    elif event.get("type") == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use" and block.get("name") in _STATUS:
                            yield "status", _STATUS[block["name"]]
                elif kind == "assistant":
                    for block in msg.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use" and block.get("name") == BOARD_TOOL:
                            board_calls.add(block.get("id"))
                elif kind == "user":
                    for block in msg.get("message", {}).get("content", []) or []:
                        if isinstance(block, dict) and block.get("tool_use_id") in board_calls and not block.get("is_error"):
                            self.board = Board(self.settings.board_path)
                            yield "board", self.board.to_dict()
                elif kind == "result":
                    result = msg
            await proc.wait()
        except BaseException:
            # Interrupted: SIGINT lets Claude Code end the turn cleanly and save it.
            if proc.returncode is None:
                # Windows has no SIGINT for child processes; there it goes straight to kill below.
                with contextlib.suppress(ProcessLookupError, ValueError, OSError):
                    proc.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(proc.wait(), 5)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
            raise
        if result is None or result.get("is_error"):
            detail = (result or {}).get("result") or (await proc.stderr.read()).decode(errors="replace").strip()
            raise SubscriptionBrainError(_explain(detail))


def _explain(detail: str) -> str:
    lowered = detail.lower()
    if "log in" in lowered or "login" in lowered or "authenticat" in lowered:
        return "Claude Code isn't signed in. Run `claude` in a terminal once, sign in with your Claude plan, then try again."
    if "usage limit" in lowered or "rate limit" in lowered:
        return "Your Claude plan's usage limit is reached for now. It resets after a while; VIPLAV will work again then."
    return f"Claude Code stopped with an error: {detail[:300]}"
