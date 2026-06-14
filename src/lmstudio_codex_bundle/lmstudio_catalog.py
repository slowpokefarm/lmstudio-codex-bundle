#!/usr/bin/env python3
"""Standalone LM Studio catalog helpers."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from lmstudio_codex_bundle.catalog_common import (
    BASE_INSTRUCTIONS,
    DEFAULT_TRUNCATION_POLICY,
    REASONING_LEVELS,
    load_catalog,
    save_catalog,
)
from lmstudio_codex_bundle.codex_env import load_codex_env


DEFAULT_CATALOG_PATH = Path.home() / ".codex" / "model-catalog.local.json"
DEFAULT_INVENTORY_URL = "http://127.0.0.1:1234/api/v0/models?q="
DEFAULT_ENDPOINT_ENV_VAR = "LMSTUDIO_INVENTORY_URL"


def resolve_inventory_url(explicit_url: str | None = None) -> str:
    if explicit_url:
        stripped = explicit_url.strip()
        if stripped:
            return stripped
    load_codex_env()
    env_value = os.environ.get(DEFAULT_ENDPOINT_ENV_VAR, "").strip()
    return env_value or DEFAULT_INVENTORY_URL


def fetch_inventory(url: str | None = None) -> list[dict[str, Any]]:
    resolved_url = resolve_inventory_url(url)
    with urlopen(resolved_url, timeout=30) as response:
        payload = json.load(response)
    return payload["data"]


def infer_input_modalities(model: dict[str, Any]) -> list[str]:
    if model.get("type") == "vlm":
        return ["text", "image"]
    return ["text"]


def build_description(model: dict[str, Any]) -> str:
    publisher = model.get("publisher", "unknown")
    arch = model.get("arch", "unknown")
    quant = model.get("quantization", "unknown")
    ctx = model.get("max_context_length", "unknown")
    tool_use = (
        "tool_use capable"
        if "tool_use" in model.get("capabilities", [])
        else "no tool_use flag"
    )
    return (
        f"LM Studio local model: {publisher} {arch}, {quant}, {ctx} context, "
        f"{tool_use}."
    )


def build_entry(
    model: dict[str, Any], existing: dict[str, Any] | None, priority: int
) -> dict[str, Any]:
    context_window = (
        existing.get("context_window", model.get("max_context_length"))
        if existing
        else model.get("max_context_length")
    )
    max_context_window = (
        existing.get("max_context_window", context_window)
        if existing
        else context_window
    )
    return {
        "slug": model["id"],
        "display_name": model["id"],
        "description": build_description(model),
        "default_reasoning_level": (
            existing.get("default_reasoning_level", "medium")
            if existing
            else "medium"
        ),
        "supported_reasoning_levels": (
            deepcopy(existing.get("supported_reasoning_levels", REASONING_LEVELS))
            if existing
            else deepcopy(REASONING_LEVELS)
        ),
        "shell_type": (
            existing.get("shell_type", "shell_command")
            if existing
            else "shell_command"
        ),
        "visibility": existing.get("visibility", "list") if existing else "list",
        "supported_in_api": (
            existing.get("supported_in_api", True) if existing else True
        ),
        "priority": priority,
        "availability_nux": existing.get("availability_nux") if existing else None,
        "upgrade": existing.get("upgrade") if existing else None,
        "base_instructions": (
            existing.get("base_instructions", BASE_INSTRUCTIONS)
            if existing
            else BASE_INSTRUCTIONS
        ),
        "supports_reasoning_summaries": (
            existing.get("supports_reasoning_summaries", True) if existing else True
        ),
        "default_reasoning_summary": (
            existing.get("default_reasoning_summary", "auto")
            if existing
            else "auto"
        ),
        "support_verbosity": (
            existing.get("support_verbosity", False) if existing else False
        ),
        "default_verbosity": existing.get("default_verbosity") if existing else None,
        "apply_patch_tool_type": (
            existing.get("apply_patch_tool_type", "freeform")
            if existing
            else "freeform"
        ),
        "truncation_policy": (
            deepcopy(existing.get("truncation_policy", DEFAULT_TRUNCATION_POLICY))
            if existing
            else deepcopy(DEFAULT_TRUNCATION_POLICY)
        ),
        "supports_parallel_tool_calls": (
            existing.get("supports_parallel_tool_calls", False) if existing else False
        ),
        "experimental_supported_tools": (
            deepcopy(existing.get("experimental_supported_tools", []))
            if existing
            else []
        ),
        "context_window": context_window,
        "max_context_window": max_context_window,
        "input_modalities": (
            deepcopy(existing.get("input_modalities", infer_input_modalities(model)))
            if existing
            else infer_input_modalities(model)
        ),
    }


def sync_catalog(
    inventory: list[dict[str, Any]],
    existing_models: list[dict[str, Any]],
    prune: bool,
) -> list[dict[str, Any]]:
    existing_by_slug = {model["slug"]: model for model in existing_models}
    selected = [model for model in inventory if model.get("type") != "embeddings"]
    selected.sort(key=lambda model: model["id"])

    synced: list[dict[str, Any]] = []
    for index, model in enumerate(selected, start=1):
        synced.append(build_entry(model, existing_by_slug.get(model["id"]), index * 10))

    if not prune:
        present = {model["slug"] for model in synced}
        for model in existing_models:
            if model["slug"] not in present:
                synced.append(deepcopy(model))

    return synced


def build_status_maps(
    inventory: list[dict[str, Any]], catalog_models: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    inventory_by_slug = {
        model["id"]: model for model in inventory if model.get("type") != "embeddings"
    }
    catalog_by_slug = {model["slug"]: model for model in catalog_models}
    all_slugs = sorted(set(inventory_by_slug) | set(catalog_by_slug))
    statuses = {}
    for slug in all_slugs:
        if slug in inventory_by_slug and slug in catalog_by_slug:
            statuses[slug] = "both"
        elif slug in inventory_by_slug:
            statuses[slug] = "inventory"
        else:
            statuses[slug] = "catalog"
    return inventory_by_slug, statuses
