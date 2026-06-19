"""Source plugin contract + registry.

Add a tracker/index by subclassing ``Source`` and decorating with ``@register``.
The engine, the ``--source`` flag and ``--list-sources`` all read the registry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import requests

from ..models import Torrent

USER_AGENT = (
    "torrent-search/0.1 (legal torrent meta-search; "
    "https://github.com/abdoulaw/torrent-search)"
)

_REGISTRY: dict[str, "Source"] = {}


class Source(ABC):
    name: str = ""        # CLI machine name, e.g. "archive"
    label: str = ""       # human label

    @abstractmethod
    def search(self, query: str, *, limit: int, session: requests.Session) -> Iterable[Torrent]:
        """Return up to ``limit`` :class:`Torrent` results.

        Let network errors propagate; the engine isolates each source so one
        failing tracker never sinks the whole search.
        """
        raise NotImplementedError


def register(cls: type[Source]) -> type[Source]:
    inst = cls()
    if not inst.name:
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    if inst.name in _REGISTRY:
        raise ValueError(f"duplicate source name: {inst.name!r}")
    _REGISTRY[inst.name] = inst
    return cls


def all_sources() -> list[Source]:
    return list(_REGISTRY.values())


def get_sources(names: Iterable[str] | None) -> list[Source]:
    if not names or list(names) == ["all"]:
        return all_sources()
    chosen, unknown = [], []
    for n in names:
        n = n.strip().lower()
        if n == "all":
            return all_sources()
        if n in _REGISTRY:
            chosen.append(_REGISTRY[n])
        else:
            unknown.append(n)
    if unknown:
        valid = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"unknown source(s): {', '.join(unknown)}. Available: {valid}")
    return chosen
