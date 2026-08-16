# yt-dlp Manager

A small, local-first web interface for downloading supported media with the bundled `yt-dlp` engine. It queues one download at a time, records job history in SQLite, and supports browser or uploaded Netscape-format cookies for sites that need authentication.

The interface is intentionally bound to `127.0.0.1`; it is not designed as a network service.

The package also installs the full `yt-dlp` command-line interface, so any yt-dlp feature not represented in the manager interface remains available.

## Requirements

- Python 3.10 or newer
- `ffmpeg` on your `PATH` for merging separate audio/video streams or converting media

## Run locally

Using [uv](https://docs.astral.sh/uv/):

```powershell
uv sync
uv run yt-dlp-manager web
```

Then open <http://127.0.0.1:8765>.

Downloads are written to `downloads/` and job history is stored in `yt-dlp-manager.sqlite3` by default. Both locations can be changed:

```powershell
uv run yt-dlp-manager --database data/jobs.sqlite3 web --port 9000 --download-directory D:\Media\Downloads
```

## Full yt-dlp CLI

```powershell
uv run yt-dlp --help
uv run yt-dlp "https://example.com/video"
```

## Command-line queue

```powershell
uv run yt-dlp-manager add "https://example.com/video"
uv run yt-dlp-manager list
uv run yt-dlp-manager show <job-id>
```

## Development

```powershell
uv run pytest
```

The project vendors yt-dlp under `yt_dlp/` because the manager invokes its Python API directly and ships its CLI. Its runtime modules should be updated as a unit; selectively pruning extractors or helpers can break dynamic imports. Upstream release, CI, packaging, and test infrastructure is intentionally not included; update the vendored runtime as a single replacement rather than merging upstream repository history.

## Licence and notices

This project and the included yt-dlp source use the Unlicense. See [LICENSE](LICENSE) and [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt) for dependency notices.
