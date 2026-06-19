"""Normalized torrent result shared by every source."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


def human_size(n: Optional[int]) -> str:
    if not n or n < 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return (f"{f:.0f} {u}" if u == "B" else f"{f:.1f} {u}")
        f /= 1024
    return f"{n} B"


@dataclass
class Torrent:
    """A single torrent, normalized across all sources.

    At least one of ``magnet`` or ``torrent_url`` must be set so the result is
    actually downloadable — the engine drops results that have neither.
    """

    name: str
    source: str                       # machine name, e.g. "archive"
    magnet: str = ""                  # magnet: URI (preferred handle)
    torrent_url: str = ""            # https URL to a .torrent file
    infohash: str = ""               # 40-char hex btih, if known
    size_bytes: Optional[int] = None
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    category: str = ""
    provider: str = ""               # human label, e.g. "Internet Archive"
    source_url: str = ""             # human-facing details page
    trackers: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        self.infohash = (self.infohash or "").strip().lower()

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)

    @property
    def downloadable(self) -> bool:
        return bool(self.magnet or self.torrent_url)

    @property
    def dedup_key(self) -> str:
        if self.infohash:
            return self.infohash
        return f"{self.name.lower()}|{self.size_bytes}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["size_human"] = self.size_human
        return d
