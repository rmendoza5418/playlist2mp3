"""Spotify authentication and playlist listing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import spotipy
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

SCOPE = "playlist-read-private playlist-read-collaborative"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
CACHE_DIR = Path.home() / ".cache" / "playlist2mp3"
CACHE_FILE = CACHE_DIR / "token.json"


class ConfigError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Playlist:
    id: str
    name: str
    url: str
    owner_id: str
    owner_name: str
    public: bool | None
    collaborative: bool
    total: int | None


def get_config() -> tuple[str, str]:
    """Return (client_id, redirect_uri) from the environment."""
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    if not client_id:
        raise ConfigError(
            "SPOTIFY_CLIENT_ID is not set. Copy .env.example to .env and "
            "fill in your Spotify app client ID."
        )
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()
    return client_id, redirect_uri or DEFAULT_REDIRECT_URI


def make_auth_manager() -> SpotifyPKCE:
    """Build the PKCE auth manager with a private token cache."""
    client_id, redirect_uri = get_config()
    CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CACHE_DIR, 0o700)
    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_handler=CacheFileHandler(cache_path=str(CACHE_FILE)),
        open_browser=True,
    )


def authenticate() -> tuple[spotipy.Spotify, SpotifyPKCE]:
    """Log in and return the client plus its auth manager."""
    auth = make_auth_manager()
    auth.get_access_token()
    if CACHE_FILE.exists():
        os.chmod(CACHE_FILE, 0o600)
    return spotipy.Spotify(auth_manager=auth), auth


def track_total(raw: dict) -> int | None:
    """Read the track count from the `items` or the older `tracks` shape."""
    for key in ("items", "tracks"):
        block = raw.get(key)
        if isinstance(block, dict) and isinstance(block.get("total"), int):
            return block["total"]
    return None


def parse_playlist(raw: dict) -> Playlist:
    """Convert a raw API playlist object into a Playlist."""
    pid = raw["id"]
    owner = raw.get("owner") or {}
    owner_id = owner.get("id", "")
    url = (raw.get("external_urls") or {}).get("spotify") or (
        f"https://open.spotify.com/playlist/{pid}"
    )
    return Playlist(
        id=pid,
        name=raw.get("name") or pid,
        url=url,
        owner_id=owner_id,
        owner_name=owner.get("display_name") or owner_id,
        public=raw.get("public"),
        collaborative=bool(raw.get("collaborative")),
        total=track_total(raw),
    )


def list_playlists(sp: spotipy.Spotify) -> list[Playlist]:
    """Return all playlists of the current user."""
    playlists: list[Playlist] = []
    page = sp.current_user_playlists(limit=50, offset=0)
    while page:
        items = page.get("items") or []
        playlists.extend(
            parse_playlist(p) for p in items if p and p.get("id")
        )
        page = sp.next(page) if page.get("next") else None
    return playlists


def current_user_id(sp: spotipy.Spotify) -> str:
    """Return the Spotify id of the logged-in user."""
    return sp.current_user()["id"]
