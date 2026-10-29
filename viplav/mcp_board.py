"""The thinking board as a tiny MCP server, for the subscription brain.

Claude Code starts this over stdio (see claude_code.py), and it offers one tool,
update_board, with the same schema and validation as the API brain's tool. It writes
the same data/board.json, so the web page shows the same board whichever brain is used.

    python -m viplav.mcp_board /path/to/board.json
"""

import json
import sys
from pathlib import Path

from .board import TOOL, Board, InvalidBoardUpdate

SERVER_INFO = {"name": "viplav", "version": "0.1.0"}


def handle(request: dict, board_path: Path) -> dict | None:
    method = request.get("method")
    if "id" not in request:  # a notification, such as notifications/initialized
        return None
    if method == "initialize":
        result = {
            "protocolVersion": request.get("params", {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "tools/list":
        result = {"tools": [{"name": TOOL["name"], "description": TOOL["description"], "inputSchema": TOOL["input_schema"]}]}
    elif method == "tools/call":
        params = request.get("params", {})
        if params.get("name") != TOOL["name"]:
            return _error(request["id"], -32602, f"Unknown tool {params.get('name')}")
        try:
            summary = Board(board_path).apply(params.get("arguments"))
            result = {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False)}]}
        except InvalidBoardUpdate as exc:
            result = {"content": [{"type": "text", "text": f"INVALID_INPUT: {exc}"}], "isError": True}
    elif method == "ping":
        result = {}
    else:
        return _error(request["id"], -32601, f"Method not found: {method}")
    return {"jsonrpc": "2.0", "id": request["id"], "result": result}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main() -> None:
    board_path = Path(sys.argv[1])
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (response := handle(request, board_path)) is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
