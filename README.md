# playlist2mp3

Pick one of your Spotify playlists, find each track on YouTube Music with spotDL, and save MP3s to `output/<playlist name>/`.

## Quick start (no Spotify Premium needed)

Copy the link of a public playlist and run:

```
playlist2mp3 --url "<public playlist link>"
```

To copy the link, open the playlist in Spotify. Select Share, then Copy link to playlist.

The playlist must be public. To download a private playlist, set it to public for the run. Then set it back to private.

If `SPOTIFY_CLIENT_ID` is not set, running `playlist2mp3` with no arguments asks you to paste a link.

## How it works

```
Spotify login (PKCE)
        |
        v
list your playlists
        |
        v
you pick one
        |
        v
     spotDL
        |
        v
  YouTube Music
        |
        v
     yt-dlp
        |
        v
     ffmpeg
        |
        v
output/<playlist>/
```

## Requirements

- Python 3.10 to 3.14
- ffmpeg. Install it with `brew install ffmpeg` or `python -m spotdl --download-ffmpeg`. The tool accepts the copy that spotDL downloads to `~/.spotdl`.
- Optional: a Spotify developer app, only for the playlist picker (see below).

## Optional: pick from your playlists (needs Spotify Premium)

The picker lists your own playlists, including private ones. It needs a Spotify developer app.

1. Create an app at https://developer.spotify.com/dashboard.
2. Select "Web API".
3. Add the redirect URI `http://127.0.0.1:8888/callback`. It must match exactly.
4. Copy the Client ID. You do not need the client secret, because the login uses PKCE.

Since February 2026, development-mode apps need the app owner to have Spotify Premium. They also allow only 5 users. Add each user under User Management in the dashboard.

## Install

With uv:

```
uv tool install git+https://github.com/rmendoza5418/playlist2mp3
```

With pipx:

```
pipx install git+https://github.com/rmendoza5418/playlist2mp3
```

For development:

```
git clone https://github.com/rmendoza5418/playlist2mp3
cd playlist2mp3
uv sync --extra dev --locked
```

`uv sync --locked` installs the exact versions in `uv.lock`. `uv tool install` has no `--locked` flag, so a tool install resolves versions fresh.

## Configure

Copy the example file and set your Client ID:

```
cp .env.example .env
```

| Variable | Required | Default |
| --- | --- | --- |
| `SPOTIFY_CLIENT_ID` | yes | none |
| `SPOTIFY_REDIRECT_URI` | no | `http://127.0.0.1:8888/callback` |

If you change `SPOTIFY_REDIRECT_URI`, register the same value in the Spotify dashboard.

## Usage

Run the tool with no arguments. The first run opens a browser for Spotify login. The tool then prints a numbered list of your playlists.

```
$ playlist2mp3
  1.  Road Trip  [42 tracks]  private
  2.  Focus  [80 tracks]  public
  3.  Friend Mix  [25 tracks]  private  by Sam  (unavailable)
Select a playlist [1-3, q to quit]: 2
Downloading 'Focus' (free mode) to output/Focus
```

Skip the picker with `--playlist`. It accepts a playlist ID, a playlist URL, or an exact name:

```
playlist2mp3 --playlist "Road Trip" --output ~/Music --threads 8
```

Preview the spotDL command without downloading:

```
playlist2mp3 --playlist "Road Trip" --dry-run
```

| Flag | Default | Description |
| --- | --- | --- |
| `--url URL` | none | Public playlist URL. No login or client ID needed. Cannot combine with `--playlist` or `--official`. |
| `--playlist TEXT` | none | Playlist ID, URL, or exact name. Skips the picker. |
| `--output DIR` | `output` | Output directory. Files go to `DIR/<playlist name>/`. It must not contain `{` or `}`. |
| `--format` | `mp3` | One of `mp3`, `flac`, `ogg`, `opus`, `m4a`, `wav`. |
| `--bitrate` | `320k` | Target bitrate. One of `auto`, `disable`, `8k` to `320k`, or `0` to `9`. |
| `--threads` | `4` | Parallel downloads. Must be 1 or higher. |
| `--cookie-file PATH` | none | Cookies file for YouTube Music. The file must exist. |
| `--official` | off | Force the official Spotify API. Works for playlists you own or collaborate on. |
| `--no-fallback` | off | With `--url`, do not search YouTube for tracks spotDL cannot match. |
| `--dry-run` | off | Print the spotDL command and exit. The token is hidden. |
| `--version` | | Print the version. |

Files are named `{artists} - {title}.{ext}`. spotDL skips files that already exist, so you can re-run a playlist to fetch new tracks.

## When spotDL cannot match a track

With `--url`, spotDL sometimes finds no match for small artists. The tool then searches YouTube itself for each failed track. It passes the video it finds to spotDL, which downloads it with the Spotify tags.

A video is accepted only if all of these are true:

- The main artist is in the channel name (without " - Topic") or in the video title.
- The title is at least 80% similar to the track name, or the track name is inside the video title.
- If both lengths are known, they differ by 5 seconds or less.

Auto-generated "Artist - Topic" uploads rank higher.

Tracks with no accepted video, or that still fail, are listed in `missing.txt` in the playlist folder. Each line has the form `artist - title | Spotify URL`. The tool deletes an old `missing.txt` when nothing is missing.

The run ends with a line like `Done: 88 downloaded by spotDL, 9 by YouTube fallback, 3 missing (see missing.txt)`. Use `--no-fallback` to skip the YouTube search. Picker and `--official` modes have no fallback.

## Which playlists work

| Playlist | Works | How |
| --- | --- | --- |
| Public, any owner | Yes | spotDL public reader |
| Private, you own or collaborate | Yes | Your login token |
| Private, owned by someone else | No | Spotify API rule since February 2026 |
| Spotify-made (Daily Mix, Discover Weekly) | Not guaranteed | Spotify restricts these |

## Audio quality

YouTube streams about 128 to 160 kbps. With YouTube Music Premium cookies passed through `--cookie-file`, the source reaches 256 kbps AAC. The default 320k MP3 does not add quality beyond the source. Use `--bitrate auto` to match the source size.

## Security notes

- The login token is cached at `~/.cache/playlist2mp3/token.json` with `0600` permissions.
- Never commit `.env`.
- URL mode uses spotDL's unofficial public reader. It contacts Spotify's web player endpoints. It may fetch a secret from code.thetadev.de. If that fails, spotDL uses a built-in default.
- For private playlists, the tool passes the short-lived token to spotDL through stdin. It never appears on the command line or in the process list.
- The repository includes `uv.lock`. Dependabot proposes updates each week.

## Running tests

```
.venv/bin/pytest -q
```

## Legal

Downloading from YouTube can violate YouTube's Terms of Service and copyright law. Use this tool for personal use with music you have rights to. This project is not affiliated with Spotify or YouTube.

## Credits and license

Built on [spotDL](https://github.com/spotDL/spotify-downloader), [spotipy](https://github.com/spotipy-dev/spotipy), and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Licensed under the MIT License.
