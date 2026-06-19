"""Build and resolve magnet URIs."""
from __future__ import annotations

import urllib.parse

import requests

from .bencode import parse_torrent
from .models import Torrent


class TorrentUnavailable(RuntimeError):
    """The .torrent file can't be fetched (restricted, missing, etc.)."""


def fetch_torrent_bytes(url: str, *, session: requests.Session) -> bytes:
    """GET a .torrent file, raising a clear :class:`TorrentUnavailable` on the
    common "exists in the index but isn't downloadable" cases."""
    resp = session.get(url, timeout=30)
    if resp.status_code in (401, 403):
        raise TorrentUnavailable(
            f"access-restricted by the host (HTTP {resp.status_code}) — this item is "
            "stream-only / not available for download; try another result"
        )
    if resp.status_code == 404:
        raise TorrentUnavailable("the .torrent file is gone (HTTP 404); try another result")
    resp.raise_for_status()
    return resp.content


def build_magnet(infohash: str, name: str = "", trackers=None) -> str:
    # The xt urn must stay literal (xt=urn:btih:HASH); only dn/tr values get encoded.
    parts = [f"xt=urn:btih:{infohash.lower()}"]
    if name:
        parts.append("dn=" + urllib.parse.quote(name, safe=""))
    for tr in trackers or []:
        parts.append("tr=" + urllib.parse.quote(tr, safe=""))
    return "magnet:?" + "&".join(parts)


def ensure_magnet(t: Torrent, *, session: requests.Session) -> str:
    """Return a magnet URI for ``t``, fetching/parsing its .torrent if needed.

    Order of preference: existing magnet -> build from known infohash ->
    download the .torrent and compute the infohash (pure-python, no libtorrent).
    Fills ``t.infohash``/``t.trackers`` as a side effect when it has to fetch.
    """
    if t.magnet:
        return t.magnet
    if t.infohash:
        return build_magnet(t.infohash, t.name, t.trackers)
    if not t.torrent_url:
        raise ValueError(f"{t.name!r} has neither magnet, infohash nor torrent_url")

    meta = parse_torrent(fetch_torrent_bytes(t.torrent_url, session=session))
    t.infohash = meta.infohash
    if not t.trackers:
        t.trackers = meta.trackers
    if t.size_bytes is None:
        t.size_bytes = meta.size_bytes
    t.magnet = build_magnet(meta.infohash, t.name or meta.name, t.trackers)
    return t.magnet
