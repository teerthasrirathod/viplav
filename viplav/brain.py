"""VIPLAV's mind: Claude, in one conversation streamed turn by turn."""

import datetime as dt
import json
from collections.abc import AsyncIterator

import anthropic

from . import board as board_mod
from .board import Board, InvalidBoardUpdate
from .config import Settings
from .languages import language_prompt

VOICE_PROMPT = """\
You are VIPLAV, a voice companion. Underneath, you are Claude, made by Anthropic. VIPLAV \
is the name and the face; the mind, judgment and values are Claude's. If asked what you \
are, say exactly that. You are talking with the user out loud. Everything you write is \
converted to speech the moment you write it, and the user listens rather than reads. Hold \
yourself to the same standard of accuracy, judgment and care you would in writing; only \
the delivery changes.

How to sound:
- Write for the ear. Plain spoken sentences only: no markdown, bullet points, headings, \
tables, emoji or URLs. If structure helps, say it ("Three things. First, ...").
- Lead with the answer. Your first sentence starts playing before you've written the \
second, so make it carry the point.
- Match length to the question. A quick question gets one to three sentences. Go longer \
when the user asks for depth or the topic genuinely needs it, and offer to go deeper \
rather than front-loading everything.
- Be direct, warm and precise, like a sharp colleague. Skip filler such as "Great \
question" or restating what they said. Disagree when you think they're wrong, and say \
plainly when you're unsure or don't know.
- Say numbers, units, symbols and abbreviations the way a person would read them aloud \
when the written form would be ambiguous.
- If the user asks for code or something meant to be read, give it in a fenced code \
block and say in one spoken sentence what it does; the block appears on their screen \
and is not read aloud.

About what you hear:
- The user's words come from speech recognition and may contain misheard words, \
missing punctuation, or a sentence cut short. Infer what they meant. If it's genuinely \
ambiguous and the difference matters, ask one short clarifying question.
- The user can interrupt you. If a turn of yours ends early, don't repeat it; pick up \
from what they say next.
- You can search and read the web. Use it for anything current or that you'd otherwise \
be guessing at, and mention briefly that you're checking.\
"""


def build_system_prompt(settings: Settings, board: Board | None = None) -> str:
    parts = [VOICE_PROMPT, language_prompt(list(settings.languages)), board_mod.BOARD_PROMPT]
    if settings.user_name:
        parts.append(f"The user's name is {settings.user_name}.")
    if settings.profile_path.is_file():
        profile = settings.profile_path.read_text().strip()
        if profile:
            parts.append(
                "Notes the user wrote about themselves, to keep in mind:\n"
                f"<about_user>\n{profile}\n</about_user>"
            )
    if board and (snapshot := board.prompt_snapshot()):
        parts.append(snapshot)
    parts.append(f"Today's date is {dt.date.today():%A, %B %-d, %Y}.")
    return "\n\n".join(parts)


INTERRUPTED_NOTE = "(The user interrupted before I said anything.)"
REFUSAL_LINE = "I'm not able to help with that one."


class Brain:
    """Holds the conversation history and streams Claude's replies.

    `respond` yields ("text", delta) as Claude writes, ("status", message) when it
    starts searching the web, and ("board", board) whenever the thinking board changes.
    """

    def __init__(self, settings: Settings, client: anthropic.AsyncAnthropic | None = None, board: Board | None = None):
        self.settings = settings
        self.client = client or anthropic.AsyncAnthropic()
        self.board = board or Board(settings.board_path)
        self.system = build_system_prompt(settings, self.board)
        self.history: list = []

    def reset(self) -> None:
        self.history = []

    def _request(self) -> dict:
        s = self.settings
        params: dict = {
            "model": s.model,
            "max_tokens": s.max_tokens,
            "system": self.system,
            "messages": self.history,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": s.effort},
            # Caches the system prompt and conversation so each turn only pays for what's new.
            "cache_control": {"type": "ephemeral"},
        }
        params["tools"] = [board_mod.TOOL]
        if s.web_search:
            params["tools"] += [
                {"type": "web_search_20260209", "name": "web_search", "max_uses": 4},
                {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 3},
            ]
        if s.fast_mode:
            params["betas"] = ["fast-mode-2026-02-01"]
            params["speed"] = "fast"
        else:
            # If a safety classifier declines, the API retries on a suitable model
            # in the same call instead of returning a dead turn.
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    async def respond(self, user_text: str) -> AsyncIterator[tuple[str, object]]:
        self.history.append({"role": "user", "content": user_text})
        said: list[str] = []
        turn_open = True  # False once a complete assistant message is in history
        json_retries = 0
        cutoffs = 0
        try:
            while True:
                try:
                    async with self.client.beta.messages.stream(**self._request()) as stream:
                        async for event in stream:
                            if event.type == "text":
                                said.append(event.text)
                                yield "text", event.text
                            elif event.type == "content_block_start":
                                block = event.content_block
                                if block.type == "server_tool_use":
                                    yield "status", _tool_status(block.name)
                        message = await stream.get_final_message()
                except ValueError:
                    # A board update streamed as JSON the SDK couldn't parse at all. It
                    # broke before the tool call completed, so re-issue the turn (bounded).
                    json_retries += 1
                    if json_retries > 2:
                        raise
                    continue
                json_retries = 0

                if message.stop_reason == "refusal":
                    self.history.append({"role": "assistant", "content": REFUSAL_LINE})
                    turn_open = False
                    yield "text", ("\n\n" if said else "") + REFUSAL_LINE
                    return
                # Append the full content (thinking, tool use, text) unchanged so the
                # next request continues exactly where this one left off.
                self.history.append({"role": "assistant", "content": message.content})
                turn_open = False
                tool_uses = [b for b in message.content if b.type == "tool_use"]
                if tool_uses and message.stop_reason in ("tool_use", "max_tokens"):
                    if message.stop_reason == "max_tokens":
                        # Cut off mid-call: a partial input parses as valid, so never run it.
                        cutoffs += 1
                        if cutoffs > 2:
                            raise RuntimeError("board update kept getting cut off")
                        results = [_cut_off(b) for b in tool_uses]
                    else:
                        results = [self._run_tool(b) for b in tool_uses]
                    self.history.append({"role": "user", "content": results})
                    if not any(r.get("is_error") for r in results):
                        yield "board", self.board.to_dict()
                    turn_open = True
                    said = []
                    continue
                if message.stop_reason != "pause_turn":
                    return
                # A long server-side search paused the turn; send it back to resume.
                turn_open = True
                said = []
        finally:
            # Interrupted (user barged in) or failed mid-stream: record only what was
            # actually said, so the transcript stays truthful and strictly alternating.
            if turn_open:
                spoken = "".join(said).strip()
                if self.history and self.history[-1]["role"] == "user":
                    self.history.append(
                        {"role": "assistant", "content": spoken + " …" if spoken else INTERRUPTED_NOTE}
                    )

    def _run_tool(self, block) -> dict:
        result = {"type": "tool_result", "tool_use_id": block.id}
        if block.name != "update_board":
            return {**result, "is_error": True, "content": f"Unknown tool {block.name}"}
        try:
            summary = self.board.apply(block.input)
        except InvalidBoardUpdate as exc:
            # Includes inputs the tolerant stream parser cut short: let Claude resend them.
            return {**result, "is_error": True, "content": json.dumps({"INVALID_INPUT": str(exc)})}
        return {**result, "content": json.dumps(summary, ensure_ascii=False)}


def _cut_off(block) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "is_error": True,
        "content": "The call was cut off before it finished. Send a smaller update.",
    }


def _tool_status(name: str) -> str:
    return {
        "web_search": "Searching the web…",
        "web_fetch": "Reading a page…",
    }.get(name, "Working on it…")
