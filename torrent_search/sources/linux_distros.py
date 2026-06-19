"""Official Linux distribution ISOs — the canonical legal torrent.

Scrapes the distributions' own torrent index pages (stable, first-party URLs)
for ``.torrent`` links and filters them by the query. These are signed,
official releases seeded by the projects themselves.
"""
from __future__ import annotations

import re
import urllib.parse

from ..models import Torrent
from .base import Source, register

# (provider label, index page) — first-party, long-lived directories.
INDEXES = [
    ("Ubuntu", "https://releases.ubuntu.com/24.04/"),
    ("Ubuntu", "https://releases.ubuntu.com/22.04/"),
    ("Debian", "https://cdimage.debian.org/debian-cd/current/amd64/bt-cd/"),
    ("Debian", "https://cdimage.debian.org/debian-cd/current/amd64/bt-dvd/"),
]
_HREF = re.compile(r'href="([^"?]+\.torrent)"', re.I)


@register
class LinuxDistros(Source):
    name = "linux"
    label = "Linux distros"

    def search(self, query, *, limit, session):
        needles = [w for w in query.lower().split() if w not in ("linux", "iso", "distro")]
        out: list[Torrent] = []
        seen: set[str] = set()
        for provider, index in INDEXES:
            if len(out) >= limit:
                break
            try:
                resp = session.get(index, timeout=20)
                resp.raise_for_status()
            except Exception:
                continue  # skip a temporarily-down mirror, keep the rest
            for href in _HREF.findall(resp.text):
                url = urllib.parse.urljoin(index, href)
                fname = urllib.parse.unquote(href.rsplit("/", 1)[-1])
                if url in seen:
                    continue
                hay = (provider + " " + fname).lower()
                if needles and not all(n in hay for n in needles):
                    continue
                seen.add(url)
                out.append(
                    Torrent(
                        name=fname[:-8] if fname.endswith(".torrent") else fname,
                        source=self.name,
                        provider=provider,
                        torrent_url=url,
                        source_url=index,
                        category="linux-iso",
                        seeders=1,  # officially seeded releases
                    )
                )
                if len(out) >= limit:
                    break
        return out
