"""
Temporary CSV vs JSON output comparison panel (debug only).

Remove this module and its call site in app.py when comparison is no longer needed.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st


_COMPARE_PANEL_DIR = os.path.dirname(os.path.abspath(__file__))
_COMPARE_PARENT_DIR = os.path.dirname(_COMPARE_PANEL_DIR)
_COMPARE_DATA_DIR = os.path.join(_COMPARE_PARENT_DIR, "Data")
_COMPARE_GEMINI_DIR = os.path.join(_COMPARE_PARENT_DIR, "Version 9", "Gemini")

COMPARE_JSON_DB = "moving_items_logistics_v2.json"
COMPARE_SPREADSHEET_DB = "VA fixed names and high base time.csv"


def resolve_compare_database_path(db_name: str) -> Optional[str]:
    """Resolve item database from Data/ first, then project root."""
    if not db_name:
        return None
    data_path = os.path.join(_COMPARE_DATA_DIR, db_name)
    if os.path.isfile(data_path):
        return data_path
    root_path = os.path.join(_COMPARE_PARENT_DIR, db_name)
    if os.path.isfile(root_path):
        return root_path
    return data_path


def _load_calculator_modules():
    if _COMPARE_GEMINI_DIR not in sys.path:
        sys.path.insert(0, _COMPARE_GEMINI_DIR)
    from modules.calculator import MovingCalculator
    from modules.item_enrichment import enrich_items

    return MovingCalculator, enrich_items


def compute_source_logistics(
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    *,
    items_file_path: str,
    source_type: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Run enrich + logistics for one database path. Returns (bundle, error)."""
    db_filename = os.path.basename(items_file_path)
    if not os.path.isfile(items_file_path):
        return None, f"Database file not found: {items_file_path}"

    try:
        MovingCalculator, enrich_items = _load_calculator_modules()
        calculator = MovingCalculator(items_file=items_file_path)
        categories = calculator.items_data.get("categories", []) if calculator.items_data else []
        category_count = len(categories)

        raw_copy = [copy.deepcopy(i) for i in (detected_items or [])]
        enriched = enrich_items(calculator, raw_copy)

        logistics = calculator.calculate_total_logistics(
            enriched,
            logistics_params["pickup_access"],
            logistics_params["dropoff_access"],
            logistics_params["travel_time"],
            logistics_params["pre_move_travel"],
            forced_movers=logistics_params.get("forced_movers"),
        )
        if not logistics:
            return None, "Calculation returned no result."

        bundle = {
            "items": enriched,
            "calculations": logistics,
            "comparison_meta": {
                "source_type": source_type,
                "database_filename": db_filename,
                "database_path": items_file_path,
                "category_count": category_count,
            },
        }
        return bundle, None
    except Exception as exc:
        return None, str(exc)


def build_source_result_bundle(
    source_bundle: Dict[str, Any],
    vision_result: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Shape compatible with existing result tab renderers."""
    return {
        "items": source_bundle.get("items", []),
        "summary": (vision_result or {}).get("summary", {}),
        "calculations": source_bundle.get("calculations", {}),
        "metrics": dict(metrics or {}),
        "comparison_meta": source_bundle.get("comparison_meta", {}),
    }


def compute_dual_source_results(
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    vision_result: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Prepare JSON and spreadsheet calculation outputs separately.
    Each return value is either a full result bundle or an error dict.
    """
    json_path = resolve_compare_database_path(COMPARE_JSON_DB)
    spreadsheet_path = resolve_compare_database_path(COMPARE_SPREADSHEET_DB)

    json_bundle, json_err = compute_source_logistics(
        detected_items,
        logistics_params,
        items_file_path=json_path,
        source_type="JSON",
    )
    if json_err:
        json_result = {
            "error": json_err,
            "comparison_meta": {
                "source_type": "JSON",
                "database_filename": COMPARE_JSON_DB,
                "database_path": json_path,
                "category_count": None,
            },
        }
    else:
        json_result = build_source_result_bundle(json_bundle, vision_result, metrics)

    sheet_bundle, sheet_err = compute_source_logistics(
        detected_items,
        logistics_params,
        items_file_path=spreadsheet_path,
        source_type="Spreadsheet CSV",
    )
    if sheet_err:
        spreadsheet_result = {
            "error": sheet_err,
            "comparison_meta": {
                "source_type": "Spreadsheet CSV",
                "database_filename": COMPARE_SPREADSHEET_DB,
                "database_path": spreadsheet_path,
                "category_count": None,
            },
        }
    else:
        spreadsheet_result = build_source_result_bundle(sheet_bundle, vision_result, metrics)

    return json_result, spreadsheet_result


def _render_source_database_header(comparison_meta: Dict[str, Any]) -> None:
    """Show source-specific database info at top of debug panel."""
    if not comparison_meta:
        return
    st.markdown("### Database source")
    lines = [
        "| Field | Value |",
        "| --- | --- |",
        f"| Source type | {comparison_meta.get('source_type', 'N/A')} |",
        f"| Database filename | {comparison_meta.get('database_filename', 'N/A')} |",
        f"| Category count | {comparison_meta.get('category_count', 'N/A')} |",
    ]
    st.markdown("\n".join(lines))
    db_path = comparison_meta.get("database_path")
    if db_path:
        st.caption(f"Path: `{db_path}`")
    st.markdown("---")


def _render_source_result_tabs(
    section_title: str,
    tab_prefix: str,
    result: Dict[str, Any],
    *,
    source_key: str,
    include_metrics: bool = False,
) -> None:
    """Render one comparison section using original non-debug tab layouts."""
    from app import (
        display_calculation_debug_panel,
        render_result_logistics_tab,
        render_result_overview_tab,
        render_result_pricing_tab,
        render_result_time_breakdown_tab,
    )

    widget_key_prefix = f"{source_key}_"

    with st.container(border=True):
        st.markdown(f"## {section_title}")
        comparison_meta = result.get("comparison_meta", {})

        if result.get("error"):
            st.error(result["error"])
            _render_source_database_header(comparison_meta)
            return

        tab_names = [
            f"{tab_prefix} Overview",
            f"{tab_prefix} Time Breakdown",
            f"{tab_prefix} Logistics",
            f"{tab_prefix} Pricing",
            f"{tab_prefix} Debug Panel",
        ]
        tabs = st.tabs(tab_names, key=f"{widget_key_prefix}result_tabs")
        tab_overview, tab_time, tab_logistics, tab_pricing, tab_debug = tabs

        with tab_overview:
            render_result_overview_tab(result, include_metrics=include_metrics)

        with tab_time:
            render_result_time_breakdown_tab(result, widget_key_prefix=widget_key_prefix)

        with tab_logistics:
            render_result_logistics_tab(result, widget_key_prefix=widget_key_prefix)

        with tab_pricing:
            render_result_pricing_tab(result)

        with tab_debug:
            _render_source_database_header(comparison_meta)
            display_calculation_debug_panel(
                result,
                comparison_meta=comparison_meta,
                enable_debug_simulation=False,
                widget_key_prefix=widget_key_prefix,
            )


def render_csv_json_comparison_sections(
    json_result: Dict[str, Any],
    spreadsheet_result: Dict[str, Any],
    *,
    show_performance: bool = False,
    performance_results: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Stack JSON and spreadsheet result sections vertically."""
    from app import display_performance_results

    _render_source_result_tabs(
        "JSON Database Results",
        "JSON",
        json_result,
        source_key="json",
        include_metrics=True,
    )
    st.markdown("---")
    _render_source_result_tabs(
        "Spreadsheet CSV Database Results",
        "Spreadsheet",
        spreadsheet_result,
        source_key="spreadsheet",
    )

    if show_performance and performance_results:
        st.markdown("---")
        st.markdown("## 🧪 Performance")
        display_performance_results(performance_results)
