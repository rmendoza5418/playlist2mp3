import pytest

from playlist2mp3.public import Track

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


def test_main_playlist_without_client_id_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    assert cli.main(["--playlist", "Rock"]) == 2
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


PUB = "3vOpFtbXnFmFCKHAYGUlbk"
PUB_URL = f"https://open.spotify.com/playlist/{PUB}"


@pytest.fixture
def pub(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "ffmpeg_missing", lambda: False)
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return "trap soul & R&B\x1b", [Track(f"u{i}", "t", ["a"], 100) for i in range(100)]

    monkeypatch.setattr(cli, "fetch_public_playlist", fake_fetch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return type("R", (), {"returncode": 5})()

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls, fetched


def test_url_mode_end_to_end(pub, tmp_path, capsys):
    calls, fetched = pub
    rc = cli.main(["--url", PUB_URL + "?si=abc", "--output", str(tmp_path)])
    cmd, kw = calls[0]
    out = capsys.readouterr().out
    assert rc == 5
    assert kw["input"] == "\n"
    assert "--auth-token" not in cmd
    assert fetched == [PUB_URL]
    assert PUB_URL in cmd and not any("si=" in a for a in cmd)
    assert "Playlist: trap soul & R&B (100 tracks)" in out
    assert "\x1b" not in out
    assert (tmp_path / "trap soul & R&B").is_dir()


def test_url_mode_folder_from_name(pub, tmp_path):
    calls, _ = pub
    cli.main(["--url", PUB_URL, "--output", str(tmp_path)])
    template = next(a for a in calls[0][0] if "{artists}" in a)
    assert "trap soul & R&B" in template


def test_url_mode_dry_run(pub, capsys):
    calls, _ = pub
    assert cli.main(["--url", PUB_URL, "--dry-run"]) == 0
    assert calls == []
    assert "spotdl_shim" in capsys.readouterr().out


def test_url_mode_ffmpeg_missing(pub, monkeypatch):
    monkeypatch.setattr(cli, "ffmpeg_missing", lambda: True)
    assert cli.main(["--url", PUB_URL]) == 2


def test_url_rejects_bad_url():
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["--url", "https://example.com/x"])
    assert e.value.code == 2


def test_url_conflicts_with_playlist_and_official():
    p = cli.build_parser()
    with pytest.raises(SystemExit) as e:
        p.parse_args(["--url", PUB_URL, "--playlist", "x"])
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        p.parse_args(["--url", PUB_URL, "--official"])


def test_url_fetch_error_returns_1(pub, monkeypatch, capsys):
    def boom(url):
        raise RuntimeError("nope")

    monkeypatch.setattr(cli, "fetch_public_playlist", boom)
    assert cli.main(["--url", PUB_URL]) == 1
    err = capsys.readouterr().err
    assert "Is it public?" in err and "nope" in err
    assert pub[0] == []


def test_no_client_id_prompts_and_reprompts(pub, monkeypatch, capsys):
    answers = iter(["garbage", PUB_URL + "?si=z"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.main([]) == 5
    out = capsys.readouterr().out
    assert "SPOTIFY_CLIENT_ID is not set" in out and "Invalid URL" in out
    assert pub[1] == [PUB_URL]


def test_no_client_id_prompt_quit_and_eof(pub, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "q")
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 0

    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 0


def test_no_client_id_prompt_ctrl_c(pub, monkeypatch):
    def boom(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", boom)
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 130


def sp_url(c):
    return "https://open.spotify.com/track/" + c * 22


T1 = Track(sp_url("a"), "Under Your Skin", ["drill clinton"], 120)
T2 = Track(sp_url("b"), "lost lost", ["drill clinton"], 104)
T3 = Track(sp_url("c"), "Want U", ["dark & sexy"], None)
T4 = Track(sp_url("d"), "fine", ["x"], 100)
YT2 = "https://www.youtube.com/watch?v=N8m17jVNaFQ"


@pytest.fixture
def fb(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "ffmpeg_missing", lambda: False)
    monkeypatch.setattr(
        cli, "fetch_public_playlist", lambda url: ("PL", [T1, T2, T3, T4])
    )
    monkeypatch.setattr(
        cli, "find_video", lambda t: YT2 if t is T2 else None
    )
    state = {"calls": [], "pass2_fail": ""}

    def fake_run(cmd, **kw):
        state["calls"].append(cmd)
        err = cmd[cmd.index("--save-errors") + 1]
        n = len(state["calls"])
        if n == 1:
            text = "2024-01-01 00:00:00\n" + "".join(
                f"{t.url} - LookupError: No results found for song: x\n"
                for t in (T1, T2, T3)
            )
        else:
            text = state["pass2_fail"]
        if text:
            with open(err, "a") as f:
                f.write(text)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr("subprocess.run", fake_run)
    return state


def test_fallback_flow(fb, tmp_path, capsys):
    rc = cli.main(["--url", PUB_URL, "--output", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert len(fb["calls"]) == 2
    cmd2 = fb["calls"][1]
    assert f"{YT2}|{T2.url}" in cmd2
    assert PUB_URL not in cmd2
    assert "Searching YouTube for 3 tracks spotDL could not match..." in out
    assert "Done: 1 downloaded by spotDL, 1 by YouTube fallback, 2 missing" in out
    lines = (tmp_path / "PL" / "missing.txt").read_text().splitlines()
    assert lines == [
        f"drill clinton - Under Your Skin | {T1.url}",
        f"dark & sexy - Want U | {T3.url}",
    ]


def test_fallback_pass2_failure_is_missing(fb, tmp_path, capsys):
    fb["pass2_fail"] = f"{T2.url} - LookupError: boom\n"
    assert cli.main(["--url", PUB_URL, "--output", str(tmp_path)]) == 0
    assert "0 by YouTube fallback, 3 missing" in capsys.readouterr().out
    assert T2.url in (tmp_path / "PL" / "missing.txt").read_text()


def test_no_fallback_skips_pass2(fb, tmp_path, capsys):
    rc = cli.main(["--url", PUB_URL, "--output", str(tmp_path), "--no-fallback"])
    assert rc == 0 and len(fb["calls"]) == 1
    assert "3 missing" in capsys.readouterr().out


def test_stale_missing_removed(fb, monkeypatch, tmp_path):
    (tmp_path / "PL").mkdir()
    (tmp_path / "PL" / "missing.txt").write_text("old")
    monkeypatch.setattr(cli, "find_video", lambda t: YT2)
    assert cli.main(["--url", PUB_URL, "--output", str(tmp_path)]) == 0
    assert not (tmp_path / "PL" / "missing.txt").exists()


def test_crash_without_error_file_returns_code(monkeypatch, fb, tmp_path):
    monkeypatch.setattr(
        "subprocess.run", lambda cmd, **kw: type("R", (), {"returncode": 3})()
    )
    assert cli.main(["--url", PUB_URL, "--output", str(tmp_path)]) == 3
