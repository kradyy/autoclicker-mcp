"""Tests for the MCP server tool functions.

Each MCP tool is called directly (bypassing the MCP transport layer) with
the clicker's Win32 calls mocked out.
"""

import json
import sys
import time
import unittest
from unittest.mock import MagicMock, patch


# Stub optional dependencies before importing anything that touches them.
_pyautogui_stub = MagicMock()
_pytesseract_stub = MagicMock()
_pytesseract_stub.Output = MagicMock()
_pytesseract_stub.Output.DICT = "dict"

sys.modules.setdefault("pyautogui", _pyautogui_stub)
sys.modules.setdefault("pytesseract", _pytesseract_stub)


class FakePoint:
    x = 55
    y = 88


# Import the server module so we can call its tool functions directly.
import mcp_server  # noqa: E402


class TestStartStopTools(unittest.TestCase):
    def setUp(self) -> None:
        # Reset clicker state between tests.
        mcp_server._clicker.stop()

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_start_clicker_returns_ok(self, _mp, _mw, _mb) -> None:
        result = mcp_server.start_clicker(cps=10, duration=5)
        self.assertIn("started", result.lower())
        mcp_server._clicker.stop()

    def test_stop_clicker_returns_ok(self) -> None:
        result = mcp_server.stop_clicker()
        self.assertIn("stopped", result.lower())

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_start_bad_cps_propagates_error(self, _mp, _mw, _mb) -> None:
        with self.assertRaises(ValueError):
            mcp_server.start_clicker(cps=0)

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_double_start_propagates_error(self, _mp, _mw, _mb) -> None:
        mcp_server.start_clicker(cps=10, duration=10)
        with self.assertRaises(RuntimeError):
            mcp_server.start_clicker(cps=10, duration=10)
        mcp_server._clicker.stop()


class TestStatusTool(unittest.TestCase):
    def setUp(self) -> None:
        mcp_server._clicker.stop()

    def test_get_status_returns_valid_json(self) -> None:
        result = mcp_server.get_clicker_status()
        data = json.loads(result)
        self.assertIn("running", data)
        self.assertIn("status", data)

    def test_status_not_running_after_stop(self) -> None:
        mcp_server.stop_clicker()
        data = json.loads(mcp_server.get_clicker_status())
        self.assertFalse(data["running"])

    @patch("ctypes.byref")
    @patch("ctypes.windll")
    @patch("ctypes.wintypes.POINT")
    def test_status_running_after_start(self, _mp, _mw, _mb) -> None:
        mcp_server.start_clicker(cps=100, duration=5)
        deadline = time.time() + 1.0
        while not mcp_server._clicker.running and time.time() < deadline:
            time.sleep(0.01)
        data = json.loads(mcp_server.get_clicker_status())
        self.assertTrue(data["running"])
        mcp_server.stop_clicker()


class TestCursorTool(unittest.TestCase):
    def test_get_cursor_position_returns_json(self) -> None:
        with patch.object(mcp_server._clicker, "get_cursor_position", return_value=(FakePoint.x, FakePoint.y)):
            result = mcp_server.get_cursor_position()
        data = json.loads(result)
        self.assertEqual(data["x"], FakePoint.x)
        self.assertEqual(data["y"], FakePoint.y)


class TestClickAtTool(unittest.TestCase):
    @patch("ctypes.windll")
    def test_click_at_reports_coordinates(self, mock_windll) -> None:
        result = mcp_server.click_at(123, 456)
        self.assertIn("123", result)
        self.assertIn("456", result)
        mock_windll.user32.SetCursorPos.assert_called_once_with(123, 456)


class TestFindImageTool(unittest.TestCase):
    def test_not_found_returns_false(self) -> None:
        with patch.object(mcp_server._clicker, "find_image_on_screen", return_value=None):
            result = mcp_server.find_image_on_screen(__file__, confidence=0.9)
        data = json.loads(result)
        self.assertFalse(data["found"])

    def test_found_returns_coordinates(self) -> None:
        with patch.object(mcp_server._clicker, "find_image_on_screen", return_value=(300, 400)):
            result = mcp_server.find_image_on_screen(__file__, confidence=0.9)
        data = json.loads(result)
        self.assertTrue(data["found"])
        self.assertEqual(data["x"], 300)
        self.assertEqual(data["y"], 400)

    def test_missing_template_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            mcp_server.find_image_on_screen("/nonexistent/template.png")


class TestFindTextTool(unittest.TestCase):
    def test_empty_query_raises(self) -> None:
        with self.assertRaises(ValueError):
            mcp_server.find_text_on_screen("")

    def test_not_found_returns_false(self) -> None:
        with patch.object(mcp_server._clicker, "find_text_on_screen", return_value=None):
            result = mcp_server.find_text_on_screen("hello")
        data = json.loads(result)
        self.assertFalse(data["found"])

    def test_found_returns_coordinates(self) -> None:
        with patch.object(mcp_server._clicker, "find_text_on_screen", return_value=(30, 27)):
            result = mcp_server.find_text_on_screen("hello", min_confidence=50)
        data = json.loads(result)
        self.assertTrue(data["found"])
        self.assertIn("x", data)
        self.assertIn("y", data)


if __name__ == "__main__":
    unittest.main()
