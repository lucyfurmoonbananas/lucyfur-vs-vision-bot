import os
import shutil
import subprocess
import time
import threading
from queue import Queue
from typing import Dict, List, Optional, Tuple

from pynput.keyboard import Controller, KeyCode

from bot.utilities import Point


# Default VS movement binds are WASD. Map logical directions to those keys.
# Do not force arrow keys; that was only a temporary Steam/Linux workaround.
MOVEMENT_CHARS: Dict[str, str] = {
    "up": "w",
    "down": "s",
    "left": "a",
    "right": "d",
}

# Optional: target the game window so OpenCV "Model Vision" focus does not eat keys.
# VS_MOVE_BACKEND=pynput (default) | xdotool
# VS_GAME_WINDOW_NAME substring match, default "Vampire Survivors"
MOVE_BACKEND = os.environ.get("VS_MOVE_BACKEND", "pynput").strip().lower()
GAME_WINDOW_NAME = os.environ.get("VS_GAME_WINDOW_NAME", "Vampire Survivors")


class PathManager:
    def __init__(self, player_speed=320, pixels_moved=75):
        self.__path_queue = Queue()
        self.input = Controller()
        self.move_time = pixels_moved / player_speed
        self._held: Optional[str] = None
        self._xdotool = shutil.which("xdotool")
        self._warned_xdotool = False

    def _focus_game_window(self) -> bool:
        """Best-effort focus of the Vampire Survivors window before key inject."""
        if not self._xdotool:
            return False
        try:
            out = subprocess.check_output(
                ["xdotool", "search", "--name", GAME_WINDOW_NAME],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            )
            wid = out.strip().splitlines()[-1].strip()
            if not wid:
                return False
            subprocess.check_call(
                ["xdotool", "windowactivate", "--sync", wid],
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            return True
        except Exception:
            return False

    def _press_char(self, ch: str) -> None:
        if MOVE_BACKEND == "xdotool" and self._xdotool:
            self._focus_game_window()
            subprocess.check_call(
                ["xdotool", "keydown", ch],
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            return
        if MOVE_BACKEND == "xdotool" and not self._xdotool and not self._warned_xdotool:
            print("xdotool missing; falling back to pynput for WASD", flush=True)
            self._warned_xdotool = True
        # pynput path: try to focus game first so Model Vision does not eat WASD
        self._focus_game_window()
        self.input.press(KeyCode.from_char(ch))

    def _release_char(self, ch: str) -> None:
        if MOVE_BACKEND == "xdotool" and self._xdotool:
            try:
                subprocess.check_call(
                    ["xdotool", "keyup", ch],
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
            except Exception:
                pass
            return
        try:
            self.input.release(KeyCode.from_char(ch))
        except Exception:
            pass
        # Also release bare string form some pynput builds accept
        try:
            self.input.release(ch)
        except Exception:
            pass

    def release_all_keys(self):
        """Release any held movement key. Safe when paused or exiting."""
        held = self._held
        self._held = None
        chars = list(MOVEMENT_CHARS.values())
        if held is not None and held not in chars:
            chars.append(held)
        for ch in chars:
            self._release_char(ch)

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

                ch = MOVEMENT_CHARS.get(next_movement)
                if ch is None:
                    continue
                try:
                    self._held = ch
                    self._press_char(ch)
                    time.sleep(self.move_time)
                finally:
                    self._release_char(ch)
                    if self._held == ch:
                        self._held = None
        finally:
            self.pause_safe()

    def add_to_pathing_queue(self, movements: List[str]):
        if self.__path_queue.qsize() != 0:
            return False
        for movement in movements:
            if movement in MOVEMENT_CHARS:
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
