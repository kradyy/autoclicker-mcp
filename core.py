"""Core auto-clicker logic, independent of any GUI framework."""

import os
import platform
import threading
import time

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    import ctypes
    import ctypes.wintypes

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


class AutoClickerCore:
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MAX_CPS = 200.0

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self._running = False
        self._status = "Idle"
        self._lock = threading.Lock()
        self.tesseract_cmd: str = ""

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def get_status(self) -> dict[str, object]:
        with self._lock:
            return {"running": self._running, "status": self._status}

    def _set_status(self, msg: str, running: bool | None = None) -> None:
        with self._lock:
            self._status = msg
            if running is not None:
                self._running = running

    # ------------------------------------------------------------------
    # Low-level input
    # ------------------------------------------------------------------

    def get_cursor_position(self) -> tuple[int, int]:
        if _IS_WINDOWS:
            point = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return point.x, point.y
        if pyautogui is None:
            raise RuntimeError("pyautogui required on non-Windows — pip install pyautogui pillow")
        pos = pyautogui.position()
        return pos.x, pos.y

    def set_cursor_position(self, x: int, y: int) -> None:
        if _IS_WINDOWS:
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
        else:
            if pyautogui is None:
                raise RuntimeError("pyautogui required on non-Windows — pip install pyautogui pillow")
            pyautogui.moveTo(int(x), int(y))

    def left_click(self) -> None:
        if _IS_WINDOWS:
            ctypes.windll.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        else:
            if pyautogui is None:
                raise RuntimeError("pyautogui required on non-Windows — pip install pyautogui pillow")
            pyautogui.click()

    def click_at(self, x: int, y: int) -> None:
        if _IS_WINDOWS:
            self.set_cursor_position(x, y)
            self.left_click()
        else:
            if pyautogui is None:
                raise RuntimeError("pyautogui required on non-Windows — pip install pyautogui pillow")
            pyautogui.click(int(x), int(y))

    # ------------------------------------------------------------------
    # Screen targeting helpers
    # ------------------------------------------------------------------

    def find_image_on_screen(
        self,
        template_path: str,
        confidence: float = 0.85,
    ) -> tuple[int, int] | None:
        """Locate a template image on screen and return its center, or None."""
        if pyautogui is None:
            raise RuntimeError(
                "pyautogui not installed — run: py -m pip install pyautogui pillow"
            )
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")
        if not (0.1 <= confidence <= 1.0):
            raise ValueError("confidence must be 0.1–1.0")

        location = (
            pyautogui.locateCenterOnScreen(template_path, confidence=confidence)
            if confidence < 1.0
            else pyautogui.locateCenterOnScreen(template_path)
        )
        return (int(location.x), int(location.y)) if location else None

    def _configure_tesseract(self) -> None:
        if pytesseract is None:
            raise RuntimeError(
                "pytesseract not installed — run: py -m pip install pytesseract"
            )
        if self.tesseract_cmd:
            if not os.path.exists(self.tesseract_cmd):
                raise RuntimeError(
                    f"Tesseract path not found: {self.tesseract_cmd}"
                )
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            return
        for candidate in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                return

    def find_text_on_screen(
        self,
        query: str,
        min_confidence: int = 45,
    ) -> tuple[int, int] | None:
        """Find text on screen via OCR and return its center, or None."""
        self._configure_tesseract()
        if pyautogui is None:
            raise RuntimeError(
                "pyautogui not installed — run: py -m pip install pyautogui pillow"
            )

        query = query.strip().lower()
        if not query:
            raise ValueError("query must not be empty")
        if not (0 <= min_confidence <= 100):
            raise ValueError("min_confidence must be 0–100")

        image = pyautogui.screenshot()
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        tokens: list[dict[str, object]] = []
        for i in range(len(data["text"])):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = int(float(str(data["conf"][i]).strip()))
            except ValueError:
                continue
            if conf < min_confidence:
                continue
            tokens.append(
                {
                    "text": text,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "block": int(data["block_num"][i]),
                    "line": int(data["line_num"][i]),
                }
            )

        if not tokens:
            return None

        by_line: dict[tuple[int, int], list[dict[str, object]]] = {}
        for token in tokens:
            key = (int(token["block"]), int(token["line"]))
            by_line.setdefault(key, []).append(token)

        query_words = query.split()
        for line_tokens in by_line.values():
            words = [str(t["text"]).lower() for t in line_tokens]
            for start in range(len(words)):
                end = start + len(query_words)
                if end > len(words):
                    break
                if words[start:end] == query_words:
                    matched = line_tokens[start:end]
                    left = min(int(t["left"]) for t in matched)
                    top = min(int(t["top"]) for t in matched)
                    right = max(int(t["left"]) + int(t["width"]) for t in matched)
                    bottom = max(
                        int(t["top"]) + int(t["height"]) for t in matched
                    )
                    return (left + right) // 2, (top + bottom) // 2

        for token in tokens:
            if query in str(token["text"]).lower():
                return (
                    int(token["left"]) + int(token["width"]) // 2,
                    int(token["top"]) + int(token["height"]) // 2,
                )

        return None

    # ------------------------------------------------------------------
    # Click-loop internals
    # ------------------------------------------------------------------

    def _resolve_target(
        self,
        target_mode: str,
        x: int,
        y: int,
        template_path: str,
        confidence: float,
        text_query: str,
        text_confidence: int,
    ) -> tuple[int, int] | None:
        if target_mode == "cursor":
            return self.get_cursor_position()
        if target_mode == "fixed":
            return x, y
        if target_mode == "image":
            return self.find_image_on_screen(template_path, confidence)
        if target_mode == "text":
            return self.find_text_on_screen(text_query, text_confidence)
        raise ValueError(f"Unknown target_mode: {target_mode!r}")

    def _run_loop(
        self,
        duration: float | None,
        interval: float,
        cps: float,
        target_mode: str,
        x: int,
        y: int,
        template_path: str,
        confidence: float,
        text_query: str,
        text_confidence: int,
    ) -> None:
        start_time = time.time()
        next_click = start_time
        label = f"{duration:g}s" if duration is not None else "continuously"
        self._set_status(f"Running {label} at {cps:g} CPS", running=True)

        while not self.stop_event.is_set():
            now = time.time()
            if duration is not None and (now - start_time) >= duration:
                break
            if now < next_click:
                time.sleep(min(next_click - now, 0.01))
                continue

            try:
                target = self._resolve_target(
                    target_mode,
                    x,
                    y,
                    template_path,
                    confidence,
                    text_query,
                    text_confidence,
                )
                if target:
                    self.click_at(*target)
            except Exception as exc:
                self._set_status(f"Error: {exc}", running=False)
                return

            next_click += interval

        self._set_status("Stopped", running=False)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(
        self,
        *,
        cps: float = 10.0,
        duration: float | None = None,
        target_mode: str = "cursor",
        x: int = 0,
        y: int = 0,
        template_path: str = "",
        confidence: float = 0.85,
        text_query: str = "",
        text_confidence: int = 45,
        start_delay: float = 0.0,
    ) -> None:
        """Start clicking in a background thread.

        Raises RuntimeError if already running, ValueError for bad params.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Clicker is already running.")

        if not (0 < cps <= self.MAX_CPS):
            raise ValueError(f"CPS must be > 0 and <= {self.MAX_CPS}.")
        if start_delay < 0:
            raise ValueError("start_delay must be >= 0.")
        if duration is not None and duration <= 0:
            raise ValueError("duration must be > 0 when specified.")

        interval = 1.0 / cps
        self.stop_event.clear()
        self._set_status(
            f"Starting in {start_delay:g}s…" if start_delay > 0 else "Starting…",
            running=True,
        )

        def _run() -> None:
            if start_delay > 0:
                time.sleep(start_delay)
                if self.stop_event.is_set():
                    self._set_status("Canceled", running=False)
                    return
            self._run_loop(
                duration,
                interval,
                cps,
                target_mode,
                x,
                y,
                template_path,
                confidence,
                text_query,
                text_confidence,
            )

        self.worker_thread = threading.Thread(target=_run, daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        """Stop clicking and wait for the worker thread to finish."""
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        self._set_status("Stopped", running=False)
