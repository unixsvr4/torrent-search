"""Internet Archive — millions of legally-shareable torrents.

The Archive derives a BitTorrent file for every item with downloadable files
and seeds it from its own trackers (bt1/bt2.archive.org) *with HTTP web-seeds*,
so downloads complete reliably even when no other peers are online. We restrict
the query to items that actually have a torrent via ``format:"Archive
BitTorrent"``, so results are never dead links — the core fix over we-get.
"""
from __future__ import annotations

from ..models import Torrent
from .base import Source, register

SEARCH = "https://archive.org/advancedsearch.php"


@register
class InternetArchive(Source):
    name = "archive"
    label = "Internet Archive"

    def search(self, query, *, limit, session):
        params = [
            ("q", f'({query}) AND format:"Archive BitTorrent"'),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("fl[]", "item_size"),
            ("fl[]", "downloads"),
            ("fl[]", "mediatype"),
            ("sort[]", "downloads desc"),
            ("rows", str(limit)),
            ("page", "1"),
            ("output", "json"),
        ]
        resp = session.get(SEARCH, params=params, timeout=25)
        resp.raise_for_status()
        out = []
        for doc in resp.json().get("response", {}).get("docs", []):
            ident = doc.get("identifier")
            if not ident:
                continue
            title = doc.get("title") or ident
            if isinstance(title, list):
                title = title[0]
            out.append(
                Torrent(
                    name=str(title),
                    source=self.name,
                    provider=self.label,
                    torrent_url=f"https://archive.org/download/{ident}/{ident}_archive.torrent",
                    source_url=f"https://archive.org/details/{ident}",
                    size_bytes=_int(doc.get("item_size")),
                    category=str(doc.get("mediatype") or ""),
                    # IA seeds everything from its own infrastructure; web-seeds
                    # guarantee availability, so treat it as always seeded.
                    seeders=1,
                    extra={"downloads": _int(doc.get("downloads")) or 0},
                )
            )
        return out


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
