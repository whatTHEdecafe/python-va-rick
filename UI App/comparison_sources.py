"""
Comparison source loaders.

Each loader reads the pre-computed result bundle from Streamlit session state
(populated by _store_comparison_results in app.py after a successful analysis).

All loaders are read-only: they never write to session state, files, or databases.

Return contract
---------------
Each loader returns a dict that is either:
  - A full result bundle  (has "calculations", "items", …)
  - An error/unavailable dict  (has "error": str and "comparison_meta": dict)

The panel and engine both handle the error case gracefully.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st


# ---------------------------------------------------------------------------
# Source labels (used as column headers in the comparison panel)
# ---------------------------------------------------------------------------

SOURCE_JSON = "JSON"
SOURCE_SPREADSHEET = "Spreadsheet"
SOURCE_BACKEND_SQL = "Backend SQL"

ALL_SOURCES = [SOURCE_JSON, SOURCE_SPREADSHEET, SOURCE_BACKEND_SQL]

# Default toggle states
SOURCE_DEFAULTS = {
    SOURCE_JSON: True,
    SOURCE_SPREADSHEET: True,
    SOURCE_BACKEND_SQL: True,
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json_comparison_source() -> Dict[str, Any]:
    """
    Return the JSON-database result bundle from session state.
    If no analysis has been run yet, return a structured unavailable state.
    """
    result = st.session_state.get("json_comparison_result")
    if result is None:
        return {
            "error": (
                "No analysis has been run yet. "
                "Run an analysis in the Analyze move tab first."
            ),
            "comparison_meta": {
                "source_type": SOURCE_JSON,
                "database_filename": st.session_state.get("selected_db", "(unknown)"),
                "category_count": None,
            },
        }
    return result


def load_spreadsheet_comparison_source() -> Dict[str, Any]:
    """
    Return the spreadsheet-CSV result bundle from session state.
    If no analysis has been run yet, return a structured unavailable state.
    """
    result = st.session_state.get("spreadsheet_comparison_result")
    if result is None:
        return {
            "error": (
                "No analysis has been run yet. "
                "Run an analysis in the Analyze move tab first."
            ),
            "comparison_meta": {
                "source_type": SOURCE_SPREADSHEET,
                "database_filename": st.session_state.get(
                    "selected_spreadsheet_db", "(unknown)"
                ),
                "category_count": None,
            },
        }
    return result


def load_backend_sql_comparison_source() -> Dict[str, Any]:
    """
    Return the Backend SQL result bundle from session state.

    The bundle may already contain an error (e.g. SQL not configured).
    If nothing is in session state at all, return a clean unavailable state.
    The app must not crash regardless of what is returned here.
    """
    result = st.session_state.get("backend_sql_comparison_result")
    if result is None:
        return {
            "error": "Backend SQL source unavailable / not configured.",
            "comparison_meta": {
                "source_type": SOURCE_BACKEND_SQL,
                "database_filename": "VisionItems (SQL)",
                "category_count": None,
            },
        }
    return result


def load_selected_sources(
    selected: Dict[str, bool],
) -> Dict[str, Dict[str, Any]]:
    """
    Load all toggled-on sources and return them as an ordered dict:
    ``{source_label: result_bundle}``.

    Only sources whose key is ``True`` in *selected* are loaded.
    """
    loaders = {
        SOURCE_JSON: load_json_comparison_source,
        SOURCE_SPREADSHEET: load_spreadsheet_comparison_source,
        SOURCE_BACKEND_SQL: load_backend_sql_comparison_source,
    }
    return {
        label: loaders[label]()
        for label in ALL_SOURCES
        if selected.get(label, False)
    }
