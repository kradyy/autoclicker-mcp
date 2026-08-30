#!/usr/bin/env python3
"""MCP server that exposes the auto-clicker as AI-callable tools.

Run as a stdio server:
    py mcp_server.py

Or register with your MCP client by pointing it at this script.
"""

import json

from mcp.server.mcpserver import MCPServer

from core import AutoClickerCore

mcp = MCPServer(
    "autoclicker",
    version="1.0.0",
    instructions=(
        "Windows auto-clicker controllable via MCP. "
        "Supports cursor, fixed-coordinate, image-match, and OCR text-match modes."
    ),
)

_clicker = AutoClickerCore()


@mcp.tool(description="Start the auto-clicker in a background thread.")
def start_clicker(
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
) -> str:
    """Start the auto-clicker.

    Args:
        cps: Clicks per second (1–200). Default 10.
        duration: Run duration in seconds. Omit for continuous mode.
        target_mode: Where to click — "cursor", "fixed", "image", or "text".
        x: X coordinate (fixed mode only).
        y: Y coordinate (fixed mode only).
        template_path: Path to template image file (image mode only).
        confidence: Image-match confidence 0.1–1.0 (image mode only).
        text_query: Text phrase to locate on screen (text mode only).
        text_confidence: OCR confidence threshold 0–100 (text mode only).
        start_delay: Seconds to wait before the first click.
    """
    _clicker.start(
        cps=cps,
        duration=duration,
        target_mode=target_mode,
        x=x,
        y=y,
        template_path=template_path,
        confidence=confidence,
        text_query=text_query,
        text_confidence=text_confidence,
        start_delay=start_delay,
    )
    return "Clicker started."


@mcp.tool(description="Stop the auto-clicker.")
def stop_clicker() -> str:
    """Stop the auto-clicker and wait for it to finish."""
    _clicker.stop()
    return "Clicker stopped."


@mcp.tool(description="Return the current clicker state and status message as JSON.")
def get_clicker_status() -> str:
    """Return clicker status.

    Returns JSON with keys:
        running (bool): whether the clicker is active.
        status (str): human-readable status message.
    """
    return json.dumps(_clicker.get_status())


@mcp.tool(description="Return the current mouse cursor screen position as JSON.")
def get_cursor_position() -> str:
    """Return the current mouse cursor position.

    Returns JSON with keys x and y (integer pixel coordinates).
    """
    x, y = _clicker.get_cursor_position()
    return json.dumps({"x": x, "y": y})


@mcp.tool(description="Perform a single left click at the specified screen coordinates.")
def click_at(x: int, y: int) -> str:
    """Click at an absolute screen position.

    Args:
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
    """
    _clicker.click_at(x, y)
    return f"Clicked at ({x}, {y})."


@mcp.tool(
    description=(
        "Locate a template image on screen and return its center coordinates. "
        "Requires pyautogui and pillow (and opencv-python for confidence < 1.0)."
    )
)
def find_image_on_screen(template_path: str, confidence: float = 0.85) -> str:
    """Find an image on screen via template matching.

    Args:
        template_path: Absolute or relative path to a PNG/JPEG template image.
        confidence: Match confidence between 0.1 and 1.0.

    Returns JSON with key 'found' (bool), and 'x', 'y' (int) when found.
    """
    result = _clicker.find_image_on_screen(template_path, confidence)
    if result:
        return json.dumps({"found": True, "x": result[0], "y": result[1]})
    return json.dumps({"found": False})


@mcp.tool(
    description=(
        "Locate text on screen via OCR and return its center coordinates. "
        "Requires pytesseract, pyautogui, pillow, and the Tesseract OCR engine."
    )
)
def find_text_on_screen(text_query: str, min_confidence: int = 45) -> str:
    """Find text on screen using Tesseract OCR.

    Args:
        text_query: Text phrase to locate.
        min_confidence: OCR confidence threshold (0–100).

    Returns JSON with key 'found' (bool), and 'x', 'y' (int) when found.
    """
    result = _clicker.find_text_on_screen(text_query, min_confidence)
    if result:
        return json.dumps({"found": True, "x": result[0], "y": result[1]})
    return json.dumps({"found": False})


if __name__ == "__main__":
    mcp.run()
