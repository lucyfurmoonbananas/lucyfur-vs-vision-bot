import os
import time
import threading
from queue import Queue
from typing import Dict, List, Tuple

from pynput.keyboard import Controller, Key, KeyCode

from bot.utilities import Point


# Default Vampire Survivors binds are WASD.
# Set VS_MOVE_KEYS=arrows only as an optional Steam/Linux fallback.
_MODE = os.environ.get("VS_MOVE_KEYS", "wasd").strip().lower()

_WASD: Dict[str, object] = {
    "up": KeyCode.from_char("w"),
    "down": KeyCode.from_char("s"),
    "left": KeyCode.from_char("a"),
    "right": KeyCode.from_char("d"),
}

_ARROWS: Dict[str, object] = {
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
}

MOVEMENT_KEYS = _ARROWS if _MODE in ("arrows", "arrow") else _WASD

# Always release both layouts on pause/stop so leftover binds cannot stick.
_ALL_RELEASE_KEYS = list(
    dict.fromkeys(list(_WASD.values()) + list(_ARROWS.values()))
)


class PathManager:
    def __init__(self, player_speed=320, pixels_moved=75):
        self.__path_queue = Queue()
        self.input = Controller()
        self.move_time = pixels_moved / player_speed
        self._held = None

    def release_all_keys(self):
        """Release any held movement key. Safe when paused or exiting."""
        held = self._held
        self._held = None
        keys = list(_ALL_RELEASE_KEYS)
        if held is not None and held not in keys:
            keys.append(held)
        for key in keys:
            try:
                self.input.release(key)
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

                key = MOVEMENT_KEYS.get(next_movement)
                if key is None:
                    continue
                try:
                    self._held = key
                    self.input.press(key)
                    time.sleep(self.move_time)
                finally:
                    try:
                        self.input.release(key)
                    except Exception:
                        pass
                    if self._held == key:
                        self._held = None
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