import pytest

from playlist2mp3.public import canonical_url, parse_playlist_id

ID = "3vOpFtbXnFmFCKHAYGUlbk"


@pytest.mark.parametrize("text", [
    f"https://open.spotify.com/playlist/{ID}",
    f"https://open.spotify.com/playlist/{ID}?si=65db968a6cf54cf2",
    f"https://open.spotify.com/intl-de/playlist/{ID}?si=x",
    f"spotify:playlist:{ID}",
    f"  https://open.spotify.com/playlist/{ID}  ",
])
def test_parse_valid(text):
    assert parse_playlist_id(text) == ID


@pytest.mark.parametrize("text", [
    "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
    "garbage",
    "",
    f"https://open.spotify.com/playlist/{ID[:21]}",
    f"https://open.spotify.com/playlist/{ID}x",
    f"https://evil.example/playlist/{ID}",
])
def test_parse_invalid(text):
    assert parse_playlist_id(text) is None


def test_canonical_url():
    assert canonical_url(ID) == f"https://open.spotify.com/playlist/{ID}"
