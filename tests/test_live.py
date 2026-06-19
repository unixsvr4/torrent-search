"""Network-dependent smoke tests (no actual download).

Skipped when offline or TORRENT_SEARCH_SKIP_NET=1 so CI stays hermetic.
"""
import os
import socket
import unittest

from torrent_search import search
from torrent_search.engine import new_session
from torrent_search.magnet import ensure_magnet


def _online(host="archive.org") -> bool:
    if os.environ.get("TORRENT_SEARCH_SKIP_NET") == "1":
        return False
    try:
        socket.create_connection((host, 443), timeout=5).close()
        return True
    except OSError:
        return False


@unittest.skipUnless(_online(), "no network / net tests disabled")
class TestLive(unittest.TestCase):
    def test_archive_search_real_results(self):
        res = search("big buck bunny", sources=["archive"], limit=5)
        self.assertTrue(res.torrents)
        self.assertTrue(all(t.torrent_url for t in res.torrents))

    def test_magnet_resolves_from_torrent(self):
        res = search("big buck bunny", sources=["archive"], limit=1)
        magnet = ensure_magnet(res.torrents[0], session=new_session())
        self.assertTrue(magnet.startswith("magnet:?xt=urn:btih:"))
        self.assertEqual(len(res.torrents[0].infohash), 40)

    def test_linux_distros(self):
        res = search("ubuntu", sources=["linux"], limit=5)
        self.assertTrue(res.torrents)
        self.assertTrue(any("ubuntu" in t.name.lower() for t in res.torrents))


if __name__ == "__main__":
    unittest.main()
