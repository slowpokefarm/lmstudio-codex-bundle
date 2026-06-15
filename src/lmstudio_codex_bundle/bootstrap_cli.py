#!/usr/bin/env python3
"""Bootstrap CLI for the standalone LM Studio Codex bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lmstudio_codex_bundle.bundle import bootstrap, choose_profile_model, write_profile_file
from lmstudio_codex_bundle.lmstudio_catalog import load_catalog
from lmstudio_codex_bundle.sync_cli import main as sync_catalog_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or update the LM Studio Codex bundle under ~/.codex."
    )
    parser.add_argument(
        "--inventory-url",
        help="LM Studio inventory endpoint. Defaults to LMSTUDIO_INVENTORY_URL or the local default.",
    )
    parser.add_argument(
        "--api-key",
        help="LM Studio API key to store in ~/.codex/.env. Existing keys are preserved when omitted.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Default model slug to place in the lmstudio profile. If omitted, the first catalog model is used when available.",
    )
    parser.add_argument(
        "--codex-home",
        default="~/.codex",
        help="Codex home directory to manage. Defaults to ~/.codex.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip the live LM Studio catalog refresh step.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    codex_home = Path(args.codex_home).expanduser()
    result = bootstrap(
        inventory_url=args.inventory_url,
        api_key=args.api_key,
        model=args.model,
        codex_home=codex_home,
    )
    print(f"Updated {result.env_path}")
    if result.env_backup is not None:
        print(f"Backup: {result.env_backup}")
    print(f"Updated {result.instructions_path}")
    if result.instructions_backup is not None:
        print(f"Backup: {result.instructions_backup}")
    print(f"Updated {result.profile_path}")
    if result.profile_backup is not None:
        print(f"Backup: {result.profile_backup}")

    if args.skip_sync:
        print(f"Skipped catalog refresh; expected catalog path: {result.catalog_path}")
        return 0

    argv = [
        "lmstudio-codex-sync",
        "--catalog",
        str(result.catalog_path),
        "--inventory-url",
        result.inventory_url,
    ]
    original_argv = sys.argv
    try:
        sys.argv = argv
        exit_code = sync_catalog_main()
    finally:
        sys.argv = original_argv
    if exit_code != 0:
        return exit_code

    selected_model = choose_profile_model(result.catalog_path, args.model)
    write_profile_file(
        result.profile_path,
        model=selected_model,
        catalog_path=result.catalog_path,
        instructions_path=result.instructions_path,
        inventory_url=result.inventory_url,
    )
    print(f"Selected profile model: {selected_model}")
    print(f"Catalog entries available: {len(load_catalog(result.catalog_path))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
