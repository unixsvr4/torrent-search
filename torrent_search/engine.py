"""Run sources concurrently, then dedup / filter / sort the merged results."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

from .models import Torrent
from .sources.base import USER_AGENT, Source, get_sources


@dataclass
class SearchResult:
    torrents: list[Torrent]
    errors: dict[str, str]


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def search(
    query: str,
    *,
    sources: list[str] | None = None,
    limit: int = 25,
    pattern: str | None = None,
    min_seeders: int = 0,
    sort: str = "seeders",
) -> SearchResult:
    """Search ``query`` across the chosen sources and merge the results.

    Args:
        sources: machine names (``["archive"]``) or ``None``/``["all"]``.
        limit: max results requested *per source*.
        pattern: optional regex kept against the torrent name.
        min_seeders: drop results with fewer known seeders.
        sort: ``seeders`` | ``size`` | ``name``.
    """
    chosen: list[Source] = get_sources(sources)
    regex = re.compile(pattern, re.I) if pattern else None
    session = new_session()

    merged: list[Torrent] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(chosen))) as pool:
        futures = {
            pool.submit(s.search, query, limit=limit, session=session): s for s in chosen
        }
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                merged.extend(fut.result())
            except Exception as exc:
                errors[src.name] = f"{type(exc).__name__}: {exc}"

    return SearchResult(
        torrents=_postprocess(merged, regex=regex, min_seeders=min_seeders, sort=sort),
        errors=errors,
    )


def _postprocess(items, *, regex, min_seeders, sort) -> list[Torrent]:
    seen: set[str] = set()
    kept: list[Torrent] = []
    for t in items:
        if not t.name or not t.downloadable:
            continue
        if min_seeders and (t.seeders or 0) < min_seeders:
            continue
        if regex and not regex.search(t.name):
            continue
        if t.dedup_key in seen:
            continue
        seen.add(t.dedup_key)
        kept.append(t)

    if sort == "name":
        kept.sort(key=lambda t: t.name.lower())
    elif sort == "size":
        kept.sort(key=lambda t: t.size_bytes or 0, reverse=True)
    else:  # seeders (default)
        kept.sort(key=lambda t: (t.seeders or 0, t.extra.get("downloads", 0)), reverse=True)
    return kept
