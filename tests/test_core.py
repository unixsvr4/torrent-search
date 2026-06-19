"""Offline unit tests — no network required."""
import re
import unittest

from torrent_search.bencode import bdecode, parse_torrent, _encode
from torrent_search.engine import _postprocess
from torrent_search.magnet import TorrentUnavailable, build_magnet, fetch_torrent_bytes
from torrent_search.models import Torrent, human_size
from torrent_search.output import render_csv, render_json, render_table
from torrent_search.sources.base import all_sources, get_sources


def mk(name="T", url="https://x/1.torrent", magnet="", source="archive",
       seeders=1, size=100, infohash=""):
    return Torrent(name=name, source=source, torrent_url=url, magnet=magnet,
                   seeders=seeders, size_bytes=size, infohash=infohash)


class TestModel(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(human_size(None), "—")
        self.assertEqual(human_size(0), "—")
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(1536), "1.5 KB")
        self.assertTrue(human_size(5 * 1024**3).endswith("GB"))

    def test_downloadable_requires_handle(self):
        self.assertTrue(mk().downloadable)
        self.assertTrue(Torrent("n", "s", magnet="magnet:?xt=1").downloadable)
        self.assertFalse(Torrent("n", "s").downloadable)

    def test_dedup_key_prefers_infohash(self):
        self.assertEqual(mk(infohash="ABC").dedup_key, "abc")
        self.assertEqual(mk(name="Foo", size=9).dedup_key, "foo|9")


class TestBencode(unittest.TestCase):
    def test_roundtrip(self):
        for v in [0, 42, b"hi", [1, b"a"], {b"k": b"v", b"n": 3}]:
            self.assertEqual(bdecode(_encode(v)), v)

    def test_dicts_are_sorted_on_encode(self):
        # canonical encoding is required for a correct infohash
        self.assertEqual(_encode({b"b": 1, b"a": 2}), b"d1:ai2e1:bi1ee")

    def test_parse_minimal_torrent(self):
        info = {b"name": b"hello.txt", b"length": 1234,
                b"piece length": 16384, b"pieces": b"\x00" * 20}
        data = _encode({b"announce": b"http://tr/announce", b"info": info})
        meta = parse_torrent(data)
        self.assertEqual(meta.name, "hello.txt")
        self.assertEqual(meta.size_bytes, 1234)
        self.assertEqual(meta.trackers, ["http://tr/announce"])
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", meta.infohash))

    def test_parse_multifile_size(self):
        info = {b"name": b"d", b"piece length": 16384, b"pieces": b"\x00" * 20,
                b"files": [{b"length": 10, b"path": [b"a"]},
                           {b"length": 5, b"path": [b"b"]}]}
        self.assertEqual(parse_torrent(_encode({b"info": info})).size_bytes, 15)


class TestMagnet(unittest.TestCase):
    def test_build(self):
        m = build_magnet("ABCDEF", "My File", ["http://tr/x"])
        self.assertTrue(m.startswith("magnet:?xt=urn:btih:abcdef"))
        self.assertIn("dn=My%20File", m)
        self.assertIn("tr=http%3A%2F%2Ftr%2Fx", m)


class _FakeResp:
    def __init__(self, status, content=b""):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("should have been mapped to TorrentUnavailable first")


class _FakeSession:
    def __init__(self, status, content=b"data"):
        self._r = _FakeResp(status, content)

    def get(self, url, timeout=None):
        return self._r


class TestFetchTorrent(unittest.TestCase):
    def test_ok_returns_bytes(self):
        self.assertEqual(fetch_torrent_bytes("u", session=_FakeSession(200, b"x")), b"x")

    def test_restricted_and_missing_raise_clean(self):
        for code in (401, 403, 404):
            with self.assertRaises(TorrentUnavailable):
                fetch_torrent_bytes("u", session=_FakeSession(code))


class TestPostprocess(unittest.TestCase):
    def test_dedup_and_drop_undownloadable(self):
        items = [mk(infohash="aa"), mk(infohash="aa"),
                 Torrent("no handle", "archive", seeders=5)]
        out = _postprocess(items, regex=None, min_seeders=0, sort="seeders")
        self.assertEqual(len(out), 1)

    def test_min_seeders(self):
        out = _postprocess([mk(seeders=0, infohash="a"), mk(seeders=3, infohash="b")],
                           regex=None, min_seeders=1, sort="seeders")
        self.assertEqual(len(out), 1)

    def test_regex_on_name(self):
        items = [mk(name="Ubuntu 24.04", infohash="a"), mk(name="Debian", infohash="b")]
        out = _postprocess(items, regex=re.compile("ubuntu", re.I), min_seeders=0, sort="name")
        self.assertEqual([t.name for t in out], ["Ubuntu 24.04"])

    def test_sort_size_desc(self):
        out = _postprocess([mk(size=10, infohash="a"), mk(size=99, infohash="b")],
                           regex=None, min_seeders=0, sort="size")
        self.assertEqual([t.size_bytes for t in out], [99, 10])


class TestRegistry(unittest.TestCase):
    def test_defaults_to_all(self):
        self.assertEqual(len(get_sources(None)), len(all_sources()))
        self.assertGreaterEqual(len(all_sources()), 2)

    def test_unknown_raises(self):
        with self.assertRaises(KeyError):
            get_sources(["archive", "thepiratebay"])


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.items = [mk(name="Ubuntu 24.04 ISO", size=4_000_000_000, seeders=42)]

    def test_table_plain(self):
        out = render_table(self.items, color=False)
        self.assertIn("Ubuntu 24.04 ISO", out)
        self.assertNotIn("\033[", out)

    def test_json(self):
        import json
        d = json.loads(render_json(self.items))
        self.assertEqual(d[0]["name"], "Ubuntu 24.04 ISO")
        self.assertIn("size_human", d[0])

    def test_csv_header(self):
        self.assertTrue(render_csv(self.items).startswith("name,source,provider"))


if __name__ == "__main__":
    unittest.main()
