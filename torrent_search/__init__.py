"""torrent-search — a fast, reliable meta-search for LEGAL torrents, with
built-in peer-to-peer downloading.

A modern take on the classic ``we-get``: instead of scraping piracy indexes
that constantly break and return dead links, ``torrent-search`` aggregates
sources of legally-shareable content (the Internet Archive, official Linux
distribution ISOs, …) where every result is a live, downloadable torrent. It
then downloads end-to-end over BitTorrent via libtorrent.

    >>> from torrent_search import search
    >>> res = search("big buck bunny", limit=5)
    >>> res.torrents[0].name, res.torrents[0].size_human
"""
from __future__ import annotations

__version__ = "0.1.0"

from . import sources  # noqa: F401,E402  (registers built-in sources)
from .engine import SearchResult, search  # noqa: E402
from .magnet import build_magnet, ensure_magnet  # noqa: E402
from .models import Torrent  # noqa: E402

__all__ = ["search", "SearchResult", "Torrent", "build_magnet", "ensure_magnet", "__version__"]
