"""Official Linux distribution ISOs — the canonical legal torrent.

Two strategies, because mirrors differ:

* **Scraped index dirs** (Ubuntu, Debian, Fedora) expose an Apache-style listing
  of ``.torrent`` files we can parse directly.
* **Direct URLs** (openSUSE) — the openSUSE mirror serves ``.torrent`` files at
  stable paths but does *not* list them in its directory index, so we name the
  known files explicitly and HEAD-validate them at query time (openSUSE
  discontinued Tumbleweed torrents; only Leap DVD images are seeded).

Either way, every emitted result is a signed, officially-seeded release, and we
never hand back a dead link.
"""
from __future__ import annotations

import re
import urllib.parse

from ..models import Torrent
from .base import Source, register

# (provider label, index page) — first-party dirs we scrape for .torrent hrefs.
INDEXES = [
    ("Ubuntu", "https://releases.ubuntu.com/24.04/"),
    ("Ubuntu", "https://releases.ubuntu.com/22.04/"),
    ("Debian", "https://cdimage.debian.org/debian-cd/current/amd64/bt-cd/"),
    ("Debian", "https://cdimage.debian.org/debian-cd/current/amd64/bt-dvd/"),
    ("Fedora", "https://torrent.fedoraproject.org/torrents/"),
]

# openSUSE Leap — bump on each Leap release (old dirs persist, so this never 404s,
# it just goes stale). Tumbleweed is intentionally absent: its torrents are gone.
_OPENSUSE_LEAP = "15.6"
_OSUSE_ISO = f"https://download.opensuse.org/distribution/leap/{_OPENSUSE_LEAP}/iso"
DIRECT = [
    ("openSUSE", f"openSUSE-Leap-{_OPENSUSE_LEAP}-DVD-{arch}",
     f"{_OSUSE_ISO}/openSUSE-Leap-{_OPENSUSE_LEAP}-DVD-{arch}-Current.iso.torrent")
    for arch in ("x86_64", "aarch64")
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

        def matches(*fields: str) -> bool:
            hay = " ".join(fields).lower()
            return not needles or all(n in hay for n in needles)

        # 1) scraped directory indexes
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
                name = fname[:-8] if fname.endswith(".torrent") else fname
                if url in seen or not matches(provider, name):
                    continue
                seen.add(url)
                out.append(self._mk(name, provider, url, index))
                if len(out) >= limit:
                    break

        # 2) direct URLs that aren't listed but exist at stable paths (openSUSE)
        for provider, name, url in DIRECT:
            if len(out) >= limit:
                break
            if url in seen or not matches(provider, name):
                continue
            try:  # only emit if it's actually live right now
                r = session.head(url, allow_redirects=True, timeout=15)
                if r.status_code != 200:
                    continue
            except Exception:
                continue
            seen.add(url)
            out.append(self._mk(name, provider, url, url))

        return out

    @staticmethod
    def _mk(name, provider, url, source_url) -> Torrent:
        return Torrent(
            name=name,
            source="linux",
            provider=provider,
            torrent_url=url,
            source_url=source_url,
            category="linux-iso",
            seeders=1,  # officially seeded releases
        )
