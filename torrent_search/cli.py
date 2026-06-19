"""Command-line interface: search legal torrents and download them over P2P."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .engine import new_session, search
from .models import human_size
from .output import render
from .sources.base import all_sources


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="torrent-search",
        description="Search legal torrents across multiple sources and download "
        "them over BitTorrent — a faster, reliable take on we-get.",
        epilog='Examples:\n'
        '  torrent-search "big buck bunny"\n'
        '  torrent-search ubuntu --source linux --magnet\n'
        '  torrent-search sintel --download ~/Downloads --pick 1\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("query", nargs="*", help="what to search for")
    p.add_argument("-s", "--source", action="append", metavar="NAME",
                   help="restrict to a source (repeatable). Default: all.")
    p.add_argument("-n", "--limit", type=int, default=25, help="max results per source (default 25)")
    p.add_argument("-f", "--filter", metavar="REGEX", help="keep only names matching this regex")
    p.add_argument("--min-seeders", type=int, default=0, help="drop results below this seeder count")
    p.add_argument("--sort", choices=["seeders", "size", "name"], default="seeders", help="ordering")

    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--json", dest="fmt", action="store_const", const="json", help="output JSON")
    fmt.add_argument("--csv", dest="fmt", action="store_const", const="csv", help="output CSV")
    fmt.add_argument("--magnet", dest="fmt", action="store_const", const="magnet", help="output magnet URIs")
    fmt.add_argument("--links", dest="fmt", action="store_const", const="links", help="output .torrent/magnet URLs")
    p.set_defaults(fmt="table")

    p.add_argument("-d", "--download", metavar="DIR", nargs="?", const=".",
                   help="download a result over P2P into DIR (default current dir)")
    p.add_argument("--pick", type=int, default=1, metavar="N",
                   help="with --download, which result number to fetch (default 1)")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--list-sources", action="store_true", help="list sources and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _download(torrents, args) -> int:
    from .download import LibtorrentUnavailable, Progress, download
    if not (1 <= args.pick <= len(torrents)):
        print(f"error: --pick {args.pick} out of range (1..{len(torrents)})", file=sys.stderr)
        return 2
    t = torrents[args.pick - 1]
    print(f"Downloading: {t.name}  ({t.size_human})  [{t.provider}]", file=sys.stderr)

    def show(p: Progress):
        bar = ("#" * int(p.progress * 30)).ljust(30)
        sys.stderr.write(
            f"\r  [{bar}] {p.progress*100:5.1f}%  {p.state:<20} "
            f"peers={p.peers} seeds={p.seeds} {p.download_rate/1000:7.1f} kB/s"
        )
        sys.stderr.flush()

    from .magnet import TorrentUnavailable
    try:
        path = download(t, args.download, session=new_session(), on_progress=show)
    except LibtorrentUnavailable as exc:
        sys.stderr.write("\n")
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except TorrentUnavailable as exc:
        sys.stderr.write("\n")
        print(f"error: {exc}", file=sys.stderr)
        if args.pick < len(torrents):
            print(f"hint: retry with --pick {args.pick + 1}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted.\n")
        return 130
    sys.stderr.write("\n")
    print(f"Done -> {path}")
    sys.stdout.flush()
    _print_contents(path)
    return 0


# media extensions worth pointing the user straight at
_MEDIA_EXT = (".mp4", ".mkv", ".avi", ".m4v", ".mov", ".webm", ".ogv", ".iso",
              ".mp3", ".flac", ".ogg", ".m4a", ".wav", ".pdf", ".epub", ".zip")


def _print_contents(path: str, top: int = 8) -> None:
    """List what landed on disk (largest first) so nested media is easy to find."""
    import os
    if os.path.isfile(path):
        return  # the printed path already is the file
    files = []
    for root, _dirs, names in os.walk(path):
        for n in names:
            fp = os.path.join(root, n)
            try:
                files.append((os.path.getsize(fp), os.path.relpath(fp, path)))
            except OSError:
                pass
    if not files:
        return
    files.sort(reverse=True)
    media = [f for f in files if f[1].lower().endswith(_MEDIA_EXT)]
    print(f"  {len(files)} files, {human_size(sum(s for s, _ in files))}:", file=sys.stderr)
    for size, rel in (media or files)[:top]:
        print(f"    {human_size(size):>9}  {rel}", file=sys.stderr)
    extra = len(media or files) - top
    if extra > 0:
        print(f"    … and {extra} more", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_sources:
        for s in all_sources():
            print(f"  {s.name:<10} {s.label}")
        return 0

    query = " ".join(args.query).strip()
    if not query:
        print("error: nothing to search for. Try: torrent-search ubuntu", file=sys.stderr)
        return 2

    try:
        result = search(query, sources=args.source, limit=args.limit,
                        pattern=args.filter, min_seeders=args.min_seeders, sort=args.sort)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for name, err in result.errors.items():
        print(f"warning: source '{name}' failed: {err}", file=sys.stderr)

    if not result.torrents:
        print(f"No torrents found for {query!r}.", file=sys.stderr)
        return 1

    if args.download is not None:
        # Show the table first so the user knows what #pick refers to.
        print(render(result.torrents, "table", color=not args.no_color), file=sys.stderr)
        return _download(result.torrents, args)

    session = new_session() if args.fmt == "magnet" else None
    print(render(result.torrents, args.fmt, color=not args.no_color, session=session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
