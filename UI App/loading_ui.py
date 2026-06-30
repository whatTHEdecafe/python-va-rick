"""80s-style loading UI for Gemini vision analysis (CSS-only, no assets)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import streamlit as st
import streamlit.components.v1 as components

# Literal colors (iframe cannot see .stApp :root variables)
_CYAN = "#00fff9"
_MAGENTA = "#ff2eea"
_AMBER = "#ffd93d"
_TEXT = "#e8f4ff"
_MUTED = "#8899aa"
_PANEL_BG = "linear-gradient(180deg, rgba(22, 8, 46, 0.98) 0%, rgba(10, 5, 24, 1) 100%)"

VISION_LOADING_CSS = f"""
    @keyframes vision-scan-blink {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.35; }}
    }}
    @keyframes vision-step-pulse {{
        0%, 100% {{
            box-shadow: 0 0 8px rgba(0, 255, 249, 0.35);
            border-color: {_CYAN};
        }}
        50% {{
            box-shadow: 0 0 18px rgba(255, 46, 234, 0.55);
            border-color: {_MAGENTA};
        }}
    }}
    @keyframes vision-bar-shimmer {{
        0% {{ background-position: 200% 0; }}
        100% {{ background-position: -200% 0; }}
    }}
    @keyframes vision-cursor-blink {{
        0%, 49% {{ opacity: 1; }}
        50%, 100% {{ opacity: 0; }}
    }}

    .vision-scan-panel {{
        font-family: 'VT323', monospace;
        color: {_TEXT};
        background: {_PANEL_BG};
        border: 3px solid {_CYAN};
        border-radius: 4px;
        padding: 14px 16px 12px;
        box-sizing: border-box;
        box-shadow:
            0 0 20px rgba(0, 255, 249, 0.25),
            inset 0 0 24px rgba(255, 46, 234, 0.08);
        width: 100%;
    }}

    .vision-scan-title {{
        font-family: 'Press Start 2P', monospace;
        font-size: 11px;
        line-height: 1.7;
        color: {_AMBER};
        text-shadow: 0 0 12px rgba(255, 217, 61, 0.5);
        animation: vision-scan-blink 1.2s step-end infinite;
        margin: 0 0 6px;
        letter-spacing: 0.12em;
    }}

    .vision-scan-sub {{
        font-size: 18px;
        color: {_MUTED};
        margin: 0 0 12px;
    }}

    .vision-scan-steps {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: stretch;
        justify-content: space-between;
        margin-bottom: 12px;
    }}

    .vision-scan-step {{
        flex: 1 1 7rem;
        min-width: 5.5rem;
        text-align: center;
        padding: 8px 6px;
        border: 2px solid rgba(0, 255, 249, 0.4);
        background: rgba(30, 15, 60, 0.9);
        font-size: 16px;
        line-height: 1.25;
        color: {_MUTED};
        box-sizing: border-box;
    }}

    .vision-scan-step .step-num {{
        display: block;
        font-size: 13px;
        opacity: 0.8;
        margin-bottom: 4px;
        color: {_MAGENTA};
    }}

    .vision-scan-step.is-active {{
        color: {_CYAN};
        animation: vision-step-pulse 1.4s ease-in-out infinite;
    }}

    .vision-scan-step.is-done {{
        color: #bfffdf;
        border-color: rgba(0, 255, 136, 0.5);
    }}

    .vision-scan-bar-wrap {{
        height: 12px;
        border: 2px solid {_MAGENTA};
        background: rgba(0, 0, 0, 0.4);
        overflow: hidden;
        box-sizing: border-box;
    }}

    .vision-scan-bar {{
        height: 100%;
        width: 100%;
        background: linear-gradient(
            90deg,
            transparent 0%,
            {_CYAN} 25%,
            {_MAGENTA} 50%,
            {_AMBER} 75%,
            transparent 100%
        );
        background-size: 200% 100%;
        animation: vision-bar-shimmer 1.8s linear infinite;
    }}

    .vision-scan-cursor {{
        display: inline-block;
        animation: vision-cursor-blink 0.9s step-end infinite;
    }}
"""

VISION_LOADING_BODY = """
  <div class="vision-scan-panel" role="status" aria-live="polite" aria-busy="true">
    <p class="vision-scan-title">SCANNING<span class="vision-scan-cursor">_</span></p>
    <p class="vision-scan-sub">Videos ~1 min · images faster</p>
    <div class="vision-scan-steps">
      <div class="vision-scan-step is-done"><span class="step-num">01</span>MEDIA IN</div>
      <div class="vision-scan-step is-active"><span class="step-num">02</span>NEURAL SCAN</div>
      <div class="vision-scan-step"><span class="step-num">03</span>ITEM MATCH</div>
      <div class="vision-scan-step"><span class="step-num">04</span>BUILD QUOTE</div>
    </div>
    <div class="vision-scan-bar-wrap" aria-hidden="true">
      <div class="vision-scan-bar"></div>
    </div>
  </div>
"""

LOGISTICS_SPINNER_MSG = "RECALC QUOTE // NO SCAN (cached vision)"

_IFRAME_HEIGHT = 200


def _vision_loading_iframe_html() -> str:
    """Self-contained document so CSS applies inside Streamlit's HTML iframe."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: transparent;
      overflow: hidden;
    }}
    {VISION_LOADING_CSS}
  </style>
</head>
<body>
{VISION_LOADING_BODY}
</body>
</html>"""


def inject_vision_loading_styles() -> None:
    """No-op kept for app.py compatibility; styles live in the iframe document."""
    pass


def render_vision_loading_infographic(container: Any) -> None:
    """Render the 80s infographic (isolated iframe with embedded CSS)."""
    with container.container():
        components.html(
            _vision_loading_iframe_html(),
            height=_IFRAME_HEIGHT,
            scrolling=False,
        )


@contextmanager
def vision_loading_panel() -> Iterator[None]:
    """Show vision loading infographic while blocking work runs; clear when done."""
    slot = st.empty()
    render_vision_loading_infographic(slot)
    try:
        yield
    finally:
        slot.empty()
