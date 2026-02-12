"""mows client — captures mouse/keyboard events and sends them over WebSocket."""

import asyncio

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

    Detects Ctrl+Esc hotkey and signals the stop_event instead of
    forwarding those keys to the server.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue,
                 stop_event: asyncio.Event):
        self._loop = loop
        self._queue = queue
        self._stop_event = stop_event
        self._ctrl_pressed = False
        self._last_mouse_pos = None

    def _put(self, data: str):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    def _signal_stop(self):
        self._loop.call_soon_threadsafe(self._stop_event.set)

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
        elif key == Key.esc and self._ctrl_pressed:
            self._signal_stop()
            return False  # stops the keyboard listener
        self._put(key_press_event(key))

    def on_release(self, key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = False
        self._put(key_release_event(key))


async def _send(host: str, port: int, suppress: bool):
    uri = f"ws://{host}:{port}"
    queue: asyncio.Queue = asyncio.Queue()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    bridge = EventBridge(loop, queue, stop_event)

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

            async def send_events():
                while True:
                    event = await queue.get()
                    await ws.send(event)

            send_task = asyncio.create_task(send_events())
            stop_task = asyncio.create_task(stop_event.wait())

            done, pending = await asyncio.wait(
                [send_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    finally:
        mouse_listener.stop()
        keyboard_listener.stop()
        print("stopped")


def run_client(host: str = "localhost", port: int = 8765, suppress: bool = False):
    asyncio.run(_send(host, port, suppress))
