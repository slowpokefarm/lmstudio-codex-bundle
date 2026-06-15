#!/usr/bin/env python3
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lmstudio_codex_bundle.bootstrap_cli import main as bootstrap_main
from lmstudio_codex_bundle.bundle import (
    DEFAULT_API_KEY,
    DEFAULT_API_KEY_ENV_VAR,
    DEFAULT_AUTO_COMPACT_TOKEN_LIMIT,
    DEFAULT_AUTO_COMPACT_TOKEN_LIMIT_SCOPE,
    DEFAULT_INSTRUCTIONS_TEXT,
    DEFAULT_PROVIDER_NAME,
    bootstrap,
    choose_profile_model,
    parse_env_file,
    render_profile,
)


class BundleTests(unittest.TestCase):
    def test_bootstrap_creates_env_profile_and_instructions_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = bootstrap(
                inventory_url="http://127.0.0.1:1234/api/v0/models?q=",
                codex_home=Path(tmpdir),
            )
            self.assertTrue(result.env_path.exists())
            self.assertTrue(result.profile_path.exists())
            self.assertTrue(result.instructions_path.exists())
            _, values = parse_env_file(result.env_path)
            self.assertEqual(
                values["LMSTUDIO_INVENTORY_URL"],
                "http://127.0.0.1:1234/api/v0/models?q=",
            )
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], DEFAULT_API_KEY)
            self.assertIn(
                f'model_provider = "{DEFAULT_PROVIDER_NAME}"',
                result.profile_path.read_text(),
            )
            self.assertIn(
                f"model_auto_compact_token_limit = {DEFAULT_AUTO_COMPACT_TOKEN_LIMIT}",
                result.profile_path.read_text(),
            )
            self.assertIn(
                f'model_auto_compact_token_limit_scope = "{DEFAULT_AUTO_COMPACT_TOKEN_LIMIT_SCOPE}"',
                result.profile_path.read_text(),
            )
            self.assertEqual(
                result.instructions_path.read_text(encoding="utf-8"),
                DEFAULT_INSTRUCTIONS_TEXT,
            )
            self.assertIn("read the nearest AGENTS.md file", DEFAULT_INSTRUCTIONS_TEXT)
            self.assertIn("Keep user-facing text brief", DEFAULT_INSTRUCTIONS_TEXT)
            self.assertIn("Do not repeat the same explanation", DEFAULT_INSTRUCTIONS_TEXT)

    def test_bootstrap_merges_env_without_dropping_other_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text('FOO="bar"\nLMSTUDIO_INVENTORY_URL="old"\n', encoding="utf-8")
            bootstrap(
                inventory_url="http://new/api/v0/models?q=",
                codex_home=Path(tmpdir),
            )
            _, values = parse_env_file(env_path)
            self.assertEqual(values["FOO"], "bar")
            self.assertEqual(values["LMSTUDIO_INVENTORY_URL"], "http://new/api/v0/models?q=")
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], DEFAULT_API_KEY)

    def test_bootstrap_preserves_existing_api_key_when_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                f'{DEFAULT_API_KEY_ENV_VAR}="existing-secret"\n',
                encoding="utf-8",
            )
            bootstrap(codex_home=Path(tmpdir))
            _, values = parse_env_file(env_path)
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], "existing-secret")

    def test_bootstrap_replaces_existing_api_key_when_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                f'{DEFAULT_API_KEY_ENV_VAR}="existing-secret"\n',
                encoding="utf-8",
            )
            result = bootstrap(api_key="replacement-secret", codex_home=Path(tmpdir))
            _, values = parse_env_file(env_path)
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], "replacement-secret")
            self.assertIsNotNone(result.env_backup)

    def test_bootstrap_shell_quotes_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            api_key = "quote'-$HOME-`command`"
            result = bootstrap(api_key=api_key, codex_home=Path(tmpdir))
            _, values = parse_env_file(result.env_path)
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], api_key)

    def test_bootstrap_rejects_multiline_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, DEFAULT_API_KEY_ENV_VAR):
                bootstrap(api_key="line-one\nline-two", codex_home=Path(tmpdir))

    def test_bootstrap_creates_backups_when_rewriting_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / ".env").write_text('LMSTUDIO_INVENTORY_URL="old"\n', encoding="utf-8")
            (home / "lmstudio.config.toml").write_text("old-profile\n", encoding="utf-8")
            (home / "lmstudio.instructions.md").write_text("old\n", encoding="utf-8")
            result = bootstrap(
                inventory_url="http://new/api/v0/models?q=",
                codex_home=home,
            )
            self.assertIsNotNone(result.env_backup)
            self.assertIsNotNone(result.profile_backup)
            self.assertIsNotNone(result.instructions_backup)

    def test_bootstrap_rerun_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            first = bootstrap(
                inventory_url="http://same/api/v0/models?q=",
                codex_home=home,
            )
            second = bootstrap(
                inventory_url="http://same/api/v0/models?q=",
                codex_home=home,
            )
            self.assertIsNone(second.env_backup)
            self.assertIsNone(second.profile_backup)
            self.assertIsNone(second.instructions_backup)
            self.assertEqual(first.profile_path.read_text(), second.profile_path.read_text())

    def test_render_profile_is_self_contained(self) -> None:
        content = render_profile(
            "openai/gpt-oss-20b",
            Path("/tmp/model-catalog.local.json"),
            Path("/tmp/lmstudio.instructions.md"),
            "http://127.0.0.1:1234/api/v0/models?q=",
        )
        self.assertIn(f'[model_providers.{DEFAULT_PROVIDER_NAME}]', content)
        self.assertIn(f'model_provider = "{DEFAULT_PROVIDER_NAME}"', content)
        self.assertIn(f'env_key = "{DEFAULT_API_KEY_ENV_VAR}"', content)
        self.assertNotIn("requires_openai_auth", content)
        self.assertIn('model_catalog_json = "/tmp/model-catalog.local.json"', content)
        self.assertIn(
            f"model_auto_compact_token_limit = {DEFAULT_AUTO_COMPACT_TOKEN_LIMIT}",
            content,
        )
        self.assertIn(
            f'model_auto_compact_token_limit_scope = "{DEFAULT_AUTO_COMPACT_TOKEN_LIMIT_SCOPE}"',
            content,
        )
        self.assertIn('model_instructions_file = "/tmp/lmstudio.instructions.md"', content)
        self.assertIn('base_url = "http://127.0.0.1:1234/v1"', content)

    def test_choose_profile_model_prefers_catalog_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "model-catalog.local.json"
            catalog_path.write_text('{"models":[{"slug":"model-a"},{"slug":"model-b"}]}\n', encoding="utf-8")
            self.assertEqual(choose_profile_model(catalog_path), "model-a")

    def test_bootstrap_cli_writes_files_and_skips_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "bootstrap_cli.py",
                "--inventory-url",
                "http://127.0.0.1:1234/api/v0/models?q=",
                "--codex-home",
                tmpdir,
                "--api-key",
                "cli-secret",
                "--skip-sync",
            ]
            with mock.patch("sys.argv", argv):
                with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                    exit_code = bootstrap_main()
            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(tmpdir) / ".env").exists())
            self.assertTrue((Path(tmpdir) / "lmstudio.config.toml").exists())
            self.assertTrue((Path(tmpdir) / "lmstudio.instructions.md").exists())
            _, values = parse_env_file(Path(tmpdir) / ".env")
            self.assertEqual(values[DEFAULT_API_KEY_ENV_VAR], "cli-secret")


if __name__ == "__main__":
    unittest.main()
