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
_COMPARE_SPREADSHEET_DATA_DIR = os.path.join(_COMPARE_DATA_DIR, "item_spreadsheets")
_COMPARE_GEMINI_DIR = os.path.join(_COMPARE_PARENT_DIR, "Version 9", "Gemini")


def resolve_json_database_path(db_name: Optional[str]) -> Optional[str]:
    """Resolve JSON item database from Data/."""
    if not db_name:
        return None
    return os.path.join(_COMPARE_DATA_DIR, db_name)


def resolve_spreadsheet_database_path(db_name: Optional[str]) -> Optional[str]:
    """Resolve spreadsheet item database from Data/item_spreadsheets/."""
    if not db_name:
        return None
    return os.path.join(_COMPARE_SPREADSHEET_DATA_DIR, db_name)


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
    items_file_path: Optional[str] = None,
    items_data: Optional[Dict[str, Any]] = None,
    source_type: str,
    database_filename: Optional[str] = None,
    database_path: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Run enrich + logistics for one database path or in-memory catalog. Returns (bundle, error)."""
    db_filename = database_filename or (
        os.path.basename(items_file_path) if items_file_path else "sql://VisionItems"
    )
    db_path = database_path or items_file_path

    if items_data is None:
        if not items_file_path or not os.path.isfile(items_file_path):
            return None, f"Database file not found: {items_file_path}"

    try:
        MovingCalculator, enrich_items = _load_calculator_modules()
        if items_data is not None:
            calculator = MovingCalculator(
                items_file=db_path or "sql://VisionItems",
                items_data=items_data,
            )
        else:
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
                "database_path": db_path,
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


def compute_backend_sql_result(
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    vision_result: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
    *,
    backend_catalog_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare Backend SQL / Cloud DB calculation output using cached SQL catalog data."""
    from vision_catalog_sql_client import (
        load_database_config,
        normalize_sql_items_to_catalog_rows,
    )

    cfg = load_database_config()
    sql_source = f"{cfg['server_with_port']}/{cfg['database']}"
    meta_base = {
        "source_type": "Backend SQL / Cloud DB",
        "database_filename": "VisionItems (SQL)",
        "database_path": sql_source,
        "sql_server": cfg["server"],
        "sql_database": cfg["database"],
        "category_count": None,
    }

    cache = backend_catalog_cache or {}
    if not cache.get("success") or not cache.get("raw_items"):
        error_message = cache.get("last_error") or cache.get("message") or (
            f"Backend SQL catalog could not be loaded from {cfg['server']}/{cfg['database']}."
        )
        return {
            "error": error_message,
            "comparison_meta": meta_base,
        }

    try:
        MovingCalculator, _ = _load_calculator_modules()
        normalized_rows = normalize_sql_items_to_catalog_rows(cache["raw_items"])
        items_data = MovingCalculator.build_items_data_from_catalog_rows(
            normalized_rows,
            source_label="VisionItems SQL",
        )
    except Exception as exc:
        return {
            "error": f"Failed to normalize backend SQL catalog: {exc}",
            "comparison_meta": meta_base,
        }

    bundle, err = compute_source_logistics(
        detected_items,
        logistics_params,
        items_data=items_data,
        source_type="Backend SQL / Cloud DB",
        database_filename="VisionItems (SQL)",
        database_path=sql_source,
    )
    if err:
        return {
            "error": err,
            "comparison_meta": {
                **meta_base,
                "category_count": len(items_data.get("categories", [])),
            },
        }

    result = build_source_result_bundle(bundle, vision_result, metrics)
    result["comparison_meta"]["sql_server"] = cfg["server"]
    result["comparison_meta"]["sql_database"] = cfg["database"]
    result["comparison_meta"]["sql_item_count"] = cache.get("item_count")
    return result


def compute_triple_source_results(
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    vision_result: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
    *,
    json_db_name: Optional[str],
    spreadsheet_db_name: Optional[str],
    backend_catalog_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Prepare JSON, spreadsheet, and Backend SQL calculation outputs separately.
    Each return value is either a full result bundle or an error dict.
    """
    json_result, spreadsheet_result = compute_dual_source_results(
        detected_items,
        logistics_params,
        vision_result,
        metrics,
        json_db_name=json_db_name,
        spreadsheet_db_name=spreadsheet_db_name,
    )
    backend_sql_result = compute_backend_sql_result(
        detected_items,
        logistics_params,
        vision_result,
        metrics,
        backend_catalog_cache=backend_catalog_cache,
    )
    return json_result, spreadsheet_result, backend_sql_result


def compute_dual_source_results(
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    vision_result: Optional[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
    *,
    json_db_name: Optional[str],
    spreadsheet_db_name: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Prepare JSON and spreadsheet calculation outputs separately.
    Each return value is either a full result bundle or an error dict.
    """
    json_path = resolve_json_database_path(json_db_name)
    spreadsheet_path = resolve_spreadsheet_database_path(spreadsheet_db_name)

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
                "database_filename": json_db_name,
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
                "database_filename": spreadsheet_db_name,
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
        st.caption(f"Source: `{db_path}`")
    sql_server = comparison_meta.get("sql_server")
    sql_database = comparison_meta.get("sql_database")
    if sql_server:
        st.caption(f"SQL server: `{sql_server}`")
    if sql_database:
        st.caption(f"SQL database: `{sql_database}`")
    sql_count = comparison_meta.get("sql_item_count")
    if sql_count is not None:
        st.caption(f"Loaded item count: {sql_count}")
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
    backend_sql_result: Optional[Dict[str, Any]] = None,
    *,
    show_performance: bool = False,
    performance_results: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Stack JSON, spreadsheet, and Backend SQL result sections vertically."""
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
        include_metrics=True,
    )
    if backend_sql_result is not None:
        st.markdown("---")
        _render_source_result_tabs(
            "Backend SQL / Cloud DB Results",
            "Backend SQL",
            backend_sql_result,
            source_key="backend_sql",
            include_metrics=True,
        )

    if show_performance and performance_results:
        st.markdown("---")
        st.markdown("## 🧪 Performance")
        display_performance_results(performance_results)
