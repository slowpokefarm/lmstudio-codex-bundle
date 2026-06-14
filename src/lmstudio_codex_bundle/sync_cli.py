#!/usr/bin/env python3
"""Standalone LM Studio catalog sync CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError

from lmstudio_codex_bundle.lmstudio_catalog import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_INVENTORY_URL,
    fetch_inventory,
    load_catalog,
    resolve_inventory_url,
    save_catalog,
    sync_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Codex model catalog JSON from LM Studio inventory, preserving "
            "existing per-model overrides."
        )
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to the Codex model catalog JSON.",
    )
    parser.add_argument(
        "--inventory-url",
        default=None,
        help=f"LM Studio inventory endpoint. Defaults to {DEFAULT_INVENTORY_URL}.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove catalog entries whose slugs are no longer present in LM Studio.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resulting catalog JSON to stdout instead of writing it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_path = Path(args.catalog).expanduser()
    inventory_url = resolve_inventory_url(args.inventory_url)
    try:
        inventory = fetch_inventory(inventory_url)
    except URLError as exc:
        print(f"Failed to fetch LM Studio inventory: {exc}", file=sys.stderr)
        return 1

    existing_models = load_catalog(catalog_path)
    synced_models = sync_catalog(inventory, existing_models, prune=args.prune)
    payload = {"models": synced_models}

    if args.dry_run:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    save_catalog(catalog_path, synced_models, create_backup_copy=False)
    print(
        f"Synced {len(synced_models)} catalog entries to {catalog_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
