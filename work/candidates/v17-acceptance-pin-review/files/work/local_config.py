"""Load project-local paths without putting machine-specific values in source.

The repository publishes ``local.env.example``.  Each developer copies it to
``local.env`` and fills in paths for their own EU4 installation and toolchain.
The real file is ignored by Git.  Process environment variables take
precedence over values from the file, which makes CI and one-off overrides
straightforward.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV = PROJECT_ROOT / "local.env"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_local_env(path: Path = LOCAL_ENV) -> dict[str, str]:
    """Read a small ``KEY=VALUE`` file without requiring python-dotenv."""

    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not _KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid local.env entry at line {line_number}: {raw_line!r}")
        values[key] = _unquote(value.strip())
    return values


def load_local_env(path: Path = LOCAL_ENV) -> dict[str, str]:
    """Load local values into the process without overriding explicit env vars."""

    values = read_local_env(path)
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def get_value(name: str, *, required: bool = True, default: str | None = None) -> str | None:
    """Return a configured value, preferring the process environment."""

    load_local_env()
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Missing {name}. Copy local.env.example to local.env and configure it, "
            "or set the environment variable explicitly."
        )
    return value


def get_path(name: str, *, required: bool = True, default: str | None = None) -> Path | None:
    """Return a configured filesystem path."""

    value = get_value(name, required=required, default=default)
    return Path(value).expanduser() if value else None


def game_root() -> Path:
    return get_path("EU4_GAME_ROOT")  # type: ignore[return-value]


def game_exe() -> Path:
    return game_root() / "eu4.exe"


def user_data() -> Path:
    return get_path("EU4_USER_DATA")  # type: ignore[return-value]
