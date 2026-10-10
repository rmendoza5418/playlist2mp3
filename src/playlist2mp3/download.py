"""Folder naming, routing, and spotDL command handling."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .spotify import Playlist

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DISPLAY_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_FORBIDDEN = re.compile(r'[/\\:*?"<>|{}]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
MAX_NAME_BYTES = 200


class UnavailablePlaylistError(Exception):
    """Raised when a playlist cannot be read with the current API rules."""


def strip_control(text: str) -> str:
    """Remove control characters so names cannot inject terminal escapes."""
    return _DISPLAY_CONTROL.sub("", text)


def safe_folder_name(name: str, fallback: str) -> str:
    """Return a filesystem-safe folder name without spotDL template braces."""
    cleaned = _CONTROL.sub("", name)
    cleaned = _FORBIDDEN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = cleaned.encode()[:MAX_NAME_BYTES].decode("utf-8", "ignore").strip(" .")
    if not cleaned:
        return fallback
    if _RESERVED.match(cleaned):
        cleaned = "_" + cleaned
    return cleaned


def is_downloadable(playlist: Playlist, user_id: str) -> bool:
    """Return True if the playlist can be read."""
    return (
        playlist.public is True
        or playlist.owner_id == user_id
        or playlist.collaborative
    )


def choose_mode(playlist: Playlist, user_id: str, force_official: bool = False) -> str:
    """Return "free" or "official", or raise if the playlist is unreadable."""
    owned_or_collab = playlist.owner_id == user_id or playlist.collaborative
    if force_official:
        if owned_or_collab:
            return "official"
        raise UnavailablePlaylistError(
            "--official needs a playlist you own or collaborate on."
        )
    if playlist.public is True:
        return "free"
    if owned_or_collab:
        return "official"
    raise UnavailablePlaylistError(
        f"'{strip_control(playlist.name)}' is a private playlist owned by someone else. "
        "Spotify's 2026 API rules do not allow reading it."
    )


def build_spotdl_command(
    queries: list[str],
    output_dir: str | Path,
    folder: str,
    fmt: str = "mp3",
    bitrate: str = "320k",
    threads: int = 4,
    cookie_file: str | None = None,
    save_errors: str | Path | None = None,
) -> list[str]:
    """Build the spotDL argument list. The token goes through stdin, never here."""
    template = os.path.join(str(output_dir), folder, "{artists} - {title}.{output-ext}")
    cmd = [
        sys.executable, "-m", "playlist2mp3._spotdl_shim", "download", *queries,
        "--format", fmt,
        "--bitrate", bitrate,
        "--output", template,
        "--overwrite", "skip",
        "--print-errors",
        "--threads", str(threads),
    ]
    if cookie_file:
        cmd += ["--cookie-file", cookie_file]
    if save_errors:
        cmd += ["--save-errors", str(save_errors)]
    return cmd


def run_download(
    cmd: list[str], target_dir: str | Path, token: str | None = None
) -> int:
    """Create the target folder, run spotDL, and return its exit code."""
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        cmd, check=False, input=(token or "") + "\n", text=True
    ).returncode
