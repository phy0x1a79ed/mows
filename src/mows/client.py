"""mows client — captures mouse/keyboard events and sends them over WebSocket."""

import asyncio
import json

import pyperclip
import websockets
from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener
from pynput.mouse import Listener as MouseListener

from .protocol import (
    key_press_event,
    key_release_event,
    mouse_click_event,
    mouse_move_event,
    mouse_scroll_event,
)

_TOGGLE = object()  # sentinel queued on Ctrl+Tab
_PUSH_CLIPBOARD = object()  # sentinel: read local clipboard and push to server


class EventBridge:
    """Bridges pynput listener threads to an asyncio queue.

    Hotkeys (always detected regardless of active/paused state):
      Ctrl+Tab  — toggle between ACTIVE and PAUSED
      Ctrl+Esc  — stop the client

    The keyboard listener runs for the entire session (never restarted)
    so hotkeys always work.  Only the mouse listener is restarted on
    toggle to change the suppress setting.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue,
                 suppress: bool = False):
        self._loop = loop
        self._queue = queue
        self._suppress = suppress
        self._active = True
        self._ctrl_pressed = False
        self._ctrl_key = None
        self._last_mouse_pos = None
        self._virtual_pos = None
        self._hotkey_down = False  # True while Ctrl+Tab is physically held

    def _put(self, data):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    # mouse callbacks
    def on_move(self, x, y):
        if not self._active:
            return
        if not self._suppress:
            # Real cursor moves freely — send actual absolute position.
            self._last_mouse_pos = (x, y)
            self._put(mouse_move_event(x, y))
        else:
            # Cursor is frozen; pynput reports frozen_pos + user_delta.
            if self._last_mouse_pos is None:
                # First event after activating suppress — pin the frozen
                # position and initialise the virtual cursor; no send yet
                # (no meaningful delta until the second event).
                self._last_mouse_pos = (x, y)
                self._virtual_pos = (x, y)
            else:
                lx, ly = self._last_mouse_pos
                vx, vy = self._virtual_pos
                dx, dy = x - lx, y - ly
                self._virtual_pos = (vx + dx, vy + dy)
                self._put(mouse_move_event(int(self._virtual_pos[0]),
                                           int(self._virtual_pos[1])))

    def on_click(self, x, y, button, pressed):
        if not self._active:
            return
        if not self._suppress:
            self._last_mouse_pos = (x, y)
        self._put(mouse_click_event(button, pressed))

    def on_scroll(self, x, y, dx, dy):
        if not self._active:
            return
        if not self._suppress:
            self._last_mouse_pos = (x, y)
        self._put(mouse_scroll_event(dx, dy))

    # keyboard callbacks
    def on_press(self, key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = True
            self._ctrl_key = key
            if self._active:
                self._put(key_press_event(key))
            return

        if self._ctrl_pressed:
            if key == Key.tab:
                if not self._hotkey_down:  # ignore key-repeat
                    self._hotkey_down = True
                    # Release Ctrl on the server before pausing
                    if self._active:
                        self._put(key_release_event(self._ctrl_key))
                    self._put(_TOGGLE)
                return
            if key == Key.esc:
                if self._active:
                    self._put(key_release_event(self._ctrl_key))
                self._put(None)  # sentinel: stop send loop
                return False  # stop keyboard listener

        if self._active:
            self._put(key_press_event(key))

    def on_release(self, key):
        if key == Key.tab:
            self._hotkey_down = False
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = False
        if self._active:
            self._put(key_release_event(key))
        elif self._ctrl_pressed and isinstance(key, KeyCode) and key.char == 'c':
            self._loop.call_later(0.15, self._queue.put_nowait, _PUSH_CLIPBOARD)


def _start_keyboard_listener(bridge, sup):
    kl = KeyboardListener(
        on_press=bridge.on_press,
        on_release=bridge.on_release,
        suppress=sup,
    )
    kl.start()
    return kl


def _start_mouse_listener(bridge, sup):
    ml = MouseListener(
        on_move=bridge.on_move,
        on_click=bridge.on_click,
        on_scroll=bridge.on_scroll,
        suppress=sup,
    )
    ml.start()
    return ml


async def _recv_loop(ws):
    try:
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "clipboard_push":
                pyperclip.copy(data["text"])
                print(f"clipboard received from server ({len(data['text'])} chars)")
    except websockets.ConnectionClosed:
        pass


async def _send(host: str, port: int, suppress: bool):
    uri = f"ws://{host}:{port}"
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    bridge = EventBridge(loop, queue, suppress=suppress)

    active = True
    kl = _start_keyboard_listener(bridge, suppress)
    ml = _start_mouse_listener(bridge, suppress)

    print(f"connecting to {uri} ...")
    try:
        async with websockets.connect(uri) as ws:
            recv_task = asyncio.create_task(_recv_loop(ws))
            mode = "suppress ON" if suppress else "suppress off"
            print(f"connected — ACTIVE ({mode}, Ctrl+Tab to toggle, Ctrl+Esc to stop)")
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    if event is _TOGGLE:
                        if ml is not None:
                            ml.stop()
                        kl.stop()
                        bridge._ctrl_pressed = False
                        bridge._hotkey_down = False
                        active = not active
                        bridge._active = active
                        bridge._last_mouse_pos = None
                        bridge._virtual_pos = None
                        if active:
                            bridge._suppress = suppress
                            kl = _start_keyboard_listener(bridge, suppress)
                            ml = _start_mouse_listener(bridge, suppress)
                            mode = "suppress ON" if suppress else "suppress off"
                            print(f"ACTIVE ({mode})")
                        else:
                            bridge._suppress = False
                            kl = _start_keyboard_listener(bridge, False)
                            ml = None
                            print("PAUSED (local input)")
                        continue
                    if event is _PUSH_CLIPBOARD:
                        text = pyperclip.paste()
                        await ws.send(json.dumps({"type": "clipboard_push", "text": text}))
                        print(f"clipboard pushed to server ({len(text)} chars)")
                        continue
                    await ws.send(event)
            finally:
                recv_task.cancel()
    finally:
        if ml is not None:
            ml.stop()
        kl.stop()
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
