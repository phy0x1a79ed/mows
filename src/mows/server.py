"""mows server — receives events over WebSocket and replays them locally."""

import asyncio
import json
import sys

import pyperclip
import websockets
from pynput.keyboard import Controller as KeyboardController, Key, KeyCode
from pynput.mouse import Controller as MouseController

from .protocol import deserialize_button, deserialize_key


def _get_screen_bounds():
    """Return (width, height) of the primary screen, or None on failure."""
    try:
        if sys.platform == 'win32':
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        else:
            from Xlib.display import Display
            d = Display()
            s = d.screen()
            return (s.width_in_pixels, s.height_in_pixels)
    except Exception:
        return None


async def _push_clipboard_after_delay(websocket, delay=0.15):
    await asyncio.sleep(delay)
    text = pyperclip.paste()
    try:
        await websocket.send(json.dumps({"type": "clipboard_push", "text": text}))
        print(f"clipboard pushed to client ({len(text)} chars)")
    except websockets.ConnectionClosed:
        pass


def _make_handler(mouse: MouseController, keyboard: KeyboardController,
                  screen_bounds):
    async def handler(websocket):
        print(f"client connected: {websocket.remote_address}")
        if screen_bounds:
            await websocket.send(json.dumps({
                "type": "screen_bounds",
                "width": screen_bounds[0],
                "height": screen_bounds[1],
            }))
        pressed_keys = set()
        pressed_buttons = set()
        try:
            async for message in websocket:
                event = json.loads(message)
                await _dispatch(event, websocket, mouse, keyboard,
                                 pressed_keys, pressed_buttons)
        except websockets.ConnectionClosed:
            pass
        finally:
            for btn in pressed_buttons:
                mouse.release(btn)
            for key in pressed_keys:
                keyboard.release(key)
            print(f"client disconnected: {websocket.remote_address}")
    return handler


async def _dispatch(event: dict, websocket, mouse: MouseController,
                    keyboard: KeyboardController,
                    pressed_keys: set, pressed_buttons: set):
    t = event["type"]
    if t == "mouse_move":
        mouse.position = (event["x"], event["y"])
    elif t == "mouse_click":
        btn = deserialize_button(event["button"])
        if event["pressed"]:
            pressed_buttons.add(btn)
            mouse.press(btn)
        else:
            pressed_buttons.discard(btn)
            mouse.release(btn)
    elif t == "mouse_scroll":
        mouse.scroll(event["dx"], event["dy"])
    elif t == "key_press":
        key = deserialize_key(event["key"])
        pressed_keys.add(key)
        keyboard.press(key)
        if (isinstance(key, KeyCode) and key.char in ('c', '\x03')
                and any(k in pressed_keys for k in (Key.ctrl_l, Key.ctrl_r))):
            asyncio.create_task(_push_clipboard_after_delay(websocket))
    elif t == "key_release":
        key = deserialize_key(event["key"])
        pressed_keys.discard(key)
        keyboard.release(key)
    elif t == "clipboard_push":
        pyperclip.copy(event["text"])
        print(f"clipboard updated from client ({len(event['text'])} chars)")
    elif t == "clipboard_pull":
        text = pyperclip.paste()
        await websocket.send(json.dumps({"type": "clipboard_data", "text": text}))
        print(f"clipboard sent to client ({len(text)} chars)")


async def _serve(host: str, port: int):
    mouse = MouseController()
    keyboard = KeyboardController()
    screen_bounds = _get_screen_bounds()
    if screen_bounds:
        print(f"screen bounds: {screen_bounds[0]}x{screen_bounds[1]}")
    handler = _make_handler(mouse, keyboard, screen_bounds)
    async with websockets.serve(handler, host, port):
        print(f"mows server listening on {host}:{port}")
        await asyncio.Future()  # run forever


def run_server(host: str = "0.0.0.0", port: int = 8765):
    try:
        asyncio.run(_serve(host, port))
    except KeyboardInterrupt:
        print('goodbye')
