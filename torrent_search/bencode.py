"""Tiny, dependency-free bencode decoder + just enough encoding to compute a
torrent's infohash.

This lets ``torrent-search`` generate magnet links from a ``.torrent`` file
without pulling in libtorrent — that heavy dependency is only needed to
actually *download*. Pure stdlib (hashlib) here.
"""
from __future__ import annotations

import hashlib
from typing import Any, Tuple


def bdecode(data: bytes) -> Any:
    value, index = _decode(data, 0)
    return value


def _decode(data: bytes, i: int) -> Tuple[Any, int]:
    c = data[i : i + 1]
    if c == b"i":  # integer: i<digits>e
        end = data.index(b"e", i)
        return int(data[i + 1 : end]), end + 1
    if c == b"l":  # list
        i += 1
        out = []
        while data[i : i + 1] != b"e":
            v, i = _decode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":  # dict (keys kept as bytes)
        i += 1
        out = {}
        while data[i : i + 1] != b"e":
            k, i = _decode(data, i)
            v, i = _decode(data, i)
            out[k] = v
        return out, i + 1
    if c.isdigit():  # byte string: <len>:<bytes>
        colon = data.index(b":", i)
        length = int(data[i:colon])
        start = colon + 1
        return data[start : start + length], start + length
    raise ValueError(f"invalid bencode at byte {i}: {c!r}")


def _encode(value: Any) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        b = value.encode()
        return str(len(b)).encode() + b":" + b
    if isinstance(value, list):
        return b"l" + b"".join(_encode(v) for v in value) + b"e"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return b"d" + b"".join(_encode(k) + _encode(v) for k, v in items) + b"e"
    raise TypeError(f"cannot bencode {type(value)}")


class TorrentMeta:
    __slots__ = ("infohash", "name", "size_bytes", "trackers", "files")

    def __init__(self, infohash, name, size_bytes, trackers, files):
        self.infohash = infohash
        self.name = name
        self.size_bytes = size_bytes
        self.trackers = trackers
        self.files = files  # list[(path:str, length:int)], '/'-joined relative paths


def parse_torrent(data: bytes) -> TorrentMeta:
    """Extract infohash (hex), name, total size and trackers from .torrent bytes."""
    meta = bdecode(data)
    if not isinstance(meta, dict) or b"info" not in meta:
        raise ValueError("not a valid .torrent (no info dict)")
    info = meta[b"info"]
    infohash = hashlib.sha1(_encode(info)).hexdigest()

    name = (info.get(b"name", b"") or b"").decode("utf-8", "replace")

    if b"length" in info:  # single-file
        size = int(info[b"length"])
        files = [(name, size)]
    else:                  # multi-file
        files = []
        for f in info.get(b"files", []):
            parts = [p.decode("utf-8", "replace") for p in f.get(b"path", [])]
            length = int(f.get(b"length", 0))
            files.append(("/".join(parts), length))
        size = sum(length for _, length in files)

    trackers = []
    if b"announce" in meta:
        trackers.append(meta[b"announce"].decode("utf-8", "replace"))
    for tier in meta.get(b"announce-list", []) or []:
        for t in tier:
            url = t.decode("utf-8", "replace")
            if url not in trackers:
                trackers.append(url)

    return TorrentMeta(infohash, name, size, trackers, files)
