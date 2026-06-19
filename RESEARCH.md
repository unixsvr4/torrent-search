# RESEARCH.md

Findings, source evaluations, validation commands, and dependencies gathered
while building `torrent-search`. This is the evidence behind the design choices
in `README.md` — kept so the work is reproducible and future contributors know
what was already tried (and what to *not* re-attempt).

Investigation date: **2026-06-18**. Environment: macOS (Darwin 25.5.0), Python 3.13,
`requests` 2.32.3, `libtorrent` 2.0.13.0.

---

## 1. Origin: reviewing `we-get`

Repo reviewed: <https://github.com/rachmadaniHaryono/we-get>

**What it is.** A CLI torrent meta-search. Each torrent site is a module under
`we_get/modules/` (1337x, The Pirate Bay, EZTV, YTS, LimeTorrents, Il Corsaro
Nero). Modules normalize results to `{name, seeds, leeches, magnet}`. CLI:
`we-get --search "query" --target <site> --filter <regex>`; output as text,
`--json`, or `--links`.

**Weaknesses identified (and what we fix):**

| we-get weakness | Consequence | Our fix |
|---|---|---|
| Scrapes piracy HTML pages | Layout changes silently break modules | Use stable JSON APIs / first-party index pages |
| No active maintenance | Dead links, stale results (the user's complaint) | Sources where a torrent is *guaranteed* to exist |
| Magnet links only | User still needs a separate client | Built-in libtorrent P2P download |
| One site down → run breaks | Fragile | Concurrent fan-out, per-source error isolation |

**Scope decision.** we-get points at piracy indexes. `torrent-search` ships and
tests **only legal, freely-shareable sources** (Internet Archive, official Linux
ISOs). The source layer stays pluggable, but this repo does not include
copyright-infringing scrapers — which is *also* what makes it reliable, since
these APIs are stable and every item is actually seeded.

---

## 2. Source evaluation

All probes were plain `curl` / `python3` one-liners against public endpoints.

### ✅ Internet Archive — SHIPPED (primary)

Millions of public-domain / Creative-Commons items; the Archive derives a
`.torrent` for every item with downloadable files and seeds it from its own
infrastructure with HTTP web-seeds.

- **Search API:** `https://archive.org/advancedsearch.php`
  ```bash
  curl -s 'https://archive.org/advancedsearch.php?q=sintel+AND+format%3A%22Archive+BitTorrent%22&fl[]=identifier&fl[]=item_size&rows=2&output=json'
  # -> numFound 93
  ```
  Key insight: filtering `AND format:"Archive BitTorrent"` guarantees the item
  has a torrent, so results are never dead links. (`format:archive.torrent`
  returns 0 — wrong string.) A bare CC-movie query returns ~1.13M items.

- **Per-item metadata:** `https://archive.org/metadata/<identifier>`
  ```bash
  curl -s https://archive.org/metadata/Sintel | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['server'])"
  ```
  Exposes the **current** data node (`server`, `dir`, `d1`, `d2`) — critical for
  the web-seed fix (§4).

- **Torrent URL pattern:** `https://archive.org/download/<id>/<id>_archive.torrent`
  ⚠️ This 302-redirects to the data node — **must follow redirects** (`curl -L`),
  otherwise you get an empty file / 503:
  ```bash
  curl -sL -o s.torrent "https://archive.org/download/Sintel/Sintel_archive.torrent"  # 37 KB, valid
  curl -s  -o s.torrent "https://archive.org/download/Sintel/Sintel_archive.torrent"  # 0 bytes!
  ```

### ✅ Official Linux distros — SHIPPED (secondary)

First-party, long-lived torrent index directories scraped for `.torrent` hrefs.

- **Ubuntu:** `https://releases.ubuntu.com/<ver>/`
  ```bash
  curl -s https://releases.ubuntu.com/24.04/ | grep -o 'ubuntu-[^"]*\.torrent' | sort -u
  # ubuntu-24.04.3-desktop-amd64.iso.torrent, ubuntu-24.04.3-live-server-amd64.iso.torrent, ...
  ```
  Version dirs (`24.04/`, `22.04/`) are stable symlinks that survive point releases.
- **Debian:** `https://cdimage.debian.org/debian-cd/current/amd64/bt-cd/` (and `bt-dvd/`)
  ```bash
  curl -s https://cdimage.debian.org/debian-cd/current/amd64/bt-cd/ | grep -o 'href="[^"]*\.torrent"'
  # debian-13.5.0-amd64-netinst.iso.torrent, ...
  ```

### ❌ Rejected sources (do not re-attempt without changes)

| Source | Probe | Result | Verdict |
|---|---|---|---|
| **Academic Torrents** | `GET https://academictorrents.com/apiv2/collection/list` | `404` | No working public API found; site scraping fragile. Skipped. |
| **Linux Mint** | `GET https://torrents.linuxmint.com/` then grep `.torrent` | no `.torrent` hrefs (different page structure) | Dropped rather than ship a dead source. |
| **linuxtracker.org** | `GET /rss.php` (works) / browse search HTML | RSS parses, but `browse.php` search HTML returned no usable rows | Not used; could be revisited via RSS-only "latest" listing. |

---

## 3. P2P download validation (libtorrent)

**libtorrent presence:**
```bash
python3 -c "import libtorrent as lt; print(lt.version)"   # 2.0.13.0
```
Install paths (documented in README): `pip install -e ".[download]"`,
`pip install libtorrent`, or OS packages `brew install libtorrent-rasterbar`
(macOS) / `apt install python3-libtorrent` (Debian/Ubuntu).

**Raw swarm test — Sintel (1.8 GB, healthy swarm):**
- Trackers in torrent: `http://bt1.archive.org:6969/announce`, `bt2…`.
- Connected to **3 peers / 2 seeds**, pulled **32 MB at 4.8 MB/s** in seconds →
  proves real BitTorrent peer transfer works end-to-end. (Stopped early; full
  file too large to complete in a test.)

**Full 100% completion — item `6a-0ddd-605c-08221` (616 KB, intact):**
```
downloading  peers=6 seeds=2  0.57/0.63 MB  91%
seeding      peers=3 seeds=0  0.63/0.63 MB 100%   <-- reached seeding
```
Files written to disk (`.mp3`, `.png`, spectrogram, `_meta.xml`, …). This is the
canonical proof that `download()` works through our own code path.

**Test items that did *not* complete (and why — not our bug):**
- `gov.uscourts.*` (9.8 KB): connected to 6 peers but 0 bytes — the underlying
  document files are gone from IA; no client could fetch them.
- `psalmi_22_vulgata_librivox` (4.7 MB): stalled at 45% on peers alone; with the
  web-seed fix jumped to **98%**, then stuck — one derivative file (e.g. a
  regenerated `_64kb.mp3`) now 404s, so 100% is impossible for *any* client.

**Lesson:** long-tail IA items sometimes have missing derivative files. To get a
clean 100% test, pick an item whose every file currently returns HTTP 200 (a
small helper that HEAD-checks each file via the metadata API was used to find
`6a-0ddd-605c-08221`).

---

## 4. The web-seed reliability problem & fix

**Symptom.** Downloads of less-popular IA items stall partway (commonly ~45%)
once transient peers leave, even though IA "seeds everything".

**Root cause.** IA `.torrent` files carry a `url-list` (BEP19 web-seeds), but the
hosts are baked in at creation time and **go stale when an item migrates** between
data nodes:
```
url-list: ['https://archive.org/download/',
           'http://ia601308.us.archive.org/20/items/',   # stale host
           'http://ia801308.us.archive.org/20/items/']
# metadata API now reports the item on a DIFFERENT node, e.g. ia802805
```
The direct stale hosts 404; the canonical `https://archive.org/download/` entry
redirects cross-host, which libtorrent does not reliably follow for web-seeds →
no HTTP fallback → stall.

**Fix (in `download.py::_ia_webseeds`).** On download, query the metadata API for
the item's **current** node and hand libtorrent that exact web-seed base
(`https://<server><parent-dir>/`), plus `d1`/`d2` and the canonical URL as
fallbacks, via `handle.add_url_seed(...)`. Verified effect:
```
# before fix: peers leave -> stuck at 45%, 0 kB/s
# after fix:  0 peers, web-seed engages -> 624 kB/s -> 98–100%
```
This is the key reliability advantage over naive clients (and over we-get, which
doesn't download at all).

---

## 5. Magnet generation without libtorrent

To keep search + magnet output dependency-light (only `requests`), infohash
computation is implemented in pure stdlib (`bencode.py`): bdecode the `.torrent`,
re-bencode the `info` dict with **canonically sorted keys**, `sha1()` it.
```bash
python3 -m torrent_search sintel -s archive -n 1 --magnet
# magnet:?xt=urn:btih:acb47ba3958759fdf09f36eeb80fe51c45c1abc9&dn=Elephants%20Dream&tr=http%3A%2F%2Fbt1.archive.org%3A6969%2Fannounce&...
```
Gotcha fixed: the `xt=urn:btih:<hash>` prefix must stay **literal** — only `dn`/`tr`
*values* are percent-encoded. Encoding the colons (`urn%3Abtih%3A`) breaks the
"starts with magnet:?xt=urn:btih:" convention some clients expect.

---

## 6. Dependencies & install commands

```bash
# runtime (search + magnets): only requests
pip install -e .

# to download over P2P: add libtorrent
pip install -e ".[download]"        # or: pip install libtorrent
brew install libtorrent-rasterbar   # macOS alternative
apt install python3-libtorrent      # Debian/Ubuntu alternative

# dev
pip install -e ".[dev]"             # pytest + ruff
```

Versions used during research: `requests 2.32.3`, `libtorrent 2.0.13.0`,
Python 3.13.

---

## 7. Test strategy

- `tests/test_core.py` — 17 offline unit tests (models, bencode roundtrip +
  infohash, magnet building, engine dedup/filter/sort, registry, output). No
  network; run in CI with `TORRENT_SEARCH_SKIP_NET=1`.
- `tests/test_live.py` — 3 network smoke tests (IA search returns results, magnet
  resolves to a 40-hex infohash, Linux source finds Ubuntu). Auto-skip offline.
  Deliberately does **not** perform a real download in CI (slow, swarm-dependent).

```bash
TORRENT_SEARCH_SKIP_NET=1 python -m pytest   # offline
python -m pytest                             # + live
ruff check torrent_search
```

---

## 8. Open issues / future work

- **Missing IA derivatives** can cap a download below 100% (data genuinely gone).
  Could surface a clear "N files unavailable" message by HEAD-checking files first.
- **Seeder counts** are not exposed by IA; we report `S:1` (IA always seeds) and
  sort IA results by `downloads`. A tracker-scrape source could provide real
  seed/leech numbers.
- **More legal sources** worth adding: a working Academic Torrents path, OpenSUSE,
  Fedora, Arch, Tails, and Project Gutenberg / Librivox bulk torrents.
- **DHT-only / magnet-first items**: current `download()` handles magnets via
  `parse_magnet_uri`; not yet exercised by a shipped source (all current sources
  provide `.torrent` URLs).
