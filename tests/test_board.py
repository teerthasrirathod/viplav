import asyncio
import json
from types import SimpleNamespace as NS

import pytest

from viplav.board import Board, InvalidBoardUpdate
from viplav.brain import Brain, build_system_prompt

from .test_app import _Client, _Event, _Message, _Stream, settings


def thread(id, category="Projects", status="open", **kw):
    return {"id": id, "title": kw.get("title", id.title()), "category": category, "status": status,
            "summary": kw.get("summary", "Just started."), "next_step": kw.get("next_step", "")}


def test_board_upserts_removes_and_saves(tmp_path):
    board = Board(tmp_path / "board.json")
    assert board.apply({"threads": [thread("viplav"), thread("company", "Company")]}) == {
        "changes": ["added viplav", "added company"], "thread_count": 2}
    created = board.threads["viplav"]["created"]
    board.apply({"threads": [thread("viplav", status="decided", next_step="Push to GitHub")], "remove_ids": ["company"]})
    assert list(board.threads) == ["viplav"]
    assert board.threads["viplav"]["created"] == created and board.threads["viplav"]["status"] == "decided"
    # Persisted, and readable by a fresh session.
    again = Board(tmp_path / "board.json")
    assert again.threads["viplav"]["next_step"] == "Push to GitHub"
    md = (tmp_path / "board.md").read_text(encoding="utf-8")
    assert "## Projects" in md and "Next: Push to GitHub" in md


def test_board_rejects_bad_updates(tmp_path):
    board = Board(tmp_path / "b.json")
    for bad in [None, {"threads": "x"}, {"threads": [{"id": "a"}]}, {"threads": [thread("a", status="someday")]},
                {"threads": [thread(" ", title="")]}]:
        with pytest.raises(InvalidBoardUpdate):
            board.apply(bad)
    assert board.threads == {}


def test_carried_over_board_is_in_the_prompt(tmp_path):
    s = settings(tmp_path)
    board = Board(s.board_path)
    board.apply({"threads": [thread("viplav", summary="Voice app built."), thread("old", status="done")]})
    prompt = build_system_prompt(s, Board(s.board_path))
    assert "[viplav] Projects / Viplav (open): Voice app built." in prompt
    assert "[old]" not in prompt  # finished threads don't clutter the prompt
    assert "Thinking board:" in prompt


def tool_use(id, input):
    return NS(type="tool_use", id=id, name="update_board", input=input)


def run_turn(brain, text="ten things"):
    async def go():
        return [x async for x in brain.respond(text)]
    return asyncio.run(go())


def test_brain_files_threads_then_keeps_talking(tmp_path):
    update = {"threads": [thread("viplav"), thread("company", "Company"), thread("thesis", "Study")]}
    client = _Client([
        _Stream([_Event("text", text="Three big ones. ")], _Message("tool_use", [NS(type="text", text="Three big ones. "), tool_use("t1", update)])),
        _Stream([_Event("text", text="Let's start with the company.")], _Message("end_turn", [NS(type="text")])),
    ])
    brain = Brain(settings(tmp_path), client=client)
    events = run_turn(brain)
    kinds = [k for k, _ in events]
    assert kinds == ["text", "board", "text"]
    assert [t["category"] for t in events[1][1]["threads"]] == ["Company", "Projects", "Study"]
    assert [m["role"] for m in brain.history] == ["user", "assistant", "user", "assistant"]
    result = brain.history[2]["content"][0]
    assert result["tool_use_id"] == "t1" and "is_error" not in result
    assert json.loads(result["content"])["thread_count"] == 3


def test_brain_reports_invalid_update_back_to_claude(tmp_path):
    client = _Client([
        _Stream([], _Message("tool_use", [tool_use("t1", {"threads": [{"id": "x"}]})])),
        _Stream([], _Message("end_turn", [NS(type="text")])),
    ])
    brain = Brain(settings(tmp_path), client=client)
    assert [k for k, _ in run_turn(brain)] == []  # no board event for a rejected update
    result = brain.history[2]["content"][0]
    assert result["is_error"] is True and "INVALID_INPUT" in result["content"]
    assert brain.board.threads == {}


def test_brain_never_runs_a_cut_off_call(tmp_path):
    client = _Client([
        _Stream([], _Message("max_tokens", [tool_use("t1", {"threads": [thread("half")]})])),
        _Stream([], _Message("end_turn", [NS(type="text")])),
    ])
    brain = Brain(settings(tmp_path), client=client)
    run_turn(brain)
    assert brain.board.threads == {}
    assert brain.history[2]["content"][0]["is_error"] is True
