#!/usr/bin/env python3
"""Bootstrap helpers for the standalone LM Studio Codex bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shlex import quote, split
from urllib.parse import urlparse, urlunparse

from lmstudio_codex_bundle.lmstudio_catalog import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_ENDPOINT_ENV_VAR,
    DEFAULT_INVENTORY_URL,
    load_catalog,
    resolve_inventory_url,
)


DEFAULT_PROFILE_NAME = "lmstudio"
DEFAULT_PROVIDER_NAME = "lmstudio_codex"
DEFAULT_MODEL = "local-model"
DEFAULT_API_KEY_ENV_VAR = "LMSTUDIO_API_KEY"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_AUTO_COMPACT_TOKEN_LIMIT = 24000
DEFAULT_AUTO_COMPACT_TOKEN_LIMIT_SCOPE = "body_after_prefix"
MANAGED_HEADER = (
    "# Managed by the LM Studio Codex bundle.\n"
    "# Re-run the bootstrap command from this bundle to update this file.\n"
)
DEFAULT_INSTRUCTIONS_TEXT = """# LM Studio guidance for Codex

You are Codex running against a local LM Studio model.

- Before acting, find and read the nearest AGENTS.md file in the current repository and treat it as required repository instructions.
- At the start of each task, restate the AGENTS.md rules that affect your commands, edits, tests, and verification, then follow them.
- If multiple AGENTS.md files apply, prefer the nearest one while still obeying higher-level instructions.
- Do not guess about repository policy when AGENTS.md can answer it. Read the file first, then proceed.
- Be precise and practical. Keep plans short and edits targeted.
- Keep user-facing text brief unless the task clearly requires detail.
- Expect capability variance across models. Verify assumptions before relying on tools, long context, or image support.
- Prefer smaller, incremental steps when the task is ambiguous or the model appears unstable.
- Use tools as soon as they are needed instead of narrating long intentions.
- Do not repeat the same explanation, plan, or failed action. If progress stalls, acknowledge it and switch to a narrower approach.
- If a result looks incomplete or inconsistent, say so directly and recover with a narrower approach.
- Avoid claiming network access, external integrations, or provider features unless they are explicitly available in the current session.
- When generating code, favor clear implementations and local verification over speculative abstraction.
"""


@dataclass
class BootstrapResult:
    env_path: Path
    profile_path: Path
    catalog_path: Path
    instructions_path: Path
    inventory_url: str
    env_backup: Path | None
    profile_backup: Path | None
    instructions_backup: Path | None


def create_backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.{timestamp}.bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def parse_env_file(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.exists():
        return [], {}
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        try:
            parsed = split(line, comments=True)
        except ValueError:
            parsed = []
        if len(parsed) == 1 and "=" in parsed[0]:
            key, value = parsed[0].split("=", 1)
        else:
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return lines, values


def render_env_file(existing_lines: list[str], values: dict[str, str]) -> str:
    managed_keys = {DEFAULT_ENDPOINT_ENV_VAR, DEFAULT_API_KEY_ENV_VAR}
    for key in managed_keys:
        if "\n" in values[key] or "\r" in values[key]:
            raise ValueError(f"{key} must not contain newline characters")
    rendered: list[str] = []
    seen = set()
    for raw_line in existing_lines:
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in managed_keys:
                if key not in seen:
                    rendered.append(f"{key}={quote(values[key])}")
                    seen.add(key)
                continue
        rendered.append(raw_line)

    if rendered and rendered[-1] != "":
        rendered.append("")

    for key in (DEFAULT_ENDPOINT_ENV_VAR, DEFAULT_API_KEY_ENV_VAR):
        if key not in seen:
            rendered.append(f"{key}={quote(values[key])}")
    return "\n".join(rendered).rstrip() + "\n"


def write_env_file(
    path: Path,
    inventory_url: str,
    api_key: str | None = None,
) -> Path | None:
    existing_lines, values = parse_env_file(path)
    values[DEFAULT_ENDPOINT_ENV_VAR] = inventory_url
    if api_key is not None:
        values[DEFAULT_API_KEY_ENV_VAR] = api_key
    elif DEFAULT_API_KEY_ENV_VAR not in values:
        values[DEFAULT_API_KEY_ENV_VAR] = DEFAULT_API_KEY
    content = render_env_file(existing_lines, values)
    backup = (
        create_backup(path)
        if path.exists() and path.read_text(encoding="utf-8") != content
        else None
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return backup


def inventory_to_api_base_url(inventory_url: str) -> str:
    parsed = urlparse(inventory_url)
    if parsed.path.endswith("/api/v0/models"):
        path = "/v1"
    elif parsed.path.endswith("/api/v0/models/"):
        path = "/v1"
    else:
        trimmed = parsed.path.rstrip("/")
        if not trimmed:
            path = "/v1"
        elif trimmed.endswith("/models"):
            path = trimmed.rsplit("/", 1)[0]
        else:
            path = trimmed
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def choose_profile_model(catalog_path: Path, explicit_model: str | None = None) -> str:
    if explicit_model:
        stripped = explicit_model.strip()
        if stripped:
            return stripped
    for model in load_catalog(catalog_path):
        slug = str(model.get("slug", "")).strip()
        if slug:
            return slug
    return DEFAULT_MODEL


def render_profile(
    model: str,
    catalog_path: Path,
    instructions_path: Path,
    inventory_url: str,
) -> str:
    api_base_url = inventory_to_api_base_url(inventory_url)
    return (
        MANAGED_HEADER
        + "\n"
        + f'model_provider = "{DEFAULT_PROVIDER_NAME}"\n'
        + f'model = "{model}"\n'
        + f'model_catalog_json = "{catalog_path.expanduser()}"\n'
        + f"model_auto_compact_token_limit = {DEFAULT_AUTO_COMPACT_TOKEN_LIMIT}\n"
        + f'model_auto_compact_token_limit_scope = "{DEFAULT_AUTO_COMPACT_TOKEN_LIMIT_SCOPE}"\n'
        + 'model_reasoning_effort = "medium"\n'
        + 'model_reasoning_summary = "auto"\n'
        + 'model_verbosity = "medium"\n'
        + f'model_instructions_file = "{instructions_path.expanduser()}"\n'
        + "\n"
        + f"[model_providers.{DEFAULT_PROVIDER_NAME}]\n"
        + 'name = "LM Studio"\n'
        + f'base_url = "{api_base_url}"\n'
        + 'wire_api = "responses"\n'
        + f'env_key = "{DEFAULT_API_KEY_ENV_VAR}"\n'
    )


def write_profile_file(
    path: Path,
    *,
    model: str,
    catalog_path: Path,
    instructions_path: Path,
    inventory_url: str,
) -> Path | None:
    content = render_profile(model, catalog_path, instructions_path, inventory_url)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    backup = create_backup(path) if existing is not None and existing != content else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return backup


def write_instructions_file(path: Path) -> Path | None:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    backup = (
        create_backup(path)
        if existing is not None and existing != DEFAULT_INSTRUCTIONS_TEXT
        else None
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_INSTRUCTIONS_TEXT, encoding="utf-8")
    return backup


def bootstrap(
    *,
    inventory_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    codex_home: Path | None = None,
) -> BootstrapResult:
    home = codex_home.expanduser() if codex_home is not None else Path.home() / ".codex"
    env_path = home / ".env"
    profile_path = home / f"{DEFAULT_PROFILE_NAME}.config.toml"
    catalog_path = home / DEFAULT_CATALOG_PATH.name
    instructions_path = home / "lmstudio.instructions.md"
    resolved_inventory_url = resolve_inventory_url(inventory_url or DEFAULT_INVENTORY_URL)
    selected_model = choose_profile_model(catalog_path, model)

    env_backup = write_env_file(env_path, resolved_inventory_url, api_key)
    instructions_backup = write_instructions_file(instructions_path)
    profile_backup = write_profile_file(
        profile_path,
        model=selected_model,
        catalog_path=catalog_path,
        instructions_path=instructions_path,
        inventory_url=resolved_inventory_url,
    )
    return BootstrapResult(
        env_path=env_path,
        profile_path=profile_path,
        catalog_path=catalog_path,
        instructions_path=instructions_path,
        inventory_url=resolved_inventory_url,
        env_backup=env_backup,
        profile_backup=profile_backup,
        instructions_backup=instructions_backup,
    )
