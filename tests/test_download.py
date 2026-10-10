import io

import pytest

from playlist2mp3.download import (
    UnavailablePlaylistError,
    build_spotdl_command,
    choose_mode,
    run_download,
    safe_folder_name,
)
from playlist2mp3.spotify import Playlist


def make(public=True, owner_id="other", collaborative=False):
    return Playlist("pid", "Name", "https://x/pid", owner_id, "Owner",
                    public, collaborative, 3)


def test_safe_folder_name_removes_braces_and_separators():
    out = safe_folder_name("a/b\\c:{artists}*?", "fb")
    assert not set('/\\:*?"<>|{}') & set(out)
    assert out == "abcartists"


def test_safe_folder_name_dots_and_empty():
    assert safe_folder_name("..", "fb") == "fb"
    assert safe_folder_name("  . . ", "fb") == "fb"
    assert safe_folder_name("", "fb") == "fb"
    assert safe_folder_name("{}", "fb") == "fb"


def test_safe_folder_name_keeps_unicode_and_collapses_space():
    assert safe_folder_name("  Música\t  日本語  ", "fb") == "Música 日本語"


def test_safe_folder_name_strips_control_and_truncates():
    assert safe_folder_name("a\x00b\nc", "fb") == "abc"
    assert len(safe_folder_name("x" * 400, "fb")) == 200


def test_choose_mode_public_is_free():
    assert choose_mode(make(public=True), "me") == "free"


def test_choose_mode_owned_private_is_official():
    assert choose_mode(make(public=False, owner_id="me"), "me") == "official"


def test_choose_mode_collab_is_official():
    assert choose_mode(make(public=None, collaborative=True), "me") == "official"


def test_choose_mode_foreign_private_raises():
    with pytest.raises(UnavailablePlaylistError):
        choose_mode(make(public=False), "me")


def test_choose_mode_force_official():
    assert choose_mode(make(public=True, owner_id="me"), "me", True) == "official"
    with pytest.raises(UnavailablePlaylistError):
        choose_mode(make(public=True), "me", True)


def test_build_command_free_has_no_token():
    cmd = build_spotdl_command(["u"], "out", "F")
    assert "--auth-token" not in cmd
    assert "--cookie-file" not in cmd
    assert cmd[1:4] == ["-m", "playlist2mp3._spotdl_shim", "download"]


def test_build_command_cookie_and_template():
    cmd = build_spotdl_command(["u"], "out", "F", cookie_file="c.txt")
    assert cmd[cmd.index("--cookie-file") + 1] == "c.txt"
    template = cmd[cmd.index("--output") + 1]
    assert template.endswith("{artists} - {title}.{output-ext}")
    assert template.startswith("out")
    assert "--auth-token" not in cmd


def test_build_command_multiple_queries_and_save_errors():
    cmd = build_spotdl_command(["a|b", "c|d"], "out", "F", save_errors="e.txt")
    i = cmd.index("download")
    assert cmd[i + 1:i + 3] == ["a|b", "c|d"]
    assert cmd[cmd.index("--save-errors") + 1] == "e.txt"
    assert "--save-errors" not in build_spotdl_command(["u"], "out", "F")


def test_run_download_sends_token_on_stdin(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return type("R", (), {"returncode": 3})()

    monkeypatch.setattr("subprocess.run", fake_run)
    assert run_download(["x"], tmp_path / "d", "SECRET") == 3
    assert seen["input"] == "SECRET\n" and seen["text"] is True
    run_download(["x"], tmp_path / "d")
    assert seen["input"] == "\n"


@pytest.mark.parametrize("name", ["CON", "nul", "Com1", "lpt9.txt", "aux.tar.gz"])
def test_safe_folder_name_reserved(name):
    assert safe_folder_name(name, "fb") == "_" + name


def test_safe_folder_name_not_reserved():
    assert safe_folder_name("console", "fb") == "console"
    assert safe_folder_name("com10", "fb") == "com10"


def test_safe_folder_name_truncates_bytes_on_emoji():
    out = safe_folder_name("\U0001F3B5" * 100, "fb")
    assert len(out.encode()) <= 200
    assert out == "\U0001F3B5" * 50


def test_shim_apply_token():
    from playlist2mp3._spotdl_shim import apply_token

    base = ["shim", "download", "u"]
    assert apply_token(base, io.StringIO("TOK\n")) == base + ["--auth-token", "TOK"]
    assert apply_token(base, io.StringIO("\n")) == base
    assert apply_token(base, io.StringIO("")) == base
    assert base == ["shim", "download", "u"]
