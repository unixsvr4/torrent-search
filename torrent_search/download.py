"""Real peer-to-peer downloading via libtorrent.

``libtorrent`` is an *optional* dependency: searching and generating magnet
links need only ``requests``. Importing this module is fine without libtorrent;
calling :func:`download` without it raises a clear, actionable error.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from .magnet import ensure_magnet
from .models import Torrent

_IA_TORRENT = re.compile(r"archive\.org/download/([^/]+)/")


def _ia_webseeds(torrent_url: str, session: requests.Session) -> list[str]:
    """Internet Archive web-seed URLs that point at the item's *current* data node.

    IA bakes a stale host into its .torrent files (items migrate between nodes),
    which is why libtorrent stalls part-way. The metadata API tells us where the
    item lives right now; we hand libtorrent that exact HTTP web-seed so downloads
    reliably complete even with zero peers. Returns [] for non-IA torrents.
    """
    m = _IA_TORRENT.search(torrent_url or "")
    if not m:
        return []
    ident = m.group(1)
    try:
        meta = session.get(f"https://archive.org/metadata/{ident}", timeout=15).json()
    except Exception:
        return ["https://archive.org/download/"]  # canonical (redirecting) fallback
    seeds = ["https://archive.org/download/"]
    server, d = meta.get("server"), meta.get("dir")
    if server and d:
        seeds.insert(0, f"https://{server}{d.rsplit('/', 1)[0]}/")
    for alt in (meta.get("d1"), meta.get("d2")):
        if alt and d:
            seeds.append(f"https://{alt}{d.rsplit('/', 1)[0]}/")
    return seeds

_STATES = [
    "queued", "checking", "downloading metadata", "downloading",
    "finished", "seeding", "allocating", "checking fastresume",
]


@dataclass
class Progress:
    name: str
    state: str
    progress: float          # 0.0 - 1.0
    peers: int
    seeds: int
    download_rate: int       # bytes/s
    upload_rate: int         # bytes/s
    total_done: int          # bytes downloaded
    total_wanted: int        # bytes to download


class LibtorrentUnavailable(RuntimeError):
    pass


def libtorrent_available() -> bool:
    try:
        import libtorrent  # noqa: F401
        return True
    except Exception:
        return False


def _import_lt():
    try:
        import libtorrent as lt
        return lt
    except Exception as exc:  # pragma: no cover - env dependent
        raise LibtorrentUnavailable(
            "Downloading needs libtorrent, which isn't installed.\n"
            "  Install it with:  pip install libtorrent   (or: brew install libtorrent-rasterbar)\n"
            "Search and magnet-link generation work without it."
        ) from exc


def _select_files(lt, ti, only: str):
    """Return (file_priorities, [(path, size)], total_bytes) for files matching
    ``only`` — everything else gets priority 0 so it's never downloaded."""
    from .magnet import path_matches
    fs = ti.files()
    prios, selected, total = [], [], 0
    for i in range(fs.num_files()):
        path, size = fs.file_path(i), fs.file_size(i)
        if path_matches(only, path):
            prios.append(4)  # normal priority
            selected.append((path, size))
            total += size
        else:
            prios.append(0)  # do not download
    return prios, selected, total


def _add_params(lt, t: Torrent, save_path: str, session: requests.Session,
                only: Optional[str] = None, on_select=None):
    os.makedirs(save_path, exist_ok=True)
    if t.torrent_url:
        from .magnet import fetch_torrent_bytes
        atp = lt.add_torrent_params()
        ti = lt.torrent_info(lt.bdecode(fetch_torrent_bytes(t.torrent_url, session=session)))
        atp.ti = ti
        if only:
            prios, selected, total = _select_files(lt, ti, only)
            if not selected:
                raise ValueError(f"no files in this torrent match --only {only!r}")
            atp.file_priorities = prios
            if on_select:
                on_select(selected, total)
    elif only:
        raise ValueError("--only needs a .torrent source; magnet results aren't supported yet")
    else:
        atp = lt.parse_magnet_uri(ensure_magnet(t, session=session))
    atp.save_path = save_path
    return atp


def download(
    t: Torrent,
    save_path: str = ".",
    *,
    session: Optional[requests.Session] = None,
    on_progress: Optional[Callable[[Progress], None]] = None,
    timeout: Optional[float] = 1800,
    poll: float = 1.0,
    seed: bool = False,
    only: Optional[str] = None,
    on_select=None,
) -> str:
    """Download ``t`` over BitTorrent into ``save_path`` and return the saved path.

    Blocks until the torrent finishes (or ``timeout`` seconds elapse, or — when
    ``seed`` is False — it reaches the seeding state). ``on_progress`` is invoked
    once per poll with a :class:`Progress` snapshot.

    ``only`` selects a subset of files (glob or substring) so you can pull a few
    items out of a huge multi-file torrent instead of the whole thing; matched
    files are reported to ``on_select(selected, total_bytes)`` before downloading.
    """
    lt = _import_lt()
    session = session or requests.Session()
    ses = lt.session({"listen_interfaces": "0.0.0.0:6881,[::]:6881", "enable_dht": True})

    handle = ses.add_torrent(
        _add_params(lt, t, save_path, session, only=only, on_select=on_select)
    )
    # Augment with live web-seeds so completion doesn't depend on a live swarm.
    for ws in _ia_webseeds(t.torrent_url, session):
        handle.add_url_seed(ws)
    deadline = time.time() + timeout if timeout else None

    while True:
        s = handle.status()
        if on_progress:
            on_progress(Progress(
                name=s.name or t.name,
                state=_STATES[s.state] if s.state < len(_STATES) else str(s.state),
                progress=s.progress,
                peers=s.num_peers,
                seeds=s.num_seeds,
                download_rate=s.download_rate,
                upload_rate=s.upload_rate,
                total_done=s.total_done,
                total_wanted=s.total_wanted,
            ))
        finished = s.is_seeding or (not seed and s.is_finished)
        if finished:
            break
        if deadline and time.time() > deadline:
            raise TimeoutError(
                f"timed out after {timeout}s at {s.progress * 100:.1f}% "
                f"({s.num_peers} peers)"
            )
        time.sleep(poll)

    name = handle.status().name or t.name
    return os.path.join(save_path, name)
