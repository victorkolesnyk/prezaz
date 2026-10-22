"""Завантаження TOML-конфігурації: типовий файл пакета плюс необов'язковий файл користувача."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT = Path(__file__).with_name("config.toml")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v  # списки замінюються цілком: так передбачувано
    return out


def load(path: str | None = None) -> dict:
    with DEFAULT.open("rb") as f:
        cfg = tomllib.load(f)
    if path:
        with open(path, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    # Змінна середовища зручна для CI, де файл конфігурації не редагують.
    flag = os.environ.get("RENOVATOR_LLM_ENABLED")
    if flag is not None and flag.strip():
        cfg.setdefault("llm", {})["enabled"] = flag.strip().lower() in ("1", "true", "yes")
    return cfg
