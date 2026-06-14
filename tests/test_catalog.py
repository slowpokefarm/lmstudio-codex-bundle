#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lmstudio_codex_bundle.lmstudio_catalog import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_ENDPOINT_ENV_VAR,
    build_status_maps,
    fetch_inventory,
    resolve_inventory_url,
    save_catalog,
    sync_catalog,
)
from lmstudio_codex_bundle.sync_cli import main


class CatalogTests(unittest.TestCase):
    def test_fetch_inventory_uses_configurable_endpoint(self) -> None:
        payload = {"data": [{"id": "model-a", "type": "llm"}]}
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))
        response.__enter__ = lambda self=response: self
        response.__exit__ = lambda *args: None
        with mock.patch("lmstudio_codex_bundle.lmstudio_catalog.urlopen", return_value=response) as mocked:
            inventory = fetch_inventory("http://127.0.0.1:9999/api/v0/models?q=")
        self.assertEqual(inventory[0]["id"], "model-a")
        mocked.assert_called_once()

    def test_sync_preserves_existing_context_override(self) -> None:
        inventory = [
            {
                "id": "google/gemma-4-26b-a4b-qat",
                "type": "vlm",
                "publisher": "google",
                "arch": "gemma4",
                "quantization": "Q4_0",
                "max_context_length": 262144,
                "capabilities": ["tool_use"],
            }
        ]
        existing = [
            {
                "slug": "google/gemma-4-26b-a4b-qat",
                "display_name": "google/gemma-4-26b-a4b-qat",
                "description": "existing",
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [{"effort": "low", "description": "x"}],
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 30,
                "availability_nux": None,
                "upgrade": None,
                "base_instructions": "x",
                "supports_reasoning_summaries": True,
                "default_reasoning_summary": "auto",
                "support_verbosity": False,
                "default_verbosity": None,
                "apply_patch_tool_type": "freeform",
                "truncation_policy": {"mode": "tokens", "limit": 12000},
                "supports_parallel_tool_calls": False,
                "experimental_supported_tools": [],
                "context_window": 65536,
                "max_context_window": 65536,
                "input_modalities": ["text", "image"],
            }
        ]
        synced = sync_catalog(inventory, existing, prune=False)
        self.assertEqual(synced[0]["context_window"], 65536)
        self.assertEqual(synced[0]["max_context_window"], 65536)

    def test_sync_adds_non_embedding_and_skips_embeddings(self) -> None:
        inventory = [
            {"id": "a", "type": "llm", "max_context_length": 100},
            {"id": "b", "type": "embeddings", "max_context_length": 100},
        ]
        synced = sync_catalog(inventory, [], prune=True)
        self.assertEqual([item["slug"] for item in synced], ["a"])

    def test_save_catalog_creates_backup_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.json"
            path.write_text(json.dumps({"models": [{"slug": "old"}]}), encoding="utf-8")
            backup = save_catalog(path, [{"slug": "new"}], create_backup_copy=True)
            self.assertIsNotNone(backup)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["models"][0]["slug"], "new")
            self.assertTrue(backup.exists())

    def test_build_status_maps_tracks_inventory_and_catalog_presence(self) -> None:
        inventory = [
            {"id": "both", "type": "llm"},
            {"id": "inv", "type": "llm"},
            {"id": "embed", "type": "embeddings"},
        ]
        catalog = [{"slug": "both"}, {"slug": "cat"}]
        inventory_by_slug, statuses = build_status_maps(inventory, catalog)
        self.assertEqual(sorted(inventory_by_slug), ["both", "inv"])
        self.assertEqual(statuses["both"], "both")
        self.assertEqual(statuses["inv"], "inventory")
        self.assertEqual(statuses["cat"], "catalog")

    def test_resolve_inventory_url_uses_env_fallback(self) -> None:
        with mock.patch.dict(os.environ, {DEFAULT_ENDPOINT_ENV_VAR: "http://env/api/v0/models?q="}, clear=True):
            self.assertEqual(resolve_inventory_url(None), "http://env/api/v0/models?q=")

    def test_cli_dry_run_emits_json_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "catalog.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = ["sync_cli.py", "--catalog", str(catalog_path), "--dry-run"]
            with mock.patch("lmstudio_codex_bundle.sync_cli.fetch_inventory") as fetcher:
                fetcher.return_value = [
                    {"id": "model-a", "type": "llm", "max_context_length": 32768}
                ]
                with mock.patch("sys.argv", argv):
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        exit_code = main()
            self.assertEqual(exit_code, 0)
            self.assertFalse(catalog_path.exists())
            self.assertIn('"slug": "model-a"', stdout.getvalue())

    def test_default_catalog_path_points_to_local_file(self) -> None:
        self.assertEqual(DEFAULT_CATALOG_PATH.name, "model-catalog.local.json")


if __name__ == "__main__":
    unittest.main()
