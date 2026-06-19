"""Render results as a table, JSON, CSV, or bare magnet/torrent links."""
from __future__ import annotations

import csv
import io
import json
import sys

from .models import Torrent

_C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
}


def _c(text, *styles, on):
    return ("".join(_C[s] for s in styles) + text + _C["reset"]) if on else text


def _trunc(text, width):
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def _seed_str(t: Torrent) -> str:
    if t.seeders is None:
        return "S:—"
    return f"S:{t.seeders}" + (f"/L:{t.leechers}" if t.leechers is not None else "")


def render_table(torrents: list[Torrent], *, color=True) -> str:
    if not torrents:
        return "No results."
    lines = []
    for i, t in enumerate(torrents, 1):
        head = "{:>2}. {}  {}".format(
            i,
            _c(_trunc(t.name, 76), "bold", "cyan", on=color),
            _c(f"[{t.provider}]", "green", on=color),
        )
        meta = _c(
            f"    {t.size_human:>9}  {_seed_str(t):<12} {t.category or t.source}",
            "dim", on=color,
        )
        lines += [head, meta]
        if t.source_url:
            lines.append(_c("    " + t.source_url, "yellow", on=color))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_json(torrents: list[Torrent]) -> str:
    return json.dumps([t.to_dict() for t in torrents], indent=2, ensure_ascii=False)


def render_csv(torrents: list[Torrent]) -> str:
    buf = io.StringIO()
    cols = ["name", "source", "provider", "size_bytes", "seeders", "leechers",
            "category", "infohash", "torrent_url", "magnet", "source_url"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for t in torrents:
        w.writerow(t.to_dict())
    return buf.getvalue().rstrip("\n")


def render_magnets(torrents, *, session) -> str:
    """Resolve every result to a magnet URI (fetches .torrent files as needed)."""
    from .magnet import ensure_magnet
    out = []
    for t in torrents:
        try:
            out.append(ensure_magnet(t, session=session))
        except Exception as exc:  # keep going; note the failure inline
            out.append(f"# {t.name}: could not resolve magnet ({exc})")
    return "\n".join(out)


def render(torrents, fmt, *, color=True, session=None) -> str:
    if fmt == "json":
        return render_json(torrents)
    if fmt == "csv":
        return render_csv(torrents)
    if fmt == "magnet":
        return render_magnets(torrents, session=session)
    if fmt == "links":
        return "\n".join(t.torrent_url or t.magnet for t in torrents)
    return render_table(torrents, color=color and sys.stdout.isatty())
