"""mows server — receives events over WebSocket and replays them locally."""

import asyncio
import json
import sys

import pyperclip
import websockets
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController

from .protocol import deserialize_button, deserialize_key


def _make_rel_mover():
    """Bypass pynput's mouse.move() to avoid its position read-back,
    which causes drift from DPI rounding (Win) or async lag (X11).

    On Linux:  XWarpPointer with src=dst=0 does a true relative move
               without querying the current position first.
    On Windows: mouse_event(MOUSEEVENTF_MOVE) sends relative pixel
               deltas directly; DPI awareness is set so coordinates
               are consistent.
    """
    if sys.platform == 'linux':
        try:
            import ctypes
            import ctypes.util
            path = ctypes.util.find_library('X11')
            if not path:
                return None
            x11 = ctypes.cdll.LoadLibrary(path)
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XFlush.argtypes = [ctypes.c_void_p]
            x11.XFlush.restype = ctypes.c_int
            x11.XWarpPointer.argtypes = [
                ctypes.c_void_p,               # Display *
                ctypes.c_ulong, ctypes.c_ulong, # src_window, dst_window
                ctypes.c_int, ctypes.c_int,     # src_x, src_y
                ctypes.c_uint, ctypes.c_uint,   # src_width, src_height
                ctypes.c_int, ctypes.c_int,     # dst_x, dst_y
            ]
            x11.XWarpPointer.restype = ctypes.c_int
            dpy = x11.XOpenDisplay(None)
            if not dpy:
                return None

            def move(dx, dy):
                x11.XWarpPointer(dpy, 0, 0, 0, 0, 0, 0, int(dx), int(dy))
                x11.XFlush(dpy)

            return move
        except Exception:
            return None

    if sys.platform == 'win32':
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass

            def move(dx, dy):
                ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)

            return move
        except Exception:
            return None

    return None


def _make_handler(mouse: MouseController, keyboard: KeyboardController):
    rel_move = _make_rel_mover()

    async def handler(websocket):
        print(f"client connected: {websocket.remote_address}")
        try:
            async for message in websocket:
                event = json.loads(message)
                await _dispatch(event, websocket, mouse, keyboard, rel_move)
        except websockets.ConnectionClosed:
            pass
        finally:
            print(f"client disconnected: {websocket.remote_address}")
    return handler


async def _dispatch(event: dict, websocket, mouse: MouseController,
                    keyboard: KeyboardController, rel_move):
    t = event["type"]
    if t == "mouse_move":
        if rel_move:
            rel_move(event["dx"], event["dy"])
        else:
            mouse.move(event["dx"], event["dy"])
    elif t == "mouse_click":
        btn = deserialize_button(event["button"])
        if event["pressed"]:
            mouse.press(btn)
        else:
            mouse.release(btn)
    elif t == "mouse_scroll":
        mouse.scroll(event["dx"], event["dy"])
    elif t == "key_press":
        key = deserialize_key(event["key"])
        keyboard.press(key)
    elif t == "key_release":
        key = deserialize_key(event["key"])
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
    handler = _make_handler(mouse, keyboard)
    async with websockets.serve(handler, host, port):
        print(f"mows server listening on {host}:{port}")
        await asyncio.Future()  # run forever


def run_server(host: str = "0.0.0.0", port: int = 8765):
    try:
        asyncio.run(_serve(host, port))
    except KeyboardInterrupt:
        print('goodbye')
