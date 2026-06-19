# torrent-search

**A fast, reliable meta-search for torrents — with built-in peer-to-peer downloading.**
Search many sources with one query, get back *live, downloadable* results, and pull
them over BitTorrent end-to-end.

[![CI](https://github.com/abdoulaw/torrent-search/actions/workflows/ci.yml/badge.svg)](https://github.com/abdoulaw/torrent-search/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A modern successor to the classic [`we-get`](https://github.com/rachmadaniHaryono/we-get),
which has gone stale and frequently returns dead links. `torrent-search` fixes that by
indexing sources where **every result is a real, currently-seeded torrent** — and then
actually downloading it for you over P2P, with an HTTP web-seed fallback so transfers
*finish* instead of stalling at 99%.

> **Scope / ethics.** The built-in sources are all **legal, freely-shareable content**:
> the Internet Archive (public-domain & Creative-Commons media, open data) and official
> Linux distribution ISOs. The source layer is pluggable, but this project ships and
> tests only legitimate sources. Don't use it to infringe copyright.

## What makes it better than we-get

| | we-get | torrent-search |
|---|---|---|
| Results | scrapes piracy sites that break / 404 | live APIs; results guaranteed to have a torrent |
| Download | prints magnet links only | **real P2P download built in** (libtorrent) |
| Reliability | dead swarms stall forever | **auto web-seed fallback** → downloads complete |
| Magnets | — | generated from the .torrent, **no libtorrent needed** |
| Resilience | one bad site breaks the run | per-source isolation; failures are warnings |
| Output | text / json | table / json / csv / magnet / links |

## Install

```bash
git clone https://github.com/abdoulaw/torrent-search.git
cd torrent-search
pip install -e .                # search + magnet generation (only needs requests)
pip install -e ".[download]"    # + libtorrent, to actually download over P2P
```

`libtorrent` can also come from your OS: `brew install libtorrent-rasterbar`
(macOS) or `apt install python3-libtorrent` (Debian/Ubuntu).

## Usage

```bash
# Search every source
torrent-search "big buck bunny"

# Official Linux ISOs only
torrent-search ubuntu --source linux

# Get magnet links (fetches each .torrent to compute the infohash — no libtorrent needed)
torrent-search sintel --magnet

# Download result #1 over BitTorrent into ~/Downloads
torrent-search "big buck bunny" --download ~/Downloads --pick 1

# Machine-readable
torrent-search debian --json
torrent-search debian --csv  > debian.csv
```

Example:

```
$ torrent-search "big buck bunny" --source archive -n 3
 1. Big Buck Bunny  [Internet Archive]
      421.1 MB  S:1          movies
     https://archive.org/details/BigBuckBunny_124
 ...

$ torrent-search 6a-0ddd-605c-08221 --download . --pick 1
Downloading: 6a 0ddd 605c 08221  (616.5 KB)  [Internet Archive]
  [##############################] 100.0%  seeding   peers=6 seeds=2  124.0 kB/s
Done -> ./6a-0ddd-605c-08221
```

### Options

| Flag | Description |
|------|-------------|
| `-s, --source NAME` | Restrict to a source (repeatable). Default: all. |
| `-n, --limit N` | Max results per source (default 25). |
| `-f, --filter REGEX` | Keep only names matching the regex. |
| `--min-seeders N` | Drop results below N seeders. |
| `--sort seeders\|size\|name` | Ordering (default `seeders`). |
| `--json` / `--csv` / `--magnet` / `--links` | Output format (default: table). |
| `-d, --download DIR` | Download a result over P2P (default dir: current). |
| `--pick N` | Which result to download (default 1). |
| `--list-sources` | List sources and exit. |

## How the reliable downloading works

BitTorrent stalls when a swarm has no complete seed. The Internet Archive seeds every
item over HTTP **web-seeds**, but it bakes a *stale* data-node host into its `.torrent`
files (items migrate between servers), so naive clients get stuck part-way. On download,
`torrent-search` queries the Archive's metadata API for the item's **current** node and
hands libtorrent that exact web-seed (plus the canonical redirecting URL as a fallback) —
so downloads complete even with zero live peers. Verified end-to-end: a real transfer
reaches 100% and enters `seeding`.

## Use as a library

```python
from torrent_search import search, ensure_magnet
from torrent_search.engine import new_session
from torrent_search.download import download   # needs libtorrent

res = search("ubuntu", sources=["linux"], limit=10, min_seeders=1)
for t in res.torrents:
    print(t.name, t.size_human, t.seeders)

magnet = ensure_magnet(res.torrents[0], session=new_session())   # no libtorrent needed
path = download(res.torrents[0], "downloads",                    # P2P download
                on_progress=lambda p: print(p.state, f"{p.progress*100:.0f}%"))
```

## Architecture

```
torrent_search/
├── models.py        # Torrent dataclass (normalized result)
├── bencode.py       # tiny bencode + infohash (pure stdlib — no libtorrent)
├── magnet.py        # build / resolve magnet URIs
├── engine.py        # concurrent fan-out, dedup, filter, sort
├── download.py      # libtorrent P2P download + IA web-seed fallback
├── output.py        # table / json / csv / magnet / links
├── cli.py
└── sources/
    ├── base.py              # Source ABC + @register registry
    ├── internet_archive.py  # millions of legal torrents (real search API)
    └── linux_distros.py     # official Ubuntu / Debian ISOs
```

### Adding a source

```python
# torrent_search/sources/my_source.py
from ..models import Torrent
from .base import Source, register

@register
class MySource(Source):
    name = "mysource"
    label = "My Source"

    def search(self, query, *, limit, session):
        r = session.get("https://api.example/search", params={"q": query}, timeout=20)
        r.raise_for_status()
        return [Torrent(name=x["title"], source=self.name, provider=self.label,
                        magnet=x["magnet"], seeders=x.get("seeders"))
                for x in r.json()["results"]]
```

Import it in `sources/__init__.py` — it's instantly available to the CLI and `--list-sources`.

## Development

```bash
pip install -e ".[dev]"
TORRENT_SEARCH_SKIP_NET=1 python -m pytest   # offline unit tests
python -m pytest                             # + live smoke tests (network)
ruff check torrent_search
```

## License

[MIT](LICENSE).
