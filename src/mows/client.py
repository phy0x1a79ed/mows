"""mows client — captures mouse/keyboard events and sends them over WebSocket."""

import asyncio
import json

import pyperclip
import websockets
from pynput.keyboard import Key, Listener as KeyboardListener
from pynput.mouse import Listener as MouseListener

from .protocol import (
    key_press_event,
    key_release_event,
    mouse_click_event,
    mouse_move_event,
    mouse_scroll_event,
)


class EventBridge:
    """Bridges pynput listener threads to an asyncio queue.

    Detects Ctrl+Esc hotkey — sends key releases for both keys to the
    server, then queues a None sentinel to stop the send loop cleanly.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self._loop = loop
        self._queue = queue
        self._ctrl_pressed = False
        self._ctrl_key = None
        self._last_mouse_pos = None

    def _put(self, data):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    # mouse callbacks
    def on_move(self, x, y):
        if self._last_mouse_pos is not None:
            lx, ly = self._last_mouse_pos
            dx, dy = x - lx, y - ly
            if dx or dy:
                self._put(mouse_move_event(dx, dy))
        self._last_mouse_pos = (x, y)

    def on_click(self, x, y, button, pressed):
        self._last_mouse_pos = (x, y)
        self._put(mouse_click_event(button, pressed))

    def on_scroll(self, x, y, dx, dy):
        self._last_mouse_pos = (x, y)
        self._put(mouse_scroll_event(dx, dy))

    # keyboard callbacks
    def on_press(self, key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = True
            self._ctrl_key = key
        elif key == Key.esc and self._ctrl_pressed:
            # send releases so server doesn't have stuck keys
            self._put(key_release_event(Key.esc))
            self._put(key_release_event(self._ctrl_key))
            self._put(None)  # sentinel: stop send loop
            return False  # stop keyboard listener
        self._put(key_press_event(key))

    def on_release(self, key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = False
        self._put(key_release_event(key))


async def _send(host: str, port: int, suppress: bool):
    uri = f"ws://{host}:{port}"
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    bridge = EventBridge(loop, queue)

    mouse_listener = MouseListener(
        on_move=bridge.on_move,
        on_click=bridge.on_click,
        on_scroll=bridge.on_scroll,
        suppress=suppress,
    )
    keyboard_listener = KeyboardListener(
        on_press=bridge.on_press,
        on_release=bridge.on_release,
        suppress=suppress,
    )
    mouse_listener.start()
    keyboard_listener.start()

    print(f"connecting to {uri} ...")
    try:
        async with websockets.connect(uri) as ws:
            mode = "suppress ON" if suppress else "suppress off"
            print(f"connected — streaming events ({mode}, Ctrl+Esc to stop)")
            while True:
                event = await queue.get()
                if event is None:
                    break
                await ws.send(event)
    finally:
        mouse_listener.stop()
        keyboard_listener.stop()
        print("stopped")


def run_client(host: str = "localhost", port: int = 8765, suppress: bool = False):
    asyncio.run(_send(host, port, suppress))


# ── Clipboard ─────────────────────────────────────────────────────

async def _copy_to(host: str, port: int):
    uri = f"ws://{host}:{port}"
    text = pyperclip.paste()
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "clipboard_push", "text": text}))
    print(f"clipboard sent to server ({len(text)} chars)")


async def _copy_from(host: str, port: int):
    uri = f"ws://{host}:{port}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "clipboard_pull"}))
        response = await ws.recv()
    data = json.loads(response)
    pyperclip.copy(data["text"])
    print(f"clipboard received from server ({len(data['text'])} chars)")


def run_copy_to(host: str = "localhost", port: int = 8765):
    asyncio.run(_copy_to(host, port))


def run_copy_from(host: str = "localhost", port: int = 8765):
    asyncio.run(_copy_from(host, port))
