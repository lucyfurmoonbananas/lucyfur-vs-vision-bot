import mss
import time
import numpy as np
from typing import Any, Dict, Tuple, Union


def _as_monitor(bounding_box: Union[Dict[str, int], Tuple[int, int, int, int]]) -> Dict[str, int]:
    if isinstance(bounding_box, dict):
        mon = {
            "left": int(bounding_box.get("left", 0)),
            "top": int(bounding_box.get("top", 0)),
            "width": int(bounding_box.get("width", 1)),
            "height": int(bounding_box.get("height", 1)),
        }
    else:
        # (left, top, right, bottom) style unused here; treat as left,top,width,height
        left, top, width, height = bounding_box
        mon = {"left": int(left), "top": int(top), "width": int(width), "height": int(height)}
    return mon


def _clamp(mon: Dict[str, int], screen: Dict[str, int]) -> Dict[str, int]:
    left = max(0, mon["left"])
    top = max(0, mon["top"])
    # screen from mss monitor 0 or 1
    sw = int(screen.get("width", 1280))
    sh = int(screen.get("height", 800))
    sl = int(screen.get("left", 0))
    st = int(screen.get("top", 0))
    max_w = max(1, sl + sw - left)
    max_h = max(1, st + sh - top)
    width = max(1, min(mon["width"], max_w))
    height = max(1, min(mon["height"], max_h))
    return {"left": left, "top": top, "width": width, "height": height}


def screenshot(bounding_box: Any) -> np.ndarray:
    last_err = None
    for attempt in range(5):
        try:
            with mss.MSS() as sct:
                screen = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                mon = _clamp(_as_monitor(bounding_box), screen)
                return np.array(sct.grab(mon))
        except Exception as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    raise last_err


def grab_every_n_seconds(n: int, bounding_box: Tuple[int, int, int, int]):
    import cv2
    from pathlib import Path
    Path("screenshots").mkdir(exist_ok=True)
    for i in range(0, 500):
        time.sleep(n)
        image = screenshot(bounding_box)
        # screenshot() returns a BGRA numpy array
        cv2.imwrite(f"screenshots/screenshot_{i}.png", image)


def main():
    """Takes a screenshot every 5 seconds and saves it."""
    offset = 70
    bounding_box = (offset, 0, offset + 1230, 800)
    grab_every_n_seconds(5, bounding_box)


if __name__ == "__main__":
    main()
