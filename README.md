# mows — Mouse Over WebSocket

Stream mouse and keyboard events from one machine to another over WebSocket. Captures input on the **client** and replays it on the **server**.

## Install

### conda/mamba

```bash
./dev.sh --ibase
conda activate mows
pip install -e .
```

### pip (requires system dependencies for pynput)

```bash
pip install .
```

## Usage

### Server (receiving machine)

Start the server on the machine where events should be replayed:

```bash
mows serve                        # defaults: 0.0.0.0:8765
mows serve --host 0.0.0.0 --port 9000
```

### Client (sending machine)

Start the client on the machine where input is captured:

```bash
mows send                         # defaults: localhost:8765
mows send --host 192.168.1.50 --port 9000
```

### Help

```bash
mows help
mows serve --help
mows send --help
```

## Development

`./dev.sh` automates common development tasks. Change `NAME` and `USER` at the top before use.

```bash
./dev.sh --idev     # create conda dev environment
./dev.sh -r help    # run from source
./dev.sh -bp        # build pip package
./dev.sh -bc        # build conda package
./dev.sh -bd        # build docker image
```

## Protocol

Events are streamed as JSON over WebSocket. Mouse movement is **relative** (deltas), so client and server screen sizes don't need to match.

| Type | Fields |
|------|--------|
| `mouse_move` | `dx`, `dy` (relative) |
| `mouse_click` | `button`, `pressed` |
| `mouse_scroll` | `dx`, `dy` |
| `key_press` | `key` |
| `key_release` | `key` |

## License

GPLv3 — see `LICENSE`.
