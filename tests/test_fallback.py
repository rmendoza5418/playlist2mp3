import pytest

from playlist2mp3.fallback import find_video, normalize, parse_failed_urls, score
from playlist2mp3.public import Track

TRACK = Track("https://open.spotify.com/track/" + "a" * 22, "lost lost",
              ["drill clinton"], 104)


def entry(title="lost lost", channel="drill clinton - Topic", duration=105, id="N8m17jVNaFQ"):
    return {"id": id, "title": title, "channel": channel, "duration": duration}


def test_normalize():
    assert normalize("Dark & Sexy (feat. X) [Remix]") == "dark and sexy"
    assert normalize("Lost Lost - Official Audio") == "lost lost"
    assert normalize("Beyoncé  Don't Stop!!") == "beyonce dont stop"
    assert normalize("Song Lyric Video") == "song"


def test_score_topic_channel_accepted():
    assert score(TRACK, entry()) is not None


def test_score_topic_bonus_beats_plain_channel():
    plain = score(TRACK, entry(channel="drill clinton"))
    assert score(TRACK, entry()) > plain


def test_score_wrong_artist_rejected():
    assert score(TRACK, entry(channel="someone else - Topic")) is None


def test_score_artist_in_title_accepted():
    e = entry(title="drill clinton - lost lost", channel="Random Uploads")
    assert score(TRACK, e) is not None


def test_score_duration_off_rejected():
    assert score(TRACK, entry(duration=114)) is None


def test_score_none_duration_accepted():
    assert score(TRACK, entry(duration=None)) is not None
    no_dur = Track(TRACK.url, TRACK.name, TRACK.artists, None)
    assert score(no_dur, entry()) is not None


def test_score_official_audio_suffix_accepted():
    assert score(TRACK, entry(title="lost lost (Official Audio)")) is not None


def test_score_title_mismatch_rejected():
    assert score(TRACK, entry(title="completely different")) is None


def test_score_uses_uploader_when_no_channel():
    e = {"id": "N8m17jVNaFQ", "title": "lost lost", "uploader": "drill clinton - Topic",
         "duration": 105}
    assert score(TRACK, e) is not None


def test_find_video_first_query():
    queries = []

    def search(q):
        queries.append(q)
        return [entry()]

    assert find_video(TRACK, search) == "https://www.youtube.com/watch?v=N8m17jVNaFQ"
    assert queries == ["drill clinton lost lost"]


def test_find_video_second_query_used():
    def search(q):
        return [entry()] if "Topic" in q else [entry(channel="other")]

    assert find_video(TRACK, search) == "https://www.youtube.com/watch?v=N8m17jVNaFQ"


def test_find_video_bad_id_rejected():
    assert find_video(TRACK, lambda q: [entry(id="short")]) is None


def test_find_video_search_error_continues():
    calls = []

    def search(q):
        calls.append(q)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return [entry()]

    assert find_video(TRACK, search) is not None
    assert len(calls) == 2


def test_find_video_none_when_nothing():
    assert find_video(TRACK, lambda q: []) is None


def test_parse_failed_urls():
    text = (
        "2026-10-10 12:00:00\n"
        "https://open.spotify.com/track/4cTRX4L6uJnNRAc9y7mD9V - LookupError: "
        "No results found for song: drill clinton - Under Your Skin\n"
        "https://open.spotify.com/track/0j9BaR2Y6OqqJOeDxSWvyb - LookupError: x\n"
        "https://open.spotify.com/track/4cTRX4L6uJnNRAc9y7mD9V - LookupError: dup\n"
    )
    assert parse_failed_urls(text) == {
        "https://open.spotify.com/track/4cTRX4L6uJnNRAc9y7mD9V",
        "https://open.spotify.com/track/0j9BaR2Y6OqqJOeDxSWvyb",
    }
    assert parse_failed_urls("") == set()
