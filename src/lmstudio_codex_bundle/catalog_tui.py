#!/usr/bin/env python3
"""Standalone curses TUI for the LM Studio Codex catalog."""

from __future__ import annotations

import argparse
import curses
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from lmstudio_codex_bundle.catalog_common import diff_catalogs
from lmstudio_codex_bundle.lmstudio_catalog import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_INVENTORY_URL,
    build_entry,
    build_status_maps,
    fetch_inventory,
    load_catalog,
    resolve_inventory_url,
    save_catalog,
)


FILTERS = ["all", "both", "inventory", "catalog"]
STATUS_LABELS = {"both": "[=]", "inventory": "[+]", "catalog": "[-]"}
EDITABLE_FIELDS = [
    "display_name",
    "description",
    "priority",
    "context_window",
    "max_context_window",
    "input_modalities",
    "default_reasoning_level",
    "supported_reasoning_levels",
    "supports_reasoning_summaries",
    "default_reasoning_summary",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Edit the LM Studio Codex model catalog."
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to the catalog JSON to edit.",
    )
    parser.add_argument(
        "--inventory-url",
        default=None,
        help=f"LM Studio inventory endpoint. Defaults to {DEFAULT_INVENTORY_URL}.",
    )
    args = parser.parse_args()
    args.inventory_url = resolve_inventory_url(args.inventory_url)
    return args


class CatalogTui:
    def __init__(self, catalog_path: Path, inventory_url: str) -> None:
        self.catalog_path = catalog_path.expanduser()
        self.inventory_url = inventory_url
        self.original_models = load_catalog(self.catalog_path)
        self.working_models = deepcopy(self.original_models)
        self.inventory: list[dict[str, Any]] = []
        self.inventory_by_slug: dict[str, dict[str, Any]] = {}
        self.statuses: dict[str, str] = {}
        self.filter_index = 0
        self.focus = "list"
        self.selected_slug: str | None = None
        self.selected_field = 0
        self.message = ""
        self.backup_path: Path | None = None
        self.preview_mode = False
        self.preview_lines: list[str] = []
        self.preview_cursor = 0
        self.refresh_inventory(initial_load=True)

    def refresh_inventory(self, initial_load: bool = False) -> None:
        try:
            self.inventory = fetch_inventory(self.inventory_url)
            self.message = "Inventory refreshed"
        except (HTTPError, URLError, OSError, ValueError) as exc:
            if not initial_load:
                self.message = f"Inventory refresh failed: {exc}"
            elif not self.original_models:
                raise
            else:
                self.message = f"Inventory unavailable; catalog-only mode: {exc}"
            self.inventory = []
        self.inventory_by_slug, self.statuses = build_status_maps(
            self.inventory, self.working_models
        )
        self.refresh_model_list()

    def refresh_model_list(self) -> None:
        filter_name = FILTERS[self.filter_index]
        slugs = sorted(self.statuses)
        if filter_name != "all":
            slugs = [slug for slug in slugs if self.statuses.get(slug) == filter_name]
        self.visible_slugs = slugs
        if self.selected_slug not in self.visible_slugs:
            self.selected_slug = self.visible_slugs[0] if self.visible_slugs else None

    def current_model(self) -> dict[str, Any] | None:
        if self.selected_slug is None:
            return None
        for model in self.working_models:
            if model["slug"] == self.selected_slug:
                return model
        return None

    def current_inventory_model(self) -> dict[str, Any] | None:
        if self.selected_slug is None:
            return None
        return self.inventory_by_slug.get(self.selected_slug)

    def find_priority(self) -> int:
        priorities = [model.get("priority", 0) for model in self.working_models]
        return max(priorities, default=0) + 10

    def rebuild_statuses(self) -> None:
        self.inventory_by_slug, self.statuses = build_status_maps(
            self.inventory, self.working_models
        )
        self.refresh_model_list()

    def add_selected_model(self) -> None:
        if self.selected_slug is None:
            self.message = "No model selected"
            return
        if self.current_model() is not None:
            self.message = "Model already in catalog"
            return
        inventory_model = self.current_inventory_model()
        if inventory_model is None:
            self.message = "Selected model is not in LM Studio inventory"
            return
        self.working_models.append(
            build_entry(inventory_model, None, self.find_priority())
        )
        self.rebuild_statuses()
        self.message = f"Added {self.selected_slug}"

    def remove_selected_model(self) -> None:
        if self.selected_slug is None:
            self.message = "No model selected"
            return
        model = self.current_model()
        if model is None:
            self.message = "Model is not in catalog"
            return
        self.working_models = [
            item for item in self.working_models if item["slug"] != self.selected_slug
        ]
        self.rebuild_statuses()
        self.message = f"Removed {self.selected_slug}"

    def restore_selected_model(self) -> None:
        if self.selected_slug is None:
            self.message = "No model selected"
            return
        inventory_model = self.current_inventory_model()
        if inventory_model is None:
            self.message = "Selected model is not in LM Studio inventory"
            return
        replacement = build_entry(inventory_model, None, self.find_priority())
        existing = self.current_model()
        if existing is None:
            self.working_models.append(replacement)
        else:
            replacement["priority"] = existing.get("priority", replacement["priority"])
            for idx, item in enumerate(self.working_models):
                if item["slug"] == self.selected_slug:
                    self.working_models[idx] = replacement
                    break
        self.rebuild_statuses()
        self.message = f"Restored defaults for {self.selected_slug}"

    def dirty(self) -> bool:
        return diff_catalogs(self.original_models, self.working_models) != {
            "added": [],
            "removed": [],
            "modified": [],
        }

    def edit_prompt(self, stdscr: Any, prompt: str, default: str) -> str | None:
        curses.echo()
        height, width = stdscr.getmaxyx()
        stdscr.move(height - 2, 0)
        stdscr.clrtoeol()
        display = f"{prompt} [{default}]: "
        stdscr.addnstr(height - 2, 0, display, width - 1)
        stdscr.refresh()
        try:
            value = stdscr.getstr(
                height - 2,
                min(len(display), width - 1),
                width - len(display) - 1,
            )
        finally:
            curses.noecho()
        if value is None:
            return None
        text = value.decode("utf-8").strip()
        return text or default

    def edit_current_field(self, stdscr: Any) -> None:
        model = self.current_model()
        if model is None:
            self.message = "Add the model to the catalog before editing it"
            return
        field = EDITABLE_FIELDS[self.selected_field]
        value = model.get(field)
        if field in {"priority", "context_window", "max_context_window"}:
            text = self.edit_prompt(stdscr, f"Set {field}", str(value))
            if text is None:
                return
            try:
                model[field] = int(text)
            except ValueError:
                self.message = f"{field} must be an integer"
                return
        elif field == "input_modalities":
            current = ",".join(value)
            text = self.edit_prompt(
                stdscr, "Set input_modalities (text,image)", current
            )
            if text is None:
                return
            modes = [item.strip() for item in text.split(",") if item.strip()]
            if not modes or any(item not in {"text", "image"} for item in modes):
                self.message = "input_modalities must use text and/or image"
                return
            model[field] = modes
        elif field == "default_reasoning_level":
            text = self.edit_prompt(stdscr, "Set default_reasoning_level", str(value))
            if text is None:
                return
            if text not in {"low", "medium", "high"}:
                self.message = "default_reasoning_level must be low, medium, or high"
                return
            model[field] = text
        elif field == "supported_reasoning_levels":
            current = ",".join(item["effort"] for item in value)
            text = self.edit_prompt(
                stdscr,
                "Set supported_reasoning_levels (comma separated low,medium,high)",
                current,
            )
            if text is None:
                return
            efforts = [item.strip() for item in text.split(",") if item.strip()]
            if not efforts or any(item not in {"low", "medium", "high"} for item in efforts):
                self.message = "supported_reasoning_levels must use low, medium, and/or high"
                return
            model[field] = [
                {
                    "effort": effort,
                    "description": {
                        "low": "Lower reasoning depth for faster turns.",
                        "medium": "Balanced reasoning depth for normal coding work.",
                        "high": "Higher reasoning depth for harder tasks.",
                    }[effort],
                }
                for effort in efforts
            ]
        elif field == "supports_reasoning_summaries":
            text = self.edit_prompt(
                stdscr,
                "Set supports_reasoning_summaries (true/false)",
                str(value).lower(),
            )
            if text is None:
                return
            if text not in {"true", "false"}:
                self.message = "supports_reasoning_summaries must be true or false"
                return
            model[field] = text == "true"
        elif field == "default_reasoning_summary":
            text = self.edit_prompt(stdscr, "Set default_reasoning_summary", str(value))
            if text is None:
                return
            if text not in {"auto", "concise", "detailed"}:
                self.message = "default_reasoning_summary must be auto, concise, or detailed"
                return
            model[field] = text
        else:
            text = self.edit_prompt(stdscr, f"Set {field}", str(value or ""))
            if text is None:
                return
            model[field] = text
        self.message = f"Updated {field}"

    def build_preview_lines(self) -> list[str]:
        diff = diff_catalogs(self.original_models, self.working_models)
        lines = [f"Save {len(self.working_models)} models to {self.catalog_path}", ""]
        lines.append(f"Added: {', '.join(diff['added']) or 'none'}")
        lines.append(f"Removed: {', '.join(diff['removed']) or 'none'}")
        lines.append("")
        for item in diff["modified"]:
            lines.append(item["slug"])
            for change in item["changes"]:
                before = repr(change["before"])
                after = repr(change["after"])
                lines.append(f"  {change['field']}: {before} -> {after}")
            lines.append("")
        if not diff["added"] and not diff["removed"] and not diff["modified"]:
            lines.append("No changes.")
        lines.append("")
        lines.append("Press s to save, q to cancel preview")
        return lines

    def save(self) -> None:
        self.backup_path = save_catalog(
            self.catalog_path, self.working_models, create_backup_copy=True
        )
        self.original_models = deepcopy(self.working_models)
        self.message = (
            f"Saved {len(self.working_models)} models"
            + (f" (backup: {self.backup_path.name})" if self.backup_path else "")
        )

    def draw_list(self, stdscr: Any, height: int, width: int) -> None:
        stdscr.addnstr(0, 0, "LM Studio catalog", width - 1, curses.A_BOLD)
        filter_name = FILTERS[self.filter_index]
        stdscr.addnstr(
            1,
            0,
            f"Filter: {filter_name} | Inventory: {self.inventory_url}",
            width - 1,
        )
        max_rows = max(height - 4, 1)
        start = 0
        if self.selected_slug in self.visible_slugs:
            selected_index = self.visible_slugs.index(self.selected_slug)
            if selected_index >= max_rows:
                start = selected_index - max_rows + 1
        for row, slug in enumerate(self.visible_slugs[start : start + max_rows], start=2):
            marker = STATUS_LABELS[self.statuses[slug]]
            attr = curses.A_REVERSE if slug == self.selected_slug and self.focus == "list" else curses.A_NORMAL
            stdscr.addnstr(row, 0, f"{marker} {slug}", width - 1, attr)

    def draw_detail(self, stdscr: Any, top: int, left: int, height: int, width: int) -> None:
        model = self.current_model()
        inventory_model = self.current_inventory_model()
        title = self.selected_slug or "No model selected"
        stdscr.addnstr(top, left, title, width - 1, curses.A_BOLD)
        if model is None:
            lines = [
                "Model is not in the catalog.",
                "Press a to add it from the current inventory.",
            ]
        else:
            lines = []
            for index, field in enumerate(EDITABLE_FIELDS):
                value = model.get(field)
                display = value
                if field == "supported_reasoning_levels":
                    display = ",".join(item["effort"] for item in value)
                if isinstance(display, list):
                    display = ",".join(str(item) for item in display)
                prefix = ">" if self.focus == "detail" and index == self.selected_field else " "
                lines.append(f"{prefix} {field}: {display}")
        if inventory_model:
            lines.append(
                f" inventory context: {inventory_model.get('max_context_length', 'n/a')}"
            )
            lines.append(f" inventory type: {inventory_model.get('type', 'n/a')}")
        for offset, line in enumerate(lines[: max(height - 1, 1)], start=1):
            stdscr.addnstr(top + offset, left, line, width - 1)

    def draw_footer(self, stdscr: Any, height: int, width: int) -> None:
        stdscr.hline(height - 3, 0, "-", width)
        stdscr.addnstr(
            height - 2,
            0,
            "Arrows move | Tab switch pane | a add | d delete | r restore | e edit | f filter | R refresh | p preview | q quit",
            width - 1,
        )
        stdscr.addnstr(height - 1, 0, self.message, width - 1)

    def draw_preview(self, stdscr: Any, height: int, width: int) -> None:
        stdscr.clear()
        stdscr.addnstr(0, 0, "Preview changes", width - 1, curses.A_BOLD)
        body_height = max(height - 2, 1)
        visible = self.preview_lines[self.preview_cursor : self.preview_cursor + body_height]
        for row, line in enumerate(visible, start=1):
            wrapped = textwrap.shorten(line, width=width - 1, placeholder="...")
            stdscr.addnstr(row, 0, wrapped, width - 1)
        stdscr.refresh()

    def handle_preview_input(self, key: int) -> bool:
        if key in {ord("q"), 27}:
            self.preview_mode = False
            return True
        if key == ord("s"):
            self.save()
            self.preview_mode = False
            return True
        if key == curses.KEY_DOWN and self.preview_cursor < max(len(self.preview_lines) - 1, 0):
            self.preview_cursor += 1
            return True
        if key == curses.KEY_UP and self.preview_cursor > 0:
            self.preview_cursor -= 1
            return True
        return False

    def handle_main_input(self, stdscr: Any, key: int) -> bool:
        if key in {ord("q"), 27}:
            if self.dirty():
                self.message = "Unsaved changes; press p to review or save"
                return True
            return False
        if key == ord("\t"):
            self.focus = "detail" if self.focus == "list" else "list"
            return True
        if key == ord("f"):
            self.filter_index = (self.filter_index + 1) % len(FILTERS)
            self.refresh_model_list()
            return True
        if key == ord("R"):
            self.refresh_inventory()
            return True
        if key == ord("a"):
            self.add_selected_model()
            return True
        if key == ord("d"):
            self.remove_selected_model()
            return True
        if key == ord("r"):
            self.restore_selected_model()
            return True
        if key == ord("e"):
            self.edit_current_field(stdscr)
            return True
        if key == ord("p"):
            self.preview_lines = self.build_preview_lines()
            self.preview_cursor = 0
            self.preview_mode = True
            return True
        if self.focus == "list":
            if key == curses.KEY_DOWN and self.visible_slugs:
                index = self.visible_slugs.index(self.selected_slug) if self.selected_slug in self.visible_slugs else -1
                self.selected_slug = self.visible_slugs[min(index + 1, len(self.visible_slugs) - 1)]
                return True
            if key == curses.KEY_UP and self.visible_slugs:
                index = self.visible_slugs.index(self.selected_slug) if self.selected_slug in self.visible_slugs else 0
                self.selected_slug = self.visible_slugs[max(index - 1, 0)]
                return True
        else:
            if key == curses.KEY_DOWN:
                self.selected_field = min(self.selected_field + 1, len(EDITABLE_FIELDS) - 1)
                return True
            if key == curses.KEY_UP:
                self.selected_field = max(self.selected_field - 1, 0)
                return True
        return True

    def run(self, stdscr: Any) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        while True:
            height, width = stdscr.getmaxyx()
            if self.preview_mode:
                self.draw_preview(stdscr, height, width)
                key = stdscr.getch()
                self.handle_preview_input(key)
                continue
            stdscr.clear()
            left_width = max(width // 2, 30)
            self.draw_list(stdscr, height, left_width)
            self.draw_detail(stdscr, 0, left_width + 1, height - 3, width - left_width - 1)
            self.draw_footer(stdscr, height, width)
            stdscr.refresh()
            key = stdscr.getch()
            if not self.handle_main_input(stdscr, key):
                return


def main() -> int:
    args = parse_args()
    tui = CatalogTui(Path(args.catalog), args.inventory_url)
    curses.wrapper(tui.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
