import pytest

from playlist2mp3 import cli
from playlist2mp3.spotify import Playlist, list_playlists, parse_playlist, track_total


def pl(pid, name, **kw):
    base = dict(owner_id="me", owner_name="Me", public=True,
                collaborative=False, total=1)
    base.update(kw)
    return Playlist(pid, name, f"https://open.spotify.com/playlist/{pid}", **base)


A1 = "37i9dQZF1DXcBWIGoYBM5M"
B2 = "0vvXsWCC9xrXsKd4FyS8kM"
C3 = "5ZXkP2ZpWQkE0tR1b6YkPq"
PLAYLISTS = [pl(A1, "Rock"), pl(B2, "Jazz"), pl(C3, "jazz")]


def test_match_by_id():
    assert cli.match_playlist(PLAYLISTS, A1).name == "Rock"


def test_match_by_url():
    url = f"https://open.spotify.com/playlist/{B2}?si=xyz"
    assert cli.match_playlist(PLAYLISTS, url).id == B2
    assert cli.match_playlist(PLAYLISTS, f"spotify:playlist:{A1}").id == A1


def test_match_url_with_unknown_id_does_not_match():
    with pytest.raises(cli.PlaylistMatchError):
        cli.match_playlist(PLAYLISTS, "https://open.spotify.com/playlist/" + "Z" * 22)


def test_match_id_substring_is_not_a_match():
    with pytest.raises(cli.PlaylistMatchError):
        cli.match_playlist(PLAYLISTS, A1[:10])


def test_match_by_name_case_insensitive():
    assert cli.match_playlist(PLAYLISTS, "rOCK").id == A1


def test_match_ambiguous_lists_candidates():
    with pytest.raises(cli.PlaylistMatchError) as e:
        cli.match_playlist(PLAYLISTS, "JAZZ")
    assert B2 in str(e.value) and C3 in str(e.value)


def test_match_none():
    with pytest.raises(cli.PlaylistMatchError):
        cli.match_playlist(PLAYLISTS, "nope")


def test_track_total_shapes():
    assert track_total({"items": {"total": 5}}) == 5
    assert track_total({"tracks": {"total": 7}}) == 7
    assert track_total({}) is None


def test_parse_playlist_url_fallback_and_total():
    p = parse_playlist({"id": "z", "name": "N", "owner": {"id": "o"},
                        "items": {"total": 2}})
    assert p.url == "https://open.spotify.com/playlist/z"
    assert p.total == 2 and p.owner_name == "o"


def test_list_playlists_paginates_and_skips_none():
    pages = {
        0: {"items": [{"id": "1", "name": "A", "owner": {"id": "o"}}, None],
            "next": "n"},
        1: {"items": [{"id": "2", "name": "B", "owner": {"id": "o"}}],
            "next": None},
    }

    class Fake:
        def current_user_playlists(self, limit, offset):
            return pages[0]

        def next(self, result):
            return pages[1]

    assert [p.id for p in list_playlists(Fake())] == ["1", "2"]


def test_picker_reprompts_on_invalid(monkeypatch, capsys):
    answers = iter(["x", "0", "9", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.pick_playlist(PLAYLISTS, "me").id == B2
    assert capsys.readouterr().out.count("Invalid choice") == 3


def test_picker_quit_exits_zero(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "q")
    with pytest.raises(SystemExit) as e:
        cli.pick_playlist(PLAYLISTS, "me")
    assert e.value.code == 0


def test_picker_ctrl_c_exits_130(monkeypatch):
    def boom(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", boom)
    with pytest.raises(SystemExit) as e:
        cli.pick_playlist(PLAYLISTS, "me")
    assert e.value.code == 130


def test_row_marks_unavailable():
    row = cli.format_row(1, pl("x", "P", public=False, owner_id="z", owner_name="Zed"), "me")
    assert "(unavailable)" in row and "by Zed" in row


def test_main_missing_client_id(monkeypatch, capsys):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    assert cli.main([]) == 2
    assert ".env.example" in capsys.readouterr().err


def test_picker_eof_exits_zero(monkeypatch):
    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(SystemExit) as e:
        cli.pick_playlist(PLAYLISTS, "me")
    assert e.value.code == 0


def test_picker_upper_case_q(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Q")
    with pytest.raises(SystemExit) as e:
        cli.pick_playlist(PLAYLISTS, "me")
    assert e.value.code == 0


def test_list_playlists_items_none_and_missing_id():
    class Fake:
        def current_user_playlists(self, limit, offset):
            return {"items": None, "next": None}

    assert list_playlists(Fake()) == []

    class Fake2:
        def current_user_playlists(self, limit, offset):
            return {"items": [{"name": "x"}, {"id": ""}], "next": None}

    assert list_playlists(Fake2()) == []


def test_row_strips_control_chars():
    row = cli.format_row(1, pl("x", "Evil\x1b[2J", owner_id="z", owner_name="Z\x07"), "me")
    assert "\x1b" not in row and "\x07" not in row


def test_output_rejects_braces():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--output", "a{b}"])


def test_bitrate_choices():
    p = cli.build_parser()
    assert p.parse_args(["--bitrate", "auto"]).bitrate == "auto"
    assert p.parse_args(["--bitrate", "5"]).bitrate == "5"
    with pytest.raises(SystemExit):
        p.parse_args(["--bitrate", "999k"])


class FakeAuth:
    def get_access_token(self):
        return "TOKEN123"


@pytest.fixture
def env(monkeypatch):
    from playlist2mp3 import spotify

    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "ffmpeg_missing", lambda: False)
    monkeypatch.setattr(spotify, "authenticate", lambda: (object(), FakeAuth()))
    monkeypatch.setattr(spotify, "current_user_id", lambda sp: "me")
    monkeypatch.setattr(spotify, "list_playlists", lambda sp: [
        pl(A1, "Rock"),
        pl(B2, "Mine", public=False),
    ])
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return type("R", (), {"returncode": 7})()

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls


def test_main_free_route(env, tmp_path):
    rc = cli.main(["--playlist", "Rock", "--output", str(tmp_path)])
    cmd, kw = env[0]
    assert rc == 7
    assert kw["input"] == "\n"
    assert "--auth-token" not in cmd


def test_main_official_route_token_on_stdin_only(env, tmp_path):
    cli.main(["--playlist", "Mine", "--output", str(tmp_path)])
    cmd, kw = env[0]
    assert kw["input"] == "TOKEN123\n"
    assert not any("TOKEN123" in a for a in cmd)
    assert "--auth-token" not in cmd


def test_main_dry_run_never_prints_token(env, capsys):
    assert cli.main(["--playlist", "Mine", "--dry-run"]) == 0
    assert "TOKEN123" not in capsys.readouterr().out
    assert env == []


def test_main_empty_playlists(env, monkeypatch, capsys):
    from playlist2mp3 import spotify

    monkeypatch.setattr(spotify, "list_playlists", lambda sp: [])
    assert cli.main([]) == 0
    assert "No playlists" in capsys.readouterr().out
    assert env == []


def test_main_spotify_error_returns_1(env, monkeypatch, capsys):
    import spotipy
    from playlist2mp3 import spotify

    def boom(sp):
        raise spotipy.SpotifyException(403, -1, "Forbidden")

    monkeypatch.setattr(spotify, "list_playlists", boom)
    assert cli.main([]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Error:") and "User Management" in err


def test_main_keyboard_interrupt_returns_130(env, monkeypatch):
    from playlist2mp3 import spotify

    def boom():
        raise KeyboardInterrupt

    monkeypatch.setattr(spotify, "authenticate", boom)
    assert cli.main([]) == 130


def test_main_no_match_returns_2(env, capsys):
    assert cli.main(["--playlist", "nope"]) == 2
