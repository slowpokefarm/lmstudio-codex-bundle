# LM Studio Codex Bundle

Portable bootstrap and catalog-management tools for using local LM Studio
models in Codex.

## What this bundle does

- bootstraps a self-contained `lmstudio` Codex profile in `~/.codex`
- stores a persistent LM Studio inventory endpoint and API key in
  `~/.codex/.env`
- syncs a live local model catalog from the LM Studio inventory endpoint
- opens a curses TUI for browsing the live inventory and editing the local
  catalog
- launches Codex with the `lmstudio` profile after loading `~/.codex/.env`

This bundle manages only local LM Studio profile, catalog, and instructions
files. 

## Requirements

- Python 3.11 or newer
- Codex CLI installed and available as `codex`
- LM Studio running locally with its API enabled

No third-party Python packages are required.

## Quick start

Clone the bundle and run:

```bash
cd lmstudio-codex-bundle
bash scripts/bootstrap_lmstudio_codex.sh
```

The bootstrap writes or updates:

- `~/.codex/.env`
- `~/.codex/lmstudio.config.toml`
- `~/.codex/model-catalog.local.json`
- `~/.codex/lmstudio.instructions.md`

It creates timestamped backups before rewriting managed files.
Generated profiles default to
`model_auto_compact_token_limit = 24000` with
`model_auto_compact_token_limit_scope = "body_after_prefix"`, so Codex starts
compacting conversation history before long local sessions overrun prompt
budget.

By default the bundle uses this LM Studio inventory endpoint:

```text
http://127.0.0.1:1234/api/v0/models?q=
```

The generated `lmstudio` profile uses the custom provider identifier
`lmstudio_codex`, avoiding Codex's reserved `lmstudio` provider name. It
always reads its bearer token from `LMSTUDIO_API_KEY`. On first setup,
bootstrap writes the placeholder `lm-studio`, which works when LM Studio
authentication is disabled.

You can override the endpoint, model, and API key during bootstrap:

```bash
bash scripts/bootstrap_lmstudio_codex.sh \
  --inventory-url "http://127.0.0.1:1234/api/v0/models?q=" \
  --model "openai/gpt-oss-20b" \
  --api-key "your-lm-studio-api-key"
```

When `--api-key` is omitted on later runs, bootstrap preserves the existing
`LMSTUDIO_API_KEY` value.

## Common commands

Refresh the live LM Studio catalog:

```bash
bash scripts/run_lmstudio_catalog_sync.sh
```

Open the LM Studio catalog TUI:

```bash
bash scripts/run_lmstudio_catalog_tui.sh
```

Start Codex with the LM Studio profile:

```bash
bash scripts/run_codex_lmstudio.sh
```

## Managed files

This bundle manages only these user-level files:

- `~/.codex/.env`
- `~/.codex/lmstudio.config.toml`
- `~/.codex/model-catalog.local.json`
- `~/.codex/lmstudio.instructions.md`

It does not edit the base `~/.codex/config.toml`. The generated
`lmstudio.config.toml` is self-contained and includes its own provider block.
Re-running bootstrap migrates older generated profiles to the
`lmstudio_codex` provider and creates a timestamped backup before replacing
changed managed files.

## Development

Run tests from the bundle root:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Initialize the profile into a temporary Codex home without calling LM Studio:

```bash
bash scripts/bootstrap_lmstudio_codex.sh --codex-home /tmp/codex-test --skip-sync
```
