"""Runtime settings, read from environment variables (or a .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path

from .languages import Language, parse_languages

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the app runs without extra dependencies."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    model: str
    effort: str
    fast_mode: bool
    web_search: bool
    max_tokens: int
    user_name: str
    languages: tuple[Language, ...]
    tts: str
    stt: str
    whisper_model: str
    profile_path: Path
    transcripts_dir: Path
    recordings_dir: Path
    board_path: Path
    access_token: str
    host: str
    port: int


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    env = os.environ.get
    return Settings(
        model=env("VIPLAV_MODEL", "claude-opus-5-5"),
        effort=env("VIPLAV_EFFORT", "medium"),
        fast_mode=_flag("VIPLAV_FAST_MODE"),
        web_search=_flag("VIPLAV_WEB_SEARCH", True),
        max_tokens=int(env("VIPLAV_MAX_TOKENS", "16000")),
        user_name=env("VIPLAV_USER_NAME", "").strip(),
        languages=tuple(parse_languages(env("VIPLAV_LANGUAGES", "en,hi,te"), env("VIPLAV_LAMBADI_SCRIPT", "Devanagari"))),
        tts=env("VIPLAV_TTS", "browser"),
        stt=env("VIPLAV_STT", "browser"),
        whisper_model=env("VIPLAV_WHISPER_MODEL", "large-v3-turbo"),
        profile_path=Path(env("VIPLAV_PROFILE", ROOT / "data" / "profile.md")),
        transcripts_dir=Path(env("VIPLAV_TRANSCRIPTS", ROOT / "data" / "transcripts")),
        recordings_dir=Path(env("VIPLAV_RECORDINGS", ROOT / "data" / "recordings")),
        board_path=Path(env("VIPLAV_BOARD", ROOT / "data" / "board.json")),
        access_token=env("VIPLAV_ACCESS_TOKEN", "").strip(),
        host=env("VIPLAV_HOST", "127.0.0.1"),
        port=int(env("VIPLAV_PORT", "8765")),
    )
