import atexit
import os
import shutil
import subprocess
import threading
import time
from queue import Queue
from typing import List, Optional, Tuple, Union

from pynput.keyboard import Controller, Key, KeyCode

from bot.utilities import Point


# Direction tokens from pathing; map to Vampire Survivors default WASD binds.
# Optional VS_MOVE_KEYS=arrows maps directions to arrow keys instead.
_MOVE_MODE = os.environ.get("VS_MOVE_KEYS", "wasd").strip().lower()
if _MOVE_MODE in ("arrows", "arrow", "arrow_keys"):
    MOVEMENT_KEYS = {
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right,
    }
    XDOTOOL_KEY_MAP = {
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
    }
else:
    MOVEMENT_KEYS = {
        "up": "w",
        "down": "s",
        "left": "a",
        "right": "d",
    }
    XDOTOOL_KEY_MAP = {
        "up": "w",
        "down": "s",
        "left": "a",
        "right": "d",
    }

# Input backend: pynput | xdotool. Default xdotool on this Steam/Linux box.
_INPUT_BACKEND = os.environ.get("VS_INPUT", "xdotool").strip().lower()
if _INPUT_BACKEND not in ("pynput", "xdotool"):
    _INPUT_BACKEND = "xdotool"

_ALL_RELEASE_KEYS: List[Union[str, Key]] = [
    "w", "a", "s", "d",
    Key.up, Key.down, Key.left, Key.right,
]


def _as_key(key: Union[str, Key, KeyCode]):
    if isinstance(key, str):
        return KeyCode.from_char(key)
    return key


class PathManager:
    def __init__(self, player_speed=320, pixels_moved=75):
        self.__path_queue = Queue()
        self.input = Controller()
        self.move_time = pixels_moved / player_speed
        self._held = None
        self._backend = _INPUT_BACKEND
        self._vs_wid: Optional[str] = None
        self._focused_once = False
        atexit.register(self.release_all_keys)
        print(
            f"PathManager backend={self._backend} move_mode={_MOVE_MODE} "
            f"keys={list(MOVEMENT_KEYS.values())}",
            flush=True,
        )

    def _xdotool(self, *args) -> None:
        if not shutil.which("xdotool"):
            return
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":6")
        try:
            subprocess.run(
                ["xdotool", *args],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                timeout=2,
            )
        except Exception:
            pass

    def _resolve_vs_window(self) -> Optional[str]:
        if self._vs_wid:
            return self._vs_wid
        if not shutil.which("xdotool"):
            return None
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":6")
        try:
            out = (
                subprocess.check_output(
                    ["xdotool", "search", "--name", "Vampire Survivors"],
                    env=env,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                .decode()
                .strip()
                .splitlines()
            )
            if out:
                self._vs_wid = out[0]
                return self._vs_wid
        except Exception:
            return None
        return None

    def ensure_vs_focus_once(self) -> None:
        """Focus VS once per live session. No Steam raise loops."""
        if self._focused_once:
            return
        wid = self._resolve_vs_window()
        if not wid:
            return
        self._xdotool("windowactivate", "--sync", wid)
        self._focused_once = True

    def _press_direction(self, direction: str) -> None:
        if self._backend == "xdotool":
            self.ensure_vs_focus_once()
            xt = XDOTOOL_KEY_MAP.get(direction)
            if not xt:
                return
            if self._vs_wid:
                self._xdotool("keydown", "--window", self._vs_wid, xt)
            else:
                self._xdotool("keydown", xt)
            return
        key = MOVEMENT_KEYS.get(direction)
        if key is None:
            return
        self.input.press(_as_key(key))

    def _release_direction(self, direction: str) -> None:
        if self._backend == "xdotool":
            xt = XDOTOOL_KEY_MAP.get(direction)
            if xt:
                if self._vs_wid:
                    self._xdotool("keyup", "--window", self._vs_wid, xt)
                else:
                    self._xdotool("keyup", xt)
            return
        key = MOVEMENT_KEYS.get(direction)
        if key is None:
            return
        try:
            self.input.release(_as_key(key))
        except Exception:
            pass

    def release_all_keys(self):
        """Release any held movement key. Safe when paused or exiting."""
        held = self._held
        self._held = None
        for direction in list(MOVEMENT_KEYS.keys()):
            try:
                self._release_direction(direction)
            except Exception:
                pass
        if held is not None and held not in MOVEMENT_KEYS:
            try:
                self._release_direction(held)
            except Exception:
                pass
        # Belt-and-suspenders: clear WASD and arrows via both backends
        if shutil.which("xdotool"):
            for xt in ("w", "a", "s", "d", "W", "A", "S", "D", "Up", "Down", "Left", "Right"):
                self._xdotool("keyup", xt)
        for key in _ALL_RELEASE_KEYS:
            try:
                self.input.release(_as_key(key))
            except Exception:
                pass

    def clear_queue(self):
        while not self.__path_queue.empty():
            try:
                self.__path_queue.get_nowait()
            except Exception:
                break

    def pause_safe(self):
        """Clear pending moves and release keys when pause turns ON."""
        self.clear_queue()
        self.release_all_keys()

    def follow_pathing_queue(self, stop_event: threading.Event, pause_event: threading.Event):
        try:
            while not stop_event.is_set():
                if pause_event.is_set() or self.__path_queue.qsize() == 0:
                    if pause_event.is_set():
                        self.pause_safe()
                    time.sleep(self.move_time)
                    continue

                next_movement = self.__path_queue.get()
                if pause_event.is_set() or stop_event.is_set():
                    self.pause_safe()
                    continue
                if next_movement not in MOVEMENT_KEYS:
                    continue

                try:
                    self._held = next_movement
                    self._press_direction(next_movement)
                    # Slice the hold so pause/stop can interrupt sooner
                    end = time.monotonic() + self.move_time
                    while time.monotonic() < end:
                        if pause_event.is_set() or stop_event.is_set():
                            break
                        time.sleep(min(0.02, end - time.monotonic()))
                finally:
                    try:
                        self._release_direction(next_movement)
                    except Exception:
                        pass
                    if self._held == next_movement:
                        self._held = None
                    if pause_event.is_set() or stop_event.is_set():
                        self.release_all_keys()
        finally:
            self.pause_safe()

    def add_to_pathing_queue(self, movements: List[str]):
        if self.__path_queue.qsize() != 0:
            return False
        for movement in movements:
            if movement in MOVEMENT_KEYS:
                self.__path_queue.put(movement)
        return True


def edge_list_to_direction_list(edges: List[Tuple[Point, Point]]):
    directions = []
    for edge in edges:
        point_a, point_b = edge[:2]

        if point_b[0] - point_a[0] > 0:
            directions.append("right")
        elif point_b[0] - point_a[0] < 0:
            directions.append("left")
        elif point_b[1] - point_a[1] > 0:
            directions.append("down")
        elif point_b[1] - point_a[1] < 0:
            directions.append("up")
    return directions


if __name__ == "__main__":
    bot = PathManager()
    bot.follow_pathing_queue(threading.Event(), threading.Event())
