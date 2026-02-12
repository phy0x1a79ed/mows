"""mows client — captures mouse/keyboard events and sends them over WebSocket."""

import asyncio

import websockets
from pynput.keyboard import Listener as KeyboardListener
from pynput.mouse import Listener as MouseListener

from .protocol import (
    key_press_event,
    key_release_event,
    mouse_click_event,
    mouse_move_event,
    mouse_scroll_event,
)


class EventBridge:
    """Bridges pynput listener threads to an asyncio queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self._loop = loop
        self._queue = queue

    def _put(self, data: str):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    # mouse callbacks
    def on_move(self, x, y):
        self._put(mouse_move_event(x, y))

    def on_click(self, x, y, button, pressed):
        self._put(mouse_click_event(x, y, button, pressed))

    def on_scroll(self, x, y, dx, dy):
        self._put(mouse_scroll_event(x, y, dx, dy))

    # keyboard callbacks
    def on_press(self, key):
        self._put(key_press_event(key))

    def on_release(self, key):
        self._put(key_release_event(key))


async def _send(host: str, port: int):
    uri = f"ws://{host}:{port}"
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    bridge = EventBridge(loop, queue)

    mouse_listener = MouseListener(
        on_move=bridge.on_move,
        on_click=bridge.on_click,
        on_scroll=bridge.on_scroll,
    )
    keyboard_listener = KeyboardListener(
        on_press=bridge.on_press,
        on_release=bridge.on_release,
    )
    mouse_listener.start()
    keyboard_listener.start()

    print(f"connecting to {uri} ...")
    async with websockets.connect(uri) as ws:
        print(f"connected — streaming events (Ctrl+C to stop)")
        while True:
            event = await queue.get()
            await ws.send(event)


def run_client(host: str = "localhost", port: int = 8765):
    asyncio.run(_send(host, port))
