"""mows server — receives events over WebSocket and replays them locally."""

import asyncio
import json

import pyperclip
import websockets
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController

from .protocol import deserialize_button, deserialize_key


def _make_handler(mouse: MouseController, keyboard: KeyboardController):
    async def handler(websocket):
        print(f"client connected: {websocket.remote_address}")
        try:
            async for message in websocket:
                event = json.loads(message)
                await _dispatch(event, websocket, mouse, keyboard)
        except websockets.ConnectionClosed:
            pass
        finally:
            print(f"client disconnected: {websocket.remote_address}")
    return handler


async def _dispatch(event: dict, websocket, mouse: MouseController,
                    keyboard: KeyboardController):
    t = event["type"]
    if t == "mouse_move":
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
