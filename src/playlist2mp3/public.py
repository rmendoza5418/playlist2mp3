"""No-login reading of public playlists through spotDL's free client."""

from __future__ import annotations

import re
from dataclasses import dataclass

_URL = re.compile(
    r"^https://open\.spotify\.com/(?:intl-[A-Za-z]{2,}(?:-[A-Za-z]+)?/)?"
    r"playlist/([A-Za-z0-9]{22})/?(?:[?#].*)?$"
)
_URI = re.compile(r"^spotify:playlist:([A-Za-z0-9]{22})$")


@dataclass(frozen=True)
class Track:
    """One playlist track as read from Spotify."""

    url: str
    name: str
    artists: list[str]
    duration: int | None


def parse_playlist_id(text: str) -> str | None:
    """Return the playlist id from a Spotify playlist URL or URI, else None."""
    text = text.strip()
    found = _URL.match(text) or _URI.match(text)
    return found.group(1) if found else None


def canonical_url(playlist_id: str) -> str:
    """Return the plain playlist URL without tracking parameters."""
    return f"https://open.spotify.com/playlist/{playlist_id}"


def fetch_public_playlist(url: str) -> tuple[str, list[Track]]:
    """Return (name, tracks) of a public playlist. Needs no credentials."""
    from spotdl.types.playlist import Playlist
    from spotdl.utils.spotify import SpotifyClient

    # init() raises if a client already exists in this process.
    try:
        SpotifyClient()
    except Exception:
        SpotifyClient.init(client_id="", client_secret="")
    meta, songs = Playlist.get_metadata(url)
    tracks = [
        Track(
            url=str(song.url),
            name=str(song.name),
            artists=[str(a) for a in (song.artists or [])],
            duration=int(song.duration) if song.duration else None,
        )
        for song in songs
    ]
    return str(meta.get("name") or ""), tracks
