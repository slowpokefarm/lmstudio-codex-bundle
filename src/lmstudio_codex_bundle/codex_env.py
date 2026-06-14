#!/usr/bin/env python3
"""Helpers for loading per-user Codex environment variables."""

from __future__ import annotations

import os
import shlex
from pathlib import Path


DEFAULT_ENV_PATH = Path.home() / ".codex" / ".env"


def load_codex_env(path: Path | None = None, override: bool = False) -> Path | None:
    env_path = (path or DEFAULT_ENV_PATH).expanduser()
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value:
            value = shlex.split(value)[0] if value[0] in {'"', "'"} else value
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path
