"""Shared event serialization/deserialization for mows protocol.

JSON messages with a "type" field:
  mouse_move, mouse_click, mouse_scroll, key_press, key_release
"""

import json
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button


# ── Key serialization ──────────────────────────────────────────────

def serialize_key(key) -> dict:
    """Convert a pynput key to a JSON-safe dict."""
    if isinstance(key, Key):
        return {"kind": "special", "name": key.name}
    elif isinstance(key, KeyCode):
        if key.char is not None:
            return {"kind": "char", "char": key.char}
        else:
            return {"kind": "vk", "vk": key.vk}
    else:
        return {"kind": "char", "char": str(key)}


def deserialize_key(data: dict):
    """Reconstruct a pynput key from a dict."""
    kind = data["kind"]
    if kind == "special":
        return Key[data["name"]]
    elif kind == "char":
        return KeyCode.from_char(data["char"])
    elif kind == "vk":
        return KeyCode.from_vk(data["vk"])


# ── Button serialization ──────────────────────────────────────────

def serialize_button(button) -> str:
    return button.name


def deserialize_button(name: str):
    return Button[name]


# ── Event constructors ────────────────────────────────────────────

def mouse_move_event(dx: int, dy: int) -> str:
    return json.dumps({"type": "mouse_move", "dx": dx, "dy": dy})


def mouse_click_event(button, pressed: bool) -> str:
    return json.dumps({
        "type": "mouse_click",
        "button": serialize_button(button),
        "pressed": pressed,
    })


def mouse_scroll_event(dx: int, dy: int) -> str:
    return json.dumps({
        "type": "mouse_scroll",
        "dx": dx, "dy": dy,
    })


def key_press_event(key) -> str:
    return json.dumps({
        "type": "key_press",
        "key": serialize_key(key),
    })


def key_release_event(key) -> str:
    return json.dumps({
        "type": "key_release",
        "key": serialize_key(key),
    })
