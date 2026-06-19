"""Build and resolve magnet URIs."""
from __future__ import annotations

import urllib.parse

import requests

from .bencode import parse_torrent
from .models import Torrent


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

    resp = session.get(t.torrent_url, timeout=30)
    resp.raise_for_status()
    meta = parse_torrent(resp.content)
    t.infohash = meta.infohash
    if not t.trackers:
        t.trackers = meta.trackers
    if t.size_bytes is None:
        t.size_bytes = meta.size_bytes
    t.magnet = build_magnet(meta.infohash, t.name or meta.name, t.trackers)
    return t.magnet
