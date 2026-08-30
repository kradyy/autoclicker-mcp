"""Unit tests for AutoClickerCore.

All Win32 and optional-dependency calls are mocked so the tests run
on any machine without a display or Tesseract installed.
"""

import json
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Stub out the optional heavy imports before core is loaded so we can
# control them per-test without actually needing the packages installed.
# ---------------------------------------------------------------------------
_pyautogui_stub = MagicMock()
_pytesseract_stub = MagicMock()

sys.modules.setdefault("pyautogui", _pyautogui_stub)
sys.modules.setdefault("pytesseract", _pytesseract_stub)

# Provide the Output.DICT attribute that core.py references.
_pytesseract_stub.Output = MagicMock()
_pytesseract_stub.Output.DICT = "dict"

from core import AutoClickerCore  # noqa: E402  (import after stubs)


class FakePoint:
    x = 42
    y = 99


def _make_core() -> AutoClickerCore:
    return AutoClickerCore()


# ---------------------------------------------------------------------------
# Cursor / click helpers
# ---------------------------------------------------------------------------


class TestCursorAndClick(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_get_cursor_position(self, mock_point_cls, mock_windll, mock_byref) -> None:
        mock_pt = MagicMock()
        mock_pt.x = FakePoint.x
        mock_pt.y = FakePoint.y
        mock_point_cls.return_value = mock_pt
        x, y = self.core.get_cursor_position()
        self.assertEqual(x, FakePoint.x)
        self.assertEqual(y, FakePoint.y)
        mock_windll.user32.GetCursorPos.assert_called_once()

    @patch("ctypes.windll")
    def test_set_cursor_position(self, mock_windll) -> None:
        self.core.set_cursor_position(10, 20)
        mock_windll.user32.SetCursorPos.assert_called_once_with(10, 20)

    @patch("ctypes.windll")
    def test_left_click_sends_both_events(self, mock_windll) -> None:
        self.core.left_click()
        calls = mock_windll.user32.mouse_event.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][0], AutoClickerCore.MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(calls[1][0][0], AutoClickerCore.MOUSEEVENTF_LEFTUP)

    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT", return_value=FakePoint())
    def test_click_at_moves_then_clicks(self, mock_point, mock_windll) -> None:
        self.core.click_at(55, 77)
        mock_windll.user32.SetCursorPos.assert_called_once_with(55, 77)
        self.assertEqual(mock_windll.user32.mouse_event.call_count, 2)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStatus(unittest.TestCase):
    def test_initial_status(self) -> None:
        core = _make_core()
        status = core.get_status()
        self.assertFalse(status["running"])
        self.assertEqual(status["status"], "Idle")

    def test_set_status_updates_message(self) -> None:
        core = _make_core()
        core._set_status("Testing", running=True)
        self.assertEqual(core.get_status()["status"], "Testing")
        self.assertTrue(core.get_status()["running"])


# ---------------------------------------------------------------------------
# Parameter validation in start()
# ---------------------------------------------------------------------------


class TestStartValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    def test_zero_cps_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.start(cps=0)

    def test_over_max_cps_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.start(cps=201)

    def test_negative_delay_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.start(start_delay=-1)

    def test_zero_duration_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.start(duration=0)

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_double_start_raises(self, _mp, _mw, _mb) -> None:
        self.core.start(cps=1, duration=10)
        with self.assertRaises(RuntimeError):
            self.core.start(cps=1, duration=10)
        self.core.stop()


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------


class TestStartStop(unittest.TestCase):
    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_start_sets_running(self, _mp, _mw, _mb) -> None:
        core = _make_core()
        core.start(cps=100, duration=5)
        deadline = time.time() + 1.0
        while not core.running and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(core.running)
        core.stop()

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_stop_clears_running(self, _mp, _mw, _mb) -> None:
        core = _make_core()
        core.start(cps=100, duration=10)
        time.sleep(0.05)
        core.stop()
        self.assertFalse(core.running)

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_timed_run_completes(self, _mp, _mw, _mb) -> None:
        core = _make_core()
        core.start(cps=200, duration=0.1)
        time.sleep(0.4)
        self.assertFalse(core.running)

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_fixed_mode_clicks_at_target(self, _mp, mock_windll, _mb) -> None:
        core = _make_core()
        core.start(cps=50, duration=0.1, target_mode="fixed", x=10, y=20)
        time.sleep(0.3)
        mock_windll.user32.SetCursorPos.assert_called_with(10, 20)


# ---------------------------------------------------------------------------
# Image targeting
# ---------------------------------------------------------------------------


class TestFindImage(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()
        _pyautogui_stub.reset_mock()

    @patch("core.pyautogui", None)
    def test_no_pyautogui_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            self.core.find_image_on_screen("x.png")

    def test_missing_template_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.core.find_image_on_screen("/nonexistent/path.png")

    def test_bad_confidence_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.find_image_on_screen(__file__, confidence=1.5)

    def test_returns_none_when_not_found(self) -> None:
        _pyautogui_stub.locateCenterOnScreen.return_value = None
        result = self.core.find_image_on_screen(__file__, confidence=0.9)
        self.assertIsNone(result)

    def test_returns_coordinates_when_found(self) -> None:
        loc = MagicMock()
        loc.x = 100
        loc.y = 200
        _pyautogui_stub.locateCenterOnScreen.return_value = loc
        result = self.core.find_image_on_screen(__file__, confidence=0.9)
        self.assertEqual(result, (100, 200))


# ---------------------------------------------------------------------------
# OCR text targeting
# ---------------------------------------------------------------------------


class TestFindText(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()
        _pyautogui_stub.reset_mock()
        _pytesseract_stub.reset_mock()

    @patch("core.pytesseract", None)
    def test_no_pytesseract_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            self.core.find_text_on_screen("hello")

    def test_empty_query_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.find_text_on_screen("   ")

    def test_bad_confidence_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core.find_text_on_screen("hi", min_confidence=200)

    def test_returns_none_when_no_tokens(self) -> None:
        _pyautogui_stub.screenshot.return_value = MagicMock()
        _pytesseract_stub.image_to_data.return_value = {
            "text": [],
            "conf": [],
            "left": [],
            "top": [],
            "width": [],
            "height": [],
            "block_num": [],
            "line_num": [],
        }
        result = self.core.find_text_on_screen("hello")
        self.assertIsNone(result)

    def test_finds_single_word(self) -> None:
        _pyautogui_stub.screenshot.return_value = MagicMock()
        _pytesseract_stub.image_to_data.return_value = {
            "text": ["Hello"],
            "conf": ["90"],
            "left": [10],
            "top": [20],
            "width": [40],
            "height": [15],
            "block_num": [1],
            "line_num": [1],
        }
        result = self.core.find_text_on_screen("hello", min_confidence=50)
        self.assertEqual(result, (30, 27))  # center of the token

    def test_finds_phrase_across_tokens(self) -> None:
        _pyautogui_stub.screenshot.return_value = MagicMock()
        _pytesseract_stub.image_to_data.return_value = {
            "text": ["Start", "download"],
            "conf": ["80", "80"],
            "left": [0, 60],
            "top": [10, 10],
            "width": [50, 70],
            "height": [20, 20],
            "block_num": [1, 1],
            "line_num": [1, 1],
        }
        result = self.core.find_text_on_screen("start download", min_confidence=50)
        # center x = (0 + 60 + 70) // 2 = 65, center y = (10 + 30) // 2 = 20
        self.assertEqual(result, (65, 20))


# ---------------------------------------------------------------------------
# _resolve_target routing
# ---------------------------------------------------------------------------


class TestResolveTarget(unittest.TestCase):
    def setUp(self) -> None:
        self.core = _make_core()

    def test_unknown_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.core._resolve_target("bogus", 0, 0, "", 0.9, "", 50)

    def test_cursor_mode_returns_cursor(self) -> None:
        with patch.object(self.core, "get_cursor_position", return_value=(FakePoint.x, FakePoint.y)):
            result = self.core._resolve_target("cursor", 0, 0, "", 0.9, "", 50)
        self.assertEqual(result, (FakePoint.x, FakePoint.y))

    def test_fixed_mode_returns_xy(self) -> None:
        result = self.core._resolve_target("fixed", 7, 13, "", 0.9, "", 50)
        self.assertEqual(result, (7, 13))


if __name__ == "__main__":
    unittest.main()
