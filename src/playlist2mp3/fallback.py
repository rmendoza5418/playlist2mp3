"""Find a YouTube video for tracks that spotDL could not match."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Callable

from .public import Track

_TRACK_URL = re.compile(r"https://open\.spotify\.com/track/[A-Za-z0-9]{22}")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOISE = re.compile(
    r"\b(?:official audio|official video|lyric video|lyrics|audio|visualizer)\b"
)
_TOPIC = re.compile(r"\s*-\s*topic\s*$")
_APOSTROPHES = re.compile(r"['’]")
_PUNCT = re.compile(r"[^\w\s]|_")
MAX_DURATION_DIFF = 5
MIN_TITLE_RATIO = 0.8
SEARCH_RESULTS = 10

Search = Callable[[str], list[dict[str, Any]]]


def parse_failed_urls(text: str) -> set[str]:
    """Return the Spotify track URLs found in a spotDL --save-errors file."""
    return set(_TRACK_URL.findall(text))


def normalize(s: str) -> str:
    """Lowercase and strip decoration so names compare fairly."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _BRACKETS.sub(" ", s)
    s = s.replace("&", " and ")
    s = _NOISE.sub(" ", s)
    s = _APOSTROPHES.sub("", s)
    s = _PUNCT.sub(" ", s)
    return " ".join(s.split())


def score(track: Track, entry: dict[str, Any]) -> float | None:
    """Score a search result for a track, or None if it must be rejected."""
    if not track.artists:
        return None
    title = normalize(str(entry.get("title") or ""))
    raw_channel = str(entry.get("channel") or entry.get("uploader") or "")
    is_topic = bool(_TOPIC.search(raw_channel.lower()))
    channel = normalize(_TOPIC.sub("", raw_channel.lower()))
    artist = normalize(track.artists[0])
    name = normalize(track.name)
    if not artist or not name:
        return None
    if artist not in channel and artist not in title:
        return None
    ratio = SequenceMatcher(None, name, title).ratio()
    if ratio < MIN_TITLE_RATIO and name not in title:
        return None
    diff = 0
    duration = entry.get("duration")
    if track.duration is not None and duration is not None:
        diff = abs(int(duration) - track.duration)
        if diff > MAX_DURATION_DIFF:
            return None
    return ratio * 100 + (20 if is_topic else 0) - diff


def yt_search(query: str) -> list[dict[str, Any]]:
    """Search YouTube with yt-dlp without downloading anything."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{SEARCH_RESULTS}:{query}", download=False)
    return [e for e in (info or {}).get("entries") or [] if e]


def find_video(track: Track, search: Search = yt_search) -> str | None:
    """Return the URL of the best matching video, or None."""
    if not track.artists:
        return None
    queries = [
        f"{' '.join(track.artists)} {track.name}",
        f"{track.artists[0]} - Topic {track.name}",
    ]
    for query in queries:
        try:
            entries = search(query)
        except Exception:
            continue
        best_id, best_score = None, None
        for entry in entries:
            video_id = str(entry.get("id") or "")
            if not _VIDEO_ID.match(video_id):
                continue
            s = score(track, entry)
            if s is not None and (best_score is None or s > best_score):
                best_id, best_score = video_id, s
        if best_id:
            return f"https://www.youtube.com/watch?v={best_id}"
    return None
