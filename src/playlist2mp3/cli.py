"""Command line interface."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import requests
import spotipy
import spotipy.oauth2
from dotenv import load_dotenv
from spotdl.utils.ffmpeg import get_ffmpeg_path

from . import __version__
from .fallback import find_video, parse_failed_urls
from .download import (
    UnavailablePlaylistError,
    build_spotdl_command,
    choose_mode,
    is_downloadable,
    run_download,
    safe_folder_name,
    strip_control,
)
from .public import Track, canonical_url, fetch_public_playlist, parse_playlist_id
from .spotify import ConfigError, Playlist

FORMATS = ["mp3", "flac", "ogg", "opus", "m4a", "wav"]
BITRATES = [
    "auto", "disable",
    "8k", "16k", "24k", "32k", "40k", "48k", "64k", "80k", "96k",
    "112k", "128k", "160k", "192k", "224k", "256k", "320k",
    *map(str, range(10)),
]
_PLAYLIST_ID = re.compile(r"playlist[/:]([A-Za-z0-9]{22})")
SPOTIFY_ERRORS = (
    spotipy.SpotifyException,
    spotipy.oauth2.SpotifyOauthError,
    requests.RequestException,
)


class PlaylistMatchError(Exception):
    """Raised when --playlist matches zero or several playlists."""


def positive_int(value: str) -> int:
    """Argparse type for integers >= 1."""
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return n


def existing_file(value: str) -> str:
    """Argparse type for a path that must exist."""
    if not os.path.isfile(value):
        raise argparse.ArgumentTypeError(f"file not found: {value}")
    return value


def output_dir(value: str) -> str:
    """Argparse type that rejects spotDL template braces."""
    if "{" in value or "}" in value:
        raise argparse.ArgumentTypeError("must not contain '{' or '}'")
    return value


def public_url(value: str) -> str:
    """Argparse type for a public Spotify playlist URL or URI."""
    if parse_playlist_id(value) is None:
        raise argparse.ArgumentTypeError(
            "not a Spotify playlist URL (expected https://open.spotify.com/playlist/<id>)"
        )
    return value.strip()


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    p = argparse.ArgumentParser(
        prog="playlist2mp3",
        description="Pick a Spotify playlist and download it with spotDL.",
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument("--url", metavar="URL", type=public_url,
                        help="public playlist URL (no login needed)")
    source.add_argument("--playlist", metavar="TEXT",
                        help="playlist id, URL, or exact name (skips the picker)")
    p.add_argument("--output", metavar="DIR", type=output_dir, default="output",
                   help="output directory (default: output)")
    p.add_argument("--format", choices=FORMATS, default="mp3")
    p.add_argument("--bitrate", choices=BITRATES, default="320k")
    p.add_argument("--threads", type=positive_int, default=4)
    p.add_argument("--cookie-file", metavar="PATH", type=existing_file)
    source.add_argument("--official", action="store_true",
                        help="force the official Spotify API (owned/collaborative only)")
    p.add_argument("--no-fallback", action="store_true",
                   help="do not search YouTube for tracks spotDL cannot match (--url only)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the spotDL command without running it")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def match_playlist(playlists: list[Playlist], query: str) -> Playlist:
    """Find one playlist by id, URL containing the id, or exact name."""
    query = query.strip()
    found = _PLAYLIST_ID.search(query)
    wanted = found.group(1) if found else query
    for pl in playlists:
        if pl.id == wanted:
            return pl
    named = [pl for pl in playlists if pl.name.casefold() == query.casefold()]
    if len(named) == 1:
        return named[0]
    if named:
        lines = "\n".join(f"  {pl.id}  {strip_control(pl.name)}" for pl in named)
        raise PlaylistMatchError(
            f"Several playlists are named '{strip_control(query)}'. "
            f"Use an id instead:\n{lines}"
        )
    raise PlaylistMatchError(f"No playlist matches '{strip_control(query)}'.")


def format_row(index: int, pl: Playlist, user_id: str) -> str:
    """Format one picker table row."""
    count = "?" if pl.total is None else str(pl.total)
    vis = {True: "public", False: "private"}.get(pl.public, "private")
    parts = [f"{index:>3}.", strip_control(pl.name), f"[{count} tracks]", vis]
    if pl.collaborative:
        parts.append("collab")
    if pl.owner_id != user_id:
        parts.append(f"by {strip_control(pl.owner_name)}")
    if not is_downloadable(pl, user_id):
        parts.append("(unavailable)")
    return "  ".join(parts)


def pick_playlist(playlists: list[Playlist], user_id: str) -> Playlist:
    """Show a numbered list and read a choice. Exits on q, EOF, or Ctrl-C."""
    for i, pl in enumerate(playlists, 1):
        print(format_row(i, pl, user_id))
    while True:
        try:
            answer = input(f"Select a playlist [1-{len(playlists)}, q to quit]: ").strip()
        except EOFError:
            print()
            sys.exit(0)
        except KeyboardInterrupt:
            print()
            sys.exit(130)
        if answer.lower() == "q":
            sys.exit(0)
        if answer.isdigit() and 1 <= int(answer) <= len(playlists):
            return playlists[int(answer) - 1]
        print("Invalid choice. Enter a number from the list or q.")


def prompt_public_url() -> str:
    """Ask for a public playlist URL. Exits on q, EOF, or Ctrl-C."""
    print("SPOTIFY_CLIENT_ID is not set, so the playlist picker is off.")
    while True:
        try:
            answer = input("Paste a public Spotify playlist URL (q to quit): ").strip()
        except EOFError:
            print()
            sys.exit(0)
        except KeyboardInterrupt:
            print()
            sys.exit(130)
        if answer.lower() == "q":
            sys.exit(0)
        if parse_playlist_id(answer):
            return answer
        print("Invalid URL. Paste a link like https://open.spotify.com/playlist/<id> or q.")


def ffmpeg_missing() -> bool:
    """Return True if spotDL cannot find ffmpeg."""
    return get_ffmpeg_path() is None


def main(argv: list[str] | None = None) -> int:
    """Entry point. Ctrl-C returns 130 without a traceback."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130


def _spotify_error(e: Exception) -> int:
    msg = f"Error: {e}"
    if getattr(e, "http_status", None) == 403:
        msg += (
            "\nHint: in development mode, add your Spotify account under "
            "User Management in the Spotify developer dashboard."
        )
    print(msg, file=sys.stderr)
    return 1


def _read_failed(path: Path) -> set[str] | None:
    """Return failed track URLs from a spotDL error file, or None if it is absent."""
    if not path.exists():
        return None
    return parse_failed_urls(path.read_text(encoding="utf-8", errors="replace"))


def _write_missing(folder: Path, missing: list[Track]) -> None:
    path = folder / "missing.txt"
    if not missing:
        path.unlink(missing_ok=True)
        return
    lines = [
        strip_control(f"{', '.join(t.artists)} - {t.name} | {t.url}") for t in missing
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_public(url: str, args: argparse.Namespace) -> int:
    """Download a public playlist, then try a YouTube fallback for unmatched tracks.

    Pass 1 runs spotDL on the playlist. Pass 2 searches YouTube for each track
    that pass 1 reported as failed and runs spotDL on "<youtube>|<spotify>" pairs.
    Tracks still missing are listed in missing.txt. The exit code is 0 when
    pass 1 or pass 2 ran, even with missing tracks. It is spotDL's own code only
    when pass 1 returned non-zero and wrote no error file (a crash).
    """
    playlist_id = parse_playlist_id(url)
    assert playlist_id is not None
    clean_url = canonical_url(playlist_id)
    try:
        name, tracks = fetch_public_playlist(clean_url)
    except Exception as e:
        print(
            f"Error: could not read playlist. Is it public?\n{strip_control(str(e))}",
            file=sys.stderr,
        )
        return 1
    print(f"Playlist: {strip_control(name)} ({len(tracks)} tracks)")
    folder = safe_folder_name(name, fallback=playlist_id)
    target = Path(args.output) / folder

    def command(queries: list[str], save_errors: Path | None = None) -> list[str]:
        return build_spotdl_command(
            queries, args.output, folder, args.format, args.bitrate,
            args.threads, args.cookie_file, save_errors,
        )

    if args.dry_run:
        print(" ".join(command([clean_url])))
        return 0
    print(f"Downloading (free mode) to {target}")
    with tempfile.TemporaryDirectory(prefix="playlist2mp3-") as tmp:
        err1 = Path(tmp) / "errors1.txt"
        rc = run_download(command([clean_url], err1), target, None)
        failed = _read_failed(err1)
        if failed is None:
            if rc != 0:
                return rc
            failed = set()
        by_url = {t.url: t for t in tracks}
        unmatched = [by_url[u] for u in sorted(failed) if u in by_url]
        by_spotdl = len(tracks) - len(unmatched)
        by_youtube = 0
        missing: list[Track] = []
        if unmatched and not args.no_fallback:
            print(
                f"Searching YouTube for {len(unmatched)} tracks "
                "spotDL could not match..."
            )
            pairs: list[str] = []
            paired: list[Track] = []
            for t in unmatched:
                video = find_video(t)
                if video:
                    pairs.append(f"{video}|{t.url}")
                    paired.append(t)
                else:
                    missing.append(t)
            if pairs:
                err2 = Path(tmp) / "errors2.txt"
                rc2 = run_download(command(pairs, err2), target, None)
                failed2 = _read_failed(err2)
                if failed2 is None:
                    failed2 = {t.url for t in paired} if rc2 != 0 else set()
                still = [t for t in paired if t.url in failed2]
                missing += still
                by_youtube = len(paired) - len(still)
        else:
            missing = unmatched
    _write_missing(target, missing)
    print(
        f"Done: {by_spotdl} downloaded by spotDL, {by_youtube} by YouTube "
        f"fallback, {len(missing)} missing (see missing.txt)"
    )
    return 0


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    from . import spotify

    url = args.url
    if not url and not args.playlist and not os.environ.get("SPOTIFY_CLIENT_ID", "").strip():
        url = prompt_public_url()

    if not url:
        try:
            spotify.get_config()
        except ConfigError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    if not args.dry_run and ffmpeg_missing():
        print(
            "Error: ffmpeg not found. Install it (e.g. `brew install ffmpeg`) "
            "or run `python -m spotdl --download-ffmpeg`.",
            file=sys.stderr,
        )
        return 2

    if url:
        return _run_public(url, args)

    try:
        sp, auth = spotify.authenticate()
        user_id = spotify.current_user_id(sp)
        playlists = spotify.list_playlists(sp)
    except SPOTIFY_ERRORS as e:
        return _spotify_error(e)
    if not playlists:
        print("No playlists found.")
        return 0

    try:
        if args.playlist:
            playlist = match_playlist(playlists, args.playlist)
        else:
            playlist = pick_playlist(playlists, user_id)
        mode = choose_mode(playlist, user_id, args.official)
    except (PlaylistMatchError, UnavailablePlaylistError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    folder = safe_folder_name(playlist.name, playlist.id)
    try:
        token = auth.get_access_token() if mode == "official" else None
    except SPOTIFY_ERRORS as e:
        return _spotify_error(e)
    cmd = build_spotdl_command(
        [playlist.url], args.output, folder, args.format, args.bitrate,
        args.threads, args.cookie_file,
    )
    if args.dry_run:
        print(" ".join(cmd))
        return 0
    print(
        f"Downloading '{strip_control(playlist.name)}' ({mode} mode) "
        f"to {Path(args.output) / folder}"
    )
    return run_download(cmd, Path(args.output) / folder, token)


if __name__ == "__main__":
    sys.exit(main())
