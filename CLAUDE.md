# CLAUDE.md — Development Notes for mows

## Project structure

- `src/mows/` — Python package source
  - `cli.py` — CLI entry point with `serve`, `send`, `help` commands
  - `protocol.py` — JSON event serialization/deserialization
  - `server.py` — WebSocket server, replays events via pynput controllers
  - `client.py` — Captures events via pynput listeners, sends over WebSocket
  - `utils.py` — Package metadata (name, version, entry points)
  - `__main__.py` — `python -m mows` entry
- `envs/` — conda environment files
- `setup.py` — pip packaging
- `dev.sh` — build/run automation
- `conda_recipe/` — conda build recipe
- `Dockerfile` — container build

## Key commands

```bash
# Run from source
PYTHONPATH=src python -m mows help

# Or via dev.sh
./dev.sh -r help

# Create dev environment
./dev.sh --idev
```

## Architecture

- Client uses pynput listeners (background threads) that bridge to asyncio via `loop.call_soon_threadsafe` + `asyncio.Queue`
- Server uses `websockets.serve` async handler dispatching to pynput controllers
- Protocol is plain JSON, one message per event

## Dependencies

- `websockets` — async WebSocket client/server
- `pynput` — cross-platform input capture and replay
