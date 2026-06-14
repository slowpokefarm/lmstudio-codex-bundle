#!/usr/bin/env python3
"""Shared catalog helpers used by the standalone LM Studio bundle."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


BASE_INSTRUCTIONS = (
    "You are Codex, a pragmatic coding agent. Work directly in the user's "
    "repository, inspect before changing, use available tools carefully, prefer "
    "precise minimal edits, and stay on task until the request is handled end to end."
)
REASONING_LEVELS = [
    {"effort": "low", "description": "Lower reasoning depth for faster turns."},
    {
        "effort": "medium",
        "description": "Balanced reasoning depth for normal coding work.",
    },
    {"effort": "high", "description": "Higher reasoning depth for harder tasks."},
]
DEFAULT_TRUNCATION_POLICY = {"mode": "tokens", "limit": 12000}


def load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("models", [])


def create_backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.{timestamp}.bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def save_catalog(
    path: Path, models: list[dict[str, Any]], create_backup_copy: bool = True
) -> Path | None:
    backup = create_backup(path) if create_backup_copy else None
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return backup


def diff_catalogs(
    original_models: list[dict[str, Any]], updated_models: list[dict[str, Any]]
) -> dict[str, Any]:
    original_by_slug = {model["slug"]: model for model in original_models}
    updated_by_slug = {model["slug"]: model for model in updated_models}
    original_slugs = set(original_by_slug)
    updated_slugs = set(updated_by_slug)

    added = sorted(updated_slugs - original_slugs)
    removed = sorted(original_slugs - updated_slugs)
    modified: list[dict[str, Any]] = []

    for slug in sorted(original_slugs & updated_slugs):
        before = original_by_slug[slug]
        after = updated_by_slug[slug]
        changes = []
        keys = sorted(set(before) | set(after))
        for key in keys:
            if before.get(key) != after.get(key):
                changes.append(
                    {
                        "field": key,
                        "before": deepcopy(before.get(key)),
                        "after": deepcopy(after.get(key)),
                    }
                )
        if changes:
            modified.append({"slug": slug, "changes": changes})

    return {"added": added, "removed": removed, "modified": modified}
