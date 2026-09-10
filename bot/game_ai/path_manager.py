import time
import threading
from queue import Queue
from typing import List, Tuple

from pynput.keyboard import Controller

from bot.utilities import Point


MOVEMENT_KEYS = ("w", "a", "s", "d")


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
        keys = list(MOVEMENT_KEYS)
        if held and held not in keys:
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

                try:
                    self._held = next_movement
                    self.input.press(next_movement)
                    time.sleep(self.move_time)
                finally:
                    try:
                        self.input.release(next_movement)
                    except Exception:
                        pass
                    if self._held == next_movement:
                        self._held = None
        finally:
            self.pause_safe()

    def add_to_pathing_queue(self, movements: List[chr]):
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
            directions.append("d")
        elif point_b[0] - point_a[0] < 0:
            directions.append("a")
        elif point_b[1] - point_a[1] > 0:
            directions.append("s")
        elif point_b[1] - point_a[1] < 0:
            directions.append("w")
    return directions


if __name__ == "__main__":
    bot = PathManager()
    bot.follow_pathing_queue(threading.Event(), threading.Event())
