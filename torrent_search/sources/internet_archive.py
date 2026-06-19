"""Internet Archive — millions of legally-shareable torrents.

The Archive derives a BitTorrent file for every item with downloadable files
and seeds it from its own trackers (bt1/bt2.archive.org) *with HTTP web-seeds*,
so downloads complete reliably even when no other peers are online.

Query design (relevance):
* ``format:"Archive BitTorrent"`` => a torrent exists (never a dead link).
* ``NOT access-restricted-item:true`` => it's actually downloadable.
* We match the query **words against the title** (AND-ed, ignoring ≤2-char
  stopwords like "of"/"the"), then sort by ``downloads`` — so a search like
  "night of the living dead" surfaces the actual film, not every item whose
  full text happens to contain the word "death". If a title search finds
  nothing, we fall back to a broader full-text match for recall.
"""
from __future__ import annotations

import re

from ..models import Torrent
from .base import Source, register

SEARCH = "https://archive.org/advancedsearch.php"
_BASE = 'format:"Archive BitTorrent" AND NOT access-restricted-item:true'
# alphanumeric tokens (keeps "24.04", "c64", "wolfenstein-3d")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")
_STOPWORDS = {"the", "of", "and", "a", "an", "to", "in", "for", "on", "with",
              "at", "by", "or", "de", "la", "el"}


def _terms(query: str) -> list[str]:
    toks = _TOKEN.findall(query)
    meaningful = [t for t in toks if t.lower() not in _STOPWORDS and len(t) > 1]
    # fall back to all tokens if the query was entirely stopwords / short
    return meaningful or toks


@register
class InternetArchive(Source):
    name = "archive"
    label = "Internet Archive"

    def search(self, query, *, limit, session):
        terms = _terms(query)
        if terms:
            anded = " AND ".join(terms)
            attempts = [f"title:({anded}) AND {_BASE}", f"({anded}) AND {_BASE}"]
        else:
            attempts = [f"({query}) AND {_BASE}"]

        docs = []
        for q in attempts:
            docs = self._fetch(q, limit, session)
            if docs:  # first attempt that returns anything wins
                break

        out = []
        for doc in docs:
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

    def _fetch(self, q, limit, session):
        params = [
            ("q", q),
            ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "item_size"),
            ("fl[]", "downloads"), ("fl[]", "mediatype"),
            ("sort[]", "downloads desc"),
            ("rows", str(limit)), ("page", "1"), ("output", "json"),
        ]
        resp = session.get(SEARCH, params=params, timeout=25)
        resp.raise_for_status()
        return resp.json().get("response", {}).get("docs", [])


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
