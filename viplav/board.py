"""The thinking board: every thread of a conversation, grouped and kept up to date.

When you think out loud across ten things at once, VIPLAV files each one as a thread:
a title, a category, a status, what's been said, and the next step. The board is shown
live beside the face, saved after every change (data/board.json, data/board.md), and
read back at the start of the next session, so threads carry over between days.
"""

import datetime as dt
import json
from pathlib import Path

STATUSES = ("open", "exploring", "decided", "action", "waiting", "parked", "done")

TOOL = {
    "name": "update_board",
    "description": (
        "Keep the user's thinking board up to date. The board holds every thread the user "
        "is thinking about, grouped by category. Call this quietly whenever a new topic comes "
        "up, a thread moves forward (an idea refined, a decision made, a next step agreed), "
        "or the user asks to rename, regroup, park or finish something. Send only the threads "
        "that changed; existing threads are matched by id. Several updates in one call is best."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "threads": {
                "type": "array",
                "description": "Threads to add or update.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Short stable slug, e.g. 'viplav-launch'. Reuse it to update."},
                        "title": {"type": "string", "description": "A few words, in the user's language mix."},
                        "category": {"type": "string", "description": "A broad group, e.g. Projects, Company, Study, Ideas, Personal, Family. Reuse existing categories where they fit."},
                        "status": {"type": "string", "enum": list(STATUSES)},
                        "summary": {"type": "string", "description": "One or two sentences: where this thread stands now."},
                        "next_step": {"type": "string", "description": "The next concrete action, or empty if none."},
                    },
                    "required": ["id", "title", "category", "status", "summary", "next_step"],
                    "additionalProperties": False,
                },
            },
            "remove_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids of threads the user wants deleted outright (not just done).",
            },
        },
        "required": ["threads"],
        "additionalProperties": False,
    },
    # Inputs stream as they're generated; Board.apply validates them before use.
    "eager_input_streaming": True,
}

BOARD_PROMPT = """\
Thinking board: the user thinks out loud across many threads at once (projects, a company, \
study, family, ideas) and jumps between them. Keep their board with update_board as you go:
- When a new topic appears, add it as a thread. When several come at once, file them all \
in one call, then respond to the substance.
- Group threads into a handful of broad categories. Reuse categories, and don't create one \
for each thread.
- Update a thread whenever it moves: refined, decided, given a next step, parked or done.
- Do the bookkeeping silently. Don't narrate it ("I've added that to the board"). If the \
user asks what's on the board or where things stand, answer from it in speech, briefly.
- When the user jumps back to an earlier thread, pick it up from its summary without \
making them repeat themselves.\
"""


class InvalidBoardUpdate(ValueError):
    pass


class Board:
    def __init__(self, path: Path):
        self.path = path
        self.threads: dict[str, dict] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.threads = {t["id"]: t for t in data.get("threads", [])}
            except (json.JSONDecodeError, KeyError, TypeError):
                self.threads = {}

    def apply(self, update) -> dict:
        """Validate and apply one update_board call. Returns a short summary of what changed."""
        if not isinstance(update, dict) or not isinstance(update.get("threads"), list):
            raise InvalidBoardUpdate("expected {'threads': [...]}")
        changes = []
        for item in update["threads"]:
            thread = self._validate(item)
            now = dt.datetime.now().isoformat(timespec="seconds")
            previous = self.threads.get(thread["id"])
            thread["created"] = previous["created"] if previous else now
            thread["updated"] = now
            self.threads[thread["id"]] = thread
            changes.append(("updated " if previous else "added ") + thread["id"])
        for thread_id in update.get("remove_ids") or []:
            if isinstance(thread_id, str) and self.threads.pop(thread_id, None):
                changes.append("removed " + thread_id)
        self.save()
        return {"changes": changes, "thread_count": len(self.threads)}

    @staticmethod
    def _validate(item) -> dict:
        fields = ("id", "title", "category", "status", "summary", "next_step")
        if not isinstance(item, dict) or not all(isinstance(item.get(f), str) for f in fields):
            raise InvalidBoardUpdate(f"each thread needs string fields {', '.join(fields)}")
        if item["status"] not in STATUSES:
            raise InvalidBoardUpdate(f"status must be one of {', '.join(STATUSES)}")
        if not item["id"].strip() or not item["title"].strip():
            raise InvalidBoardUpdate("id and title can't be empty")
        thread = {f: item[f].strip() for f in fields}
        thread["category"] = thread["category"] or "Other"
        return thread

    def to_dict(self) -> dict:
        return {"threads": sorted(self.threads.values(), key=lambda t: (t["category"].lower(), t["created"]))}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.path.with_suffix(".md").write_text(self.to_markdown(), encoding="utf-8")

    def to_markdown(self) -> str:
        lines = [f"# Thinking board ({dt.date.today():%B %-d, %Y})", ""]
        category = None
        for t in self.to_dict()["threads"]:
            if t["category"] != category:
                if category is not None:
                    lines.append("")
                category = t["category"]
                lines += [f"## {category}", ""]
            lines.append(f"- **{t['title']}** ({t['status']}): {t['summary']}")
            if t["next_step"]:
                lines.append(f"  - Next: {t['next_step']}")
        return "\n".join(lines) + "\n"

    def prompt_snapshot(self) -> str:
        """The board as it stood when this session began, for the system prompt."""
        live = [t for t in self.to_dict()["threads"] if t["status"] != "done"]
        if not live:
            return ""
        rows = [
            f"- [{t['id']}] {t['category']} / {t['title']} ({t['status']}): {t['summary']}"
            + (f" Next: {t['next_step']}" if t["next_step"] else "")
            for t in live
        ]
        return "The board carried over from earlier sessions (ids in brackets):\n" + "\n".join(rows)
