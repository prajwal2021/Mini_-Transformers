"""YAML configuration loading and stable hashing."""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


class FrozenConfig(dict[str, Any]):
    """A recursively immutable, dict-like configuration."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        super().__init__({key: _freeze(value) for key, value in values.items()})

    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("FrozenConfig is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenConfig(value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if dataclasses.is_dataclass(value):
        return _plain(dataclasses.asdict(value))
    return value


def load(path: str | Path) -> FrozenConfig:
    """Load a YAML mapping into a frozen configuration."""
    with Path(path).open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle) or {}
    if not isinstance(values, Mapping):
        raise TypeError("configuration root must be a mapping")
    return FrozenConfig(values)


def dump(config: Mapping[str, Any], path: str | Path) -> None:
    """Write a configuration as readable YAML."""
    with Path(path).open("w", encoding="utf-8") as handle:
        yaml.safe_dump(_plain(config), handle, sort_keys=True)


def config_hash(config: Mapping[str, Any]) -> str:
    """Hash canonical JSON representation and return its first 12 hex characters."""
    canonical = json.dumps(_plain(config), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
