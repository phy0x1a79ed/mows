# CLAUDE.md — Development Notes for mows

## Project structure

- `src/mows/` — Python package source
  - `cli.py` — CLI entry point with `serve`, `send`, `copy-to`, `copy-from`, `help` commands
  - `protocol.py` — JSON event serialization/deserialization (keys, buttons, mouse/keyboard events)
  - `server.py` — WebSocket server, replays events via pynput controllers; sends screen bounds on client connect; uses direct OS calls (`XWarpPointer`/`mouse_event`) for relative mouse movement to reduce drift
  - `client.py` — Captures events via pynput listeners, sends over WebSocket; suppress is on by default (`--no-suppress` to disable); clamps virtual cursor to server screen bounds
  - `utils.py` — Package metadata (name, version, entry points)
  - `__init__.py` — Package init
  - `__main__.py` — `python -m mows` entry
  - `version.txt` — Version string
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
- On toggle, **both** keyboard and mouse listeners are fully stopped and restarted:
  - **ACTIVE:** both listeners run with the original `suppress` setting; events are forwarded to the server
  - **PAUSED:** mouse listener is not started; keyboard listener runs with `suppress=False` so local input is never blocked
- Client runs a `_recv_loop` task on the WebSocket to handle incoming messages from the server (e.g. `clipboard_push`, `screen_bounds`)
- Server sends `screen_bounds` message on connect with the total virtual desktop rect `(x_min, y_min, x_max, y_max)` covering all monitors; client clamps virtual cursor to this rect when suppress is active
- Server uses `websockets.serve` async handler dispatching to pynput controllers
- Server bypasses pynput's `mouse.move()` for relative movement using direct OS calls (`_make_rel_mover()`): `XWarpPointer` on Linux, `mouse_event(MOUSEEVENTF_MOVE)` on Windows — avoids pynput's internal position read-back which causes drift
- Protocol is plain JSON, one message per event
- Clipboard transfer uses one-shot WebSocket connections (`copy-to` / `copy-from`)

## Bidirectional clipboard sync

- **ACTIVE — Ctrl+C on client:** key events are forwarded normally; server detects the Ctrl+C combo, waits 150 ms for the copy to complete, then pushes the server clipboard back to the client via a `clipboard_push` message
- **PAUSED — Ctrl+C on client:** the local app copies as normal (listener is unsuppressed); client detects the release of 'c' while Ctrl is held, waits 150 ms, then sends the local clipboard to the server via a `clipboard_push` message

## Client hotkeys

- **Ctrl+Tab** — toggle between ACTIVE and PAUSED (restarts both listeners)
- **Ctrl+Esc** — stop the client

## Dependencies

- `websockets` — async WebSocket client/server
- `pynput` — cross-platform input capture and replay
- `pyperclip` — clipboard read/write for clipboard transfer commands
