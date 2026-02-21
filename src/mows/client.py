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

_TOGGLE   = object()  # sentinel: Ctrl+Tab detected, toggle direction
_ACTIVATE = object()  # sentinel: all keys/buttons released, complete activation
_PUSH_CLIPBOARD = object()  # sentinel: read local clipboard and push to server


class EventBridge:
    """Bridges pynput listener threads to an asyncio queue.

    Hotkeys (always detected regardless of active/paused state):
      Ctrl+Tab  — toggle between ACTIVE and PAUSED
      Ctrl+Esc  — stop the client

    On toggle, both keyboard and mouse listeners are fully stopped/restarted.
    PAUSED starts keyboard with suppress=False so local input is never blocked.
    PAUSED→ACTIVE is deferred: we wait for all held keys and mouse buttons to
    be released before going ACTIVE, to avoid ghost key-presses on the server.
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
        self._hotkey_down = False    # True while Ctrl+Tab is physically held
        self._activating = False     # True while waiting for key/button release
        self._all_held_keys = set()  # all physically pressed keys (always tracked)
        self._activating_mouse = set()  # mouse buttons held during activating wait
        self._screen_bounds = None   # (x_min, y_min, x_max, y_max) from server

    def _put(self, data):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    def _check_activate(self):
        """Fire _ACTIVATE when all held keys and mouse buttons are released."""
        if self._activating and not self._all_held_keys and not self._activating_mouse:
            self._activating = False
            self._put(_ACTIVATE)

    # mouse callbacks
    def on_move(self, x, y):
        if self._activating or not self._active:
            return
        if not self._suppress:
            # Real cursor moves freely — send actual absolute position.
            self._last_mouse_pos = (x, y)
            self._put(mouse_move_event(x, y))
        else:
            # Cursor is frozen; pynput reports frozen_pos + user_delta.
            if self._last_mouse_pos is None:
                self._last_mouse_pos = (x, y)
                self._virtual_pos = (x, y)
            else:
                lx, ly = self._last_mouse_pos
                vx, vy = self._virtual_pos
                dx, dy = x - lx, y - ly
                vx, vy = vx + dx, vy + dy
                if self._screen_bounds:
                    x0, y0, x1, y1 = self._screen_bounds
                    vx = max(x0, min(vx, x1 - 1))
                    vy = max(y0, min(vy, y1 - 1))
                self._virtual_pos = (vx, vy)
                self._put(mouse_move_event(int(vx), int(vy)))

    def on_click(self, x, y, button, pressed):
        if self._activating:
            if pressed:
                self._activating_mouse.add(button)
            else:
                self._activating_mouse.discard(button)
                self._check_activate()
            return
        if not self._active:
            return
        if not self._suppress:
            self._last_mouse_pos = (x, y)
        self._put(mouse_click_event(button, pressed))

    def on_scroll(self, x, y, dx, dy):
        if self._activating or not self._active:
            return
        if not self._suppress:
            self._last_mouse_pos = (x, y)
        self._put(mouse_scroll_event(dx, dy))

    # keyboard callbacks
    def on_press(self, key):
        self._all_held_keys.add(key)

        if self._activating:
            # Only allow stop hotkey through while waiting
            if key in (Key.ctrl_l, Key.ctrl_r):
                self._ctrl_pressed = True
                self._ctrl_key = key
            elif self._ctrl_pressed and key == Key.esc:
                self._put(None)
                return False
            return

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
                    if self._active:
                        self._put(key_release_event(self._ctrl_key))
                    else:
                        # PAUSED→ACTIVE: defer until all keys/buttons released
                        self._activating = True
                    self._put(_TOGGLE)
                return
            if key == Key.esc:
                if self._active:
                    self._put(key_release_event(self._ctrl_key))
                self._put(None)  # sentinel: stop send loop
                return False     # stop keyboard listener

        if self._active:
            self._put(key_press_event(key))

    def on_release(self, key):
        self._all_held_keys.discard(key)

        if key == Key.tab:
            self._hotkey_down = False
        if key in (Key.ctrl_l, Key.ctrl_r):
            self._ctrl_pressed = False

        if self._activating:
            self._check_activate()
            return

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


async def _recv_loop(ws, bridge):
    try:
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "clipboard_push":
                pyperclip.copy(data["text"])
                print(f"clipboard received from server ({len(data['text'])} chars)")
            elif data["type"] == "screen_bounds":
                bridge._screen_bounds = (data["x_min"], data["y_min"],
                                         data["x_max"], data["y_max"])
                print(f"server screen: ({data['x_min']},{data['y_min']}) to ({data['x_max']},{data['y_max']})")
    except websockets.ConnectionClosed:
        pass
    # Server gone — tell the send loop to stop.
    print("server disconnected")
    bridge._put(None)


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
            recv_task = asyncio.create_task(_recv_loop(ws, bridge))
            mode = "suppress ON" if suppress else "suppress off"
            print(f"connected — ACTIVE ({mode}, Ctrl+Tab to toggle, Ctrl+Esc to stop)")
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break

                    if event is _TOGGLE:
                        if active:  # ACTIVE → PAUSED (immediate)
                            ml.stop()
                            ml.join()
                            kl.stop()
                            kl.join()
                            bridge._ctrl_pressed = False
                            bridge._hotkey_down = False
                            bridge._activating = False
                            bridge._all_held_keys.clear()
                            active = False
                            bridge._active = False
                            bridge._last_mouse_pos = None
                            bridge._virtual_pos = None
                            bridge._suppress = False
                            kl = _start_keyboard_listener(bridge, False)
                            ml = None
                            print("PAUSED (local input)")
                        else:  # PAUSED → ACTIVE deferred (bridge sets _activating=True)
                            # Start mouse listener so button releases are detected;
                            # on_move/on_scroll are blocked while _activating=True.
                            bridge._activating_mouse.clear()
                            bridge._last_mouse_pos = None
                            bridge._virtual_pos = None
                            bridge._suppress = suppress
                            ml = _start_mouse_listener(bridge, suppress)
                            print("ACTIVATING (release all keys and buttons)...")
                        continue

                    if event is _ACTIVATE:
                        # All held keys and buttons have been released — go ACTIVE.
                        kl.stop()
                        kl.join()
                        bridge._ctrl_pressed = False
                        bridge._hotkey_down = False
                        bridge._all_held_keys.clear()
                        active = True
                        bridge._active = True
                        bridge._last_mouse_pos = None
                        bridge._virtual_pos = None
                        kl = _start_keyboard_listener(bridge, suppress)
                        # ml is already running from the ACTIVATING phase
                        mode = "suppress ON" if suppress else "suppress off"
                        print(f"ACTIVE ({mode})")
                        continue

                    if event is _PUSH_CLIPBOARD:
                        text = pyperclip.paste()
                        await ws.send(json.dumps({"type": "clipboard_push", "text": text}))
                        print(f"clipboard pushed to server ({len(text)} chars)")
                        continue

                    try:
                        await ws.send(event)
                    except websockets.ConnectionClosed:
                        break
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
