"""Prompt template loading and rendering."""

from __future__ import annotations

import string
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from ..exceptions import PromptTemplateError

PROMPTS_DIR = Path(__file__).resolve().parent

_ANALYSIS_TEMPLATE = ("classification.txt", "extraction.txt")


@cache
def load_template(name: str) -> str:
    """Read a template from the ``prompts`` package directory."""
    if "/" in name or "\\" in name or ".." in name:
        raise PromptTemplateError(f"invalid prompt template name: {name!r}")
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise PromptTemplateError(f"prompt template not found: {name}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptTemplateError(f"unable to read prompt template {name}: {exc}") from exc


def render(template: str, context: Mapping[str, Any], *, strict: bool = True) -> str:
    """Render ``$placeholders``. Unset placeholders become ``""`` (or raise)."""
    try:
        tmpl = string.Template(template)
        if strict:
            return tmpl.substitute(dict(context))
        return tmpl.safe_substitute(dict(context))
    except (KeyError, ValueError) as exc:
        raise PromptTemplateError(f"unable to render prompt template: {exc}") from exc


def render_template(name: str, context: Mapping[str, Any], *, strict: bool = True) -> str:
    return render(load_template(name), context, strict=strict)


def build_analysis_prompt(context: Mapping[str, Any]) -> str:
    """Compose the classification + extraction prompt for one email."""
    combined = "\n\n".join(load_template(name) for name in _ANALYSIS_TEMPLATE)
    return render(combined, context)


def prompt_version() -> str:
    return "1.0"


__all__ = ["PROMPTS_DIR", "build_analysis_prompt", "load_template", "prompt_version", "render", "render_template"]
