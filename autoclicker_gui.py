import ctypes
import ctypes.wintypes
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pytesseract
except Exception:
    pytesseract = None


class AutoClickerApp:
    """Simple Windows auto-clicker with timed and continuous modes."""

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MAX_CPS = 200.0
    WM_HOTKEY = 0x0312
    PM_REMOVE = 0x0001
    HOTKEY_ID_START = 1
    HOTKEY_ID_STOP = 2
    HOTKEY_ID_EMERGENCY = 3
    VK_F6 = 0x75
    VK_F7 = 0x76
    VK_ESCAPE = 0x1B

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Simple Auto Clicker")
        self.root.geometry("620x640")
        self.root.minsize(620, 640)

        self.running = False
        self.pending_start = False
        self.pending_after_id: str | None = None
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.hotkeys_registered = False

        self.float_window: tk.Toplevel | None = None
        self.float_start_button: ttk.Button | None = None
        self.float_stop_button: ttk.Button | None = None

        self.mode_var = tk.StringVar(value="timed")
        self.duration_var = tk.StringVar(value="10")
        self.cps_var = tk.StringVar(value="10")
        self.start_delay_var = tk.StringVar(value="3")
        self.target_mode_var = tk.StringVar(value="cursor")
        self.target_x_var = tk.StringVar(value="0")
        self.target_y_var = tk.StringVar(value="0")
        self.template_path_var = tk.StringVar(value="")
        self.template_confidence_var = tk.StringVar(value="0.85")
        self.text_query_var = tk.StringVar(value="")
        self.text_confidence_var = tk.StringVar(value="45")
        self.tesseract_cmd_var = tk.StringVar(value="")
        self.pin_window_var = tk.BooleanVar(value=True)
        self.floating_controls_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Idle")

        self._build_ui()
        self._register_hotkeys()
        self._poll_hotkeys()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=0)

        settings = ttk.LabelFrame(container, text="Click Settings", padding=12)
        settings.grid(row=0, column=0, sticky="nsew")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Mode:").grid(row=0, column=0, sticky="w", pady=(0, 8))
        mode_wrap = ttk.Frame(settings)
        mode_wrap.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Radiobutton(
            mode_wrap,
            text="Timed",
            value="timed",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(side="left", padx=(0, 12))

        ttk.Radiobutton(
            mode_wrap,
            text="Continuous",
            value="continuous",
            variable=self.mode_var,
            command=self._on_mode_change,
        ).pack(side="left")

        ttk.Label(settings, text="Duration (seconds):").grid(row=1, column=0, sticky="w", pady=8)
        self.duration_entry = ttk.Entry(settings, textvariable=self.duration_var, width=12)
        self.duration_entry.grid(row=1, column=1, sticky="w", pady=8)

        ttk.Label(settings, text="Clicks per second:").grid(row=2, column=0, sticky="w", pady=8)
        self.cps_entry = ttk.Entry(settings, textvariable=self.cps_var, width=12)
        self.cps_entry.grid(row=2, column=1, sticky="w", pady=8)

        ttk.Label(settings, text="Start delay (seconds):").grid(row=3, column=0, sticky="w", pady=8)
        self.start_delay_entry = ttk.Entry(settings, textvariable=self.start_delay_var, width=12)
        self.start_delay_entry.grid(row=3, column=1, sticky="w", pady=8)

        ttk.Label(settings, text="Click target:").grid(row=4, column=0, sticky="nw", pady=(8, 0))

        target_wrap = ttk.Frame(settings)
        target_wrap.grid(row=4, column=1, sticky="w", pady=(8, 0))

        ttk.Radiobutton(
            target_wrap,
            text="Current cursor",
            value="cursor",
            variable=self.target_mode_var,
            command=self._on_target_mode_change,
        ).grid(row=0, column=0, sticky="w")

        ttk.Radiobutton(
            target_wrap,
            text="Fixed position",
            value="fixed",
            variable=self.target_mode_var,
            command=self._on_target_mode_change,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        fixed_wrap = ttk.Frame(target_wrap)
        fixed_wrap.grid(row=2, column=0, sticky="w", pady=(4, 0))

        ttk.Label(fixed_wrap, text="X:").pack(side="left")
        self.target_x_entry = ttk.Entry(fixed_wrap, textvariable=self.target_x_var, width=7)
        self.target_x_entry.pack(side="left", padx=(4, 8))
        ttk.Label(fixed_wrap, text="Y:").pack(side="left")
        self.target_y_entry = ttk.Entry(fixed_wrap, textvariable=self.target_y_var, width=7)
        self.target_y_entry.pack(side="left", padx=(4, 8))
        self.capture_button = ttk.Button(fixed_wrap, text="Use current mouse", command=self.capture_mouse_pos)
        self.capture_button.pack(side="left")

        ttk.Radiobutton(
            target_wrap,
            text="Find image on screen",
            value="image",
            variable=self.target_mode_var,
            command=self._on_target_mode_change,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        image_wrap = ttk.Frame(target_wrap)
        image_wrap.grid(row=4, column=0, sticky="w", pady=(4, 0))

        self.template_path_entry = ttk.Entry(image_wrap, textvariable=self.template_path_var, width=28)
        self.template_path_entry.pack(side="left", padx=(0, 8))
        self.template_browse_button = ttk.Button(image_wrap, text="Browse", command=self.pick_template)
        self.template_browse_button.pack(side="left")
        self.template_test_button = ttk.Button(image_wrap, text="Test match", command=self.test_match)
        self.template_test_button.pack(side="left", padx=(8, 0))

        confidence_wrap = ttk.Frame(target_wrap)
        confidence_wrap.grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Label(confidence_wrap, text="Match confidence (0.1-1.0):").pack(side="left")
        self.template_confidence_entry = ttk.Entry(
            confidence_wrap,
            textvariable=self.template_confidence_var,
            width=7,
        )
        self.template_confidence_entry.pack(side="left", padx=(6, 0))

        ttk.Radiobutton(
            target_wrap,
            text="Find text on screen (OCR)",
            value="text",
            variable=self.target_mode_var,
            command=self._on_target_mode_change,
        ).grid(row=6, column=0, sticky="w", pady=(8, 0))

        text_wrap = ttk.Frame(target_wrap)
        text_wrap.grid(row=7, column=0, sticky="w", pady=(4, 0))
        ttk.Label(text_wrap, text="Text:").pack(side="left")
        self.text_query_entry = ttk.Entry(text_wrap, textvariable=self.text_query_var, width=22)
        self.text_query_entry.pack(side="left", padx=(6, 8))
        self.text_test_button = ttk.Button(text_wrap, text="Test text", command=self.test_match)
        self.text_test_button.pack(side="left")

        text_conf_wrap = ttk.Frame(target_wrap)
        text_conf_wrap.grid(row=8, column=0, sticky="w", pady=(4, 0))
        ttk.Label(text_conf_wrap, text="OCR confidence (0-100):").pack(side="left")
        self.text_confidence_entry = ttk.Entry(
            text_conf_wrap,
            textvariable=self.text_confidence_var,
            width=7,
        )
        self.text_confidence_entry.pack(side="left", padx=(6, 0))

        tess_wrap = ttk.Frame(target_wrap)
        tess_wrap.grid(row=9, column=0, sticky="w", pady=(4, 0))
        ttk.Label(tess_wrap, text="Tesseract path (optional):").pack(side="left")
        self.tesseract_cmd_entry = ttk.Entry(tess_wrap, textvariable=self.tesseract_cmd_var, width=28)
        self.tesseract_cmd_entry.pack(side="left", padx=(6, 0))

        self.pin_window_toggle = ttk.Checkbutton(
            settings,
            text="Keep app on top",
            variable=self.pin_window_var,
            command=self._on_pin_window_change,
        )
        self.pin_window_toggle.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.floating_toggle = ttk.Checkbutton(
            settings,
            text="Show floating controls",
            variable=self.floating_controls_var,
            command=self._on_floating_controls_change,
        )
        self.floating_toggle.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(settings, text="Status:").grid(row=7, column=0, sticky="w", pady=(12, 0))
        ttk.Label(settings, textvariable=self.status_var).grid(row=7, column=1, sticky="w", pady=(12, 0))

        ttk.Label(
            settings,
            text="Global hotkeys: F6 start | F7 stop | Esc emergency stop",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Bottom-right action area for easy use.
        nav = ttk.Frame(container)
        nav.grid(row=1, column=0, sticky="se", pady=(10, 0))

        self.start_button = ttk.Button(nav, text="Start", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(nav, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._on_pin_window_change()
        self._on_mode_change()
        self._on_target_mode_change()
        self._create_floating_controls()
        self._on_floating_controls_change()
        self._update_controls_state()

    def _create_floating_controls(self) -> None:
        self.float_window = tk.Toplevel(self.root)
        self.float_window.title("Click Controls")
        self.float_window.resizable(False, False)
        self.float_window.attributes("-topmost", True)
        self.float_window.protocol("WM_DELETE_WINDOW", self._hide_floating_controls)

        frame = ttk.Frame(self.float_window, padding=10)
        frame.pack(fill="both", expand=True)

        button_row = ttk.Frame(frame)
        button_row.pack(fill="x")

        self.float_start_button = ttk.Button(button_row, text="Start", command=self.start)
        self.float_start_button.pack(side="left", padx=(0, 8))

        self.float_stop_button = ttk.Button(button_row, text="Stop", command=self.stop)
        self.float_stop_button.pack(side="left")

        ttk.Label(
            frame,
            text="F6 Start  |  F7 Stop  |  Esc Stop",
        ).pack(anchor="w", pady=(8, 0))

        self.float_window.update_idletasks()
        self._position_floating_controls()

    def _position_floating_controls(self) -> None:
        if self.float_window is None:
            return

        self.float_window.update_idletasks()
        width = self.float_window.winfo_width()
        height = self.float_window.winfo_height()
        screen_w = self.float_window.winfo_screenwidth()
        screen_h = self.float_window.winfo_screenheight()
        x = max(0, screen_w - width - 20)
        y = max(0, screen_h - height - 80)
        self.float_window.geometry(f"+{x}+{y}")

    def _hide_floating_controls(self) -> None:
        self.floating_controls_var.set(False)
        self._on_floating_controls_change()

    def _on_floating_controls_change(self) -> None:
        if self.float_window is None:
            return

        if self.floating_controls_var.get():
            self._position_floating_controls()
            self.float_window.deiconify()
            self.float_window.lift()
        else:
            self.float_window.withdraw()

    def _on_mode_change(self) -> None:
        is_timed = self.mode_var.get() == "timed"
        self.duration_entry.configure(state="normal" if is_timed else "disabled")

    def _on_target_mode_change(self) -> None:
        mode = self.target_mode_var.get()

        fixed_state = "normal" if mode == "fixed" else "disabled"
        image_state = "normal" if mode == "image" else "disabled"
        text_state = "normal" if mode == "text" else "disabled"

        self.target_x_entry.configure(state=fixed_state)
        self.target_y_entry.configure(state=fixed_state)
        self.capture_button.configure(state=fixed_state)

        self.template_path_entry.configure(state=image_state)
        self.template_browse_button.configure(state=image_state)
        self.template_test_button.configure(state=image_state)
        self.template_confidence_entry.configure(state=image_state)

        self.text_query_entry.configure(state=text_state)
        self.text_test_button.configure(state=text_state)
        self.text_confidence_entry.configure(state=text_state)
        self.tesseract_cmd_entry.configure(state=text_state)

    def _get_cursor_position(self) -> tuple[int, int]:
        point = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def _set_cursor_position(self, x: int, y: int) -> None:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))

    def capture_mouse_pos(self) -> None:
        x, y = self._get_cursor_position()
        self.target_x_var.set(str(x))
        self.target_y_var.set(str(y))
        self.status_var.set(f"Captured position X={x}, Y={y}")

    def pick_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Select button image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")],
        )
        if path:
            self.template_path_var.set(path)

    def _resolve_click_target(self) -> tuple[int, int] | None:
        mode = self.target_mode_var.get()

        if mode == "cursor":
            return self._get_cursor_position()

        if mode == "fixed":
            x = int(float(self.target_x_var.get()))
            y = int(float(self.target_y_var.get()))
            return x, y

        if pyautogui is None:
            raise RuntimeError("Image target needs pyautogui installed in Windows Python.")

        template = self.template_path_var.get().strip()
        if not template:
            raise ValueError("Pick an image template first.")

        confidence = float(self.template_confidence_var.get())
        if confidence < 0.1 or confidence > 1.0:
            raise ValueError("Confidence must be between 0.1 and 1.0.")

        if confidence < 1.0:
            location = pyautogui.locateCenterOnScreen(template, confidence=confidence)
        else:
            location = pyautogui.locateCenterOnScreen(template)

        if location is None:
            return None

        return int(location.x), int(location.y)

    def _configure_tesseract_cmd(self) -> None:
        if pytesseract is None:
            raise RuntimeError("Text mode needs pytesseract installed.")

        custom_cmd = self.tesseract_cmd_var.get().strip()
        if custom_cmd:
            if not os.path.exists(custom_cmd):
                raise RuntimeError("Configured Tesseract path does not exist.")
            pytesseract.pytesseract.tesseract_cmd = custom_cmd
            return

        # Auto-detect common Windows install locations when path is left empty.
        candidates = [
            r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
            r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                return

    def _find_text_target(self) -> tuple[int, int] | None:
        self._configure_tesseract_cmd()

        if pyautogui is None:
            raise RuntimeError("Text mode also needs pyautogui installed.")

        query = self.text_query_var.get().strip().lower()
        if not query:
            raise ValueError("Enter text to search for.")

        min_conf = int(float(self.text_confidence_var.get()))
        if min_conf < 0 or min_conf > 100:
            raise ValueError("OCR confidence must be between 0 and 100.")

        image = pyautogui.screenshot()
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        tokens: list[dict[str, int | str]] = []
        count = len(data["text"])
        for i in range(count):
            text = (data["text"][i] or "").strip()
            if not text:
                continue

            conf_raw = str(data["conf"][i]).strip()
            try:
                conf = int(float(conf_raw))
            except ValueError:
                continue

            if conf < min_conf:
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

        # Try phrase matching per OCR line first.
        by_line: dict[tuple[int, int], list[dict[str, int | str]]] = {}
        for token in tokens:
            key = (int(token["block"]), int(token["line"]))
            by_line.setdefault(key, []).append(token)

        query_words = query.split()
        for _key, line_tokens in by_line.items():
            words = [str(t["text"]).lower() for t in line_tokens]

            for start in range(0, len(words)):
                end = start + len(query_words)
                if end > len(words):
                    break
                if words[start:end] == query_words:
                    matched = line_tokens[start:end]
                    left = min(int(t["left"]) for t in matched)
                    top = min(int(t["top"]) for t in matched)
                    right = max(int(t["left"]) + int(t["width"]) for t in matched)
                    bottom = max(int(t["top"]) + int(t["height"]) for t in matched)
                    return (left + right) // 2, (top + bottom) // 2

        # Fallback: single-word contains match.
        for token in tokens:
            token_text = str(token["text"]).lower()
            if query in token_text:
                x = int(token["left"]) + int(token["width"]) // 2
                y = int(token["top"]) + int(token["height"]) // 2
                return x, y

        return None

    def _resolve_click_target_for_mode(self, mode: str) -> tuple[int, int] | None:
        if mode == "text":
            return self._find_text_target()
        return self._resolve_click_target()

    def _perform_click(self) -> bool:
        target = self._resolve_click_target_for_mode(self.target_mode_var.get())
        if target is None:
            return False

        x, y = target
        self._set_cursor_position(x, y)
        self._left_click()
        return True

    def _show_match_marker(self, x: int, y: int) -> None:
        marker = tk.Toplevel(self.root)
        marker.overrideredirect(True)
        marker.attributes("-topmost", True)
        marker.configure(bg="#ff3b30")
        marker.geometry(f"20x20+{x - 10}+{y - 10}")
        marker.after(700, marker.destroy)

    def test_match(self) -> None:
        mode = self.target_mode_var.get()
        if mode not in ("image", "text"):
            self.status_var.set("Switch target mode to image or text search first")
            return

        try:
            target = self._resolve_click_target_for_mode(mode)
        except Exception as exc:
            self.status_var.set(f"Test failed: {exc}")
            return

        if target is None:
            if mode == "text":
                self.status_var.set("Text not found. Try lower OCR confidence or simpler text.")
            else:
                self.status_var.set("No match found. Try a tighter image or lower confidence.")
            return

        x, y = target
        self._show_match_marker(x, y)
        self.status_var.set(f"Match found at X={x}, Y={y}")

    def _left_click(self) -> None:
        ctypes.windll.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _on_pin_window_change(self) -> None:
        self.root.attributes("-topmost", self.pin_window_var.get())

    def _register_hotkeys(self) -> None:
        user32 = ctypes.windll.user32
        ok_start = user32.RegisterHotKey(None, self.HOTKEY_ID_START, 0, self.VK_F6)
        ok_stop = user32.RegisterHotKey(None, self.HOTKEY_ID_STOP, 0, self.VK_F7)
        ok_esc = user32.RegisterHotKey(None, self.HOTKEY_ID_EMERGENCY, 0, self.VK_ESCAPE)
        self.hotkeys_registered = bool(ok_start and ok_stop and ok_esc)

        if not self.hotkeys_registered:
            self.status_var.set("Hotkeys unavailable (already used by another app)")

    def _unregister_hotkeys(self) -> None:
        user32 = ctypes.windll.user32
        user32.UnregisterHotKey(None, self.HOTKEY_ID_START)
        user32.UnregisterHotKey(None, self.HOTKEY_ID_STOP)
        user32.UnregisterHotKey(None, self.HOTKEY_ID_EMERGENCY)

    def _poll_hotkeys(self) -> None:
        msg = ctypes.wintypes.MSG()
        user32 = ctypes.windll.user32

        # Only consume WM_HOTKEY messages so Tk keeps its own paint/input messages.
        while user32.PeekMessageW(
            ctypes.byref(msg),
            None,
            self.WM_HOTKEY,
            self.WM_HOTKEY,
            self.PM_REMOVE,
        ):
            if msg.message == self.WM_HOTKEY:
                if msg.wParam == self.HOTKEY_ID_START:
                    self.start()
                elif msg.wParam in (self.HOTKEY_ID_STOP, self.HOTKEY_ID_EMERGENCY):
                    self.stop()

        self.root.after(50, self._poll_hotkeys)

    def _update_controls_state(self) -> None:
        start_state = "disabled" if (self.running or self.pending_start) else "normal"
        stop_state = "normal" if (self.running or self.pending_start) else "disabled"

        self.start_button.configure(state=start_state)
        self.stop_button.configure(state=stop_state)

        if self.float_start_button is not None:
            self.float_start_button.configure(state=start_state)
        if self.float_stop_button is not None:
            self.float_stop_button.configure(state=stop_state)

    def _run_clicker(self, duration: float | None, interval: float) -> None:
        start_time = time.time()
        next_click = start_time
        misses = 0

        while not self.stop_event.is_set():
            now = time.time()

            if duration is not None and (now - start_time) >= duration:
                break

            if now < next_click:
                time.sleep(min(next_click - now, 0.01))
                continue

            try:
                clicked = self._perform_click()
            except Exception as exc:
                self.root.after(0, lambda: self.status_var.set(f"Error: {exc}"))
                break

            if clicked:
                misses = 0
            else:
                misses += 1
                if misses % 15 == 0:
                    self.root.after(0, lambda: self.status_var.set("Template not found yet..."))

            next_click += interval

        self.root.after(0, self._finish_run)

    def _finish_run(self) -> None:
        self.running = False
        self.pending_start = False
        self.pending_after_id = None
        self.status_var.set("Stopped")
        self._update_controls_state()

    def _begin_run(self, duration: float | None, interval: float, cps: float) -> None:
        if self.running:
            return

        self.pending_start = False
        self.pending_after_id = None
        self.running = True
        self.stop_event.clear()
        self._update_controls_state()

        if duration is None:
            self.status_var.set(f"Running continuously at {cps:g} clicks/sec")
        else:
            self.status_var.set(f"Running for {duration:g}s at {cps:g} clicks/sec")

        self.worker_thread = threading.Thread(
            target=self._run_clicker,
            args=(duration, interval),
            daemon=True,
        )
        self.worker_thread.start()

    def start(self) -> None:
        if self.running or self.pending_start:
            return

        try:
            cps = float(self.cps_var.get())
            if cps <= 0 or cps > self.MAX_CPS:
                raise ValueError
            interval = 1.0 / cps

            start_delay = float(self.start_delay_var.get())
            if start_delay < 0:
                raise ValueError

            if self.target_mode_var.get() == "fixed":
                int(float(self.target_x_var.get()))
                int(float(self.target_y_var.get()))

            if self.target_mode_var.get() == "image":
                if pyautogui is None:
                    raise RuntimeError("Image target mode needs pyautogui installed.")

                confidence = float(self.template_confidence_var.get())
                if confidence < 0.1 or confidence > 1.0:
                    raise ValueError

                if not self.template_path_var.get().strip():
                    raise ValueError

            if self.target_mode_var.get() == "text":
                if pyautogui is None:
                    raise RuntimeError("Text mode needs pyautogui installed.")
                if pytesseract is None:
                    raise RuntimeError("Text mode needs pytesseract installed.")

                text_q = self.text_query_var.get().strip()
                if not text_q:
                    raise ValueError

                text_conf = int(float(self.text_confidence_var.get()))
                if text_conf < 0 or text_conf > 100:
                    raise ValueError

            duration: float | None = None
            if self.mode_var.get() == "timed":
                duration = float(self.duration_var.get())
                if duration <= 0:
                    raise ValueError

        except RuntimeError as err:
            messagebox.showerror("Missing dependency", str(err))
            return
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Use valid values: CPS > 0 and <= 200, duration > 0 for timed mode, delay >= 0, and valid target settings.",
            )
            return

        if start_delay > 0:
            self.status_var.set(f"Starting in {start_delay:g}s...")
            self.pending_start = True
            self._update_controls_state()
            self.pending_after_id = self.root.after(
                int(start_delay * 1000),
                lambda: self._begin_run(duration, interval, cps),
            )
        else:
            self._begin_run(duration, interval, cps)

    def stop(self) -> None:
        if self.pending_start:
            self.pending_start = False
            if self.pending_after_id is not None:
                self.root.after_cancel(self.pending_after_id)
                self.pending_after_id = None
            self.status_var.set("Canceled")
            self._update_controls_state()
            return

        if not self.running:
            return

        self.stop_event.set()
        self.status_var.set("Stopping...")

    def _on_close(self) -> None:
        self.stop_event.set()
        if self.pending_after_id is not None:
            self.root.after_cancel(self.pending_after_id)
            self.pending_after_id = None
        self._unregister_hotkeys()
        if self.float_window is not None:
            self.float_window.destroy()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")

    app = AutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
