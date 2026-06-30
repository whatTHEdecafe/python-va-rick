"""
Comparison tab UI.

Entry point: render_comparison_tab()

Responsibilities:
- Source toggle row (JSON / Spreadsheet / Backend SQL)
- High-level summary comparison table
- Collapsible detailed sections
- Item comparison table with expandable rows
- Unavailable / error source warnings

Safety contract:
- No files written
- No database writes
- No changes to any existing session state keys
- No imports from app.py (avoids circular imports)
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from comparison_engine import (
    build_fees_comparison,
    build_item_comparison,
    build_labor_comparison,
    build_summary_comparison,
    build_vehicle_crew_comparison,
    build_warnings_comparison,
)
from comparison_sources import (
    ALL_SOURCES,
    SOURCE_BACKEND_SQL,
    SOURCE_DEFAULTS,
    SOURCE_JSON,
    SOURCE_SPREADSHEET,
    load_selected_sources,
)


# ---------------------------------------------------------------------------
# CSS — scoped to elements inside the Comparison tab
# ---------------------------------------------------------------------------

def _comparison_styles() -> str:
    return (
        "<style>"
        # Source error card
        ".cmp-src-error{background:rgba(80,20,20,0.6);border:1px solid #ff6060;"
        "border-radius:4px;padding:0.5rem 0.75rem;margin:0.3rem 0;"
        "font-size:0.92rem;color:#ffaaaa;}"
        # Comparison table
        ".cmp-table{width:100%;border-collapse:collapse;font-size:0.92rem;"
        "font-family:sans-serif;}"
        ".cmp-table th{background:rgba(0,70,110,0.55);color:#00fff9;"
        "padding:5px 8px;text-align:left;border:1px solid rgba(0,255,249,0.2);}"
        ".cmp-table td{padding:4px 8px;border:1px solid rgba(0,255,249,0.1);"
        "color:#e8f4ff;vertical-align:top;}"
        ".cmp-table tr:nth-child(even) td{background:rgba(22,8,46,0.35);}"
        ".cmp-table tr:hover td{background:rgba(40,18,70,0.5);}"
        ".cmp-table td.cmp-label{color:#8899aa;font-size:0.85rem;}"
        ".cmp-table td.cmp-note{color:#6677aa;font-size:0.78rem;font-style:italic;}"
        # Value cells: color only, no status label
        ".cmp-table td.cmp-val-SAME{color:#00e060;}"
        ".cmp-table td.cmp-val-CLOSE{color:#ffd93d;}"
        ".cmp-table td.cmp-val-DIFFERENT{color:#ff9966;}"
        ".cmp-table td.cmp-val-MISSING{color:#8899aa;font-style:italic;}"
        "</style>"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_E = html.escape


def _val_cell(value: str, status: str) -> str:
    """Table cell with color class derived from status (no visible status label)."""
    return f'<td class="cmp-val-{status}">{_E(value)}</td>'


def _source_error_html(label: str, message: str) -> str:
    return (
        f'<div class="cmp-src-error">'
        f'<strong>{_E(label)}:</strong> {_E(message)}'
        f'</div>'
    )


def _build_comparison_table_html(
    rows: List[Dict[str, Any]],
    source_labels: List[str],
    *,
    show_note: bool = False,
) -> str:
    """
    Render a list of engine comparison rows as an HTML table.

    Columns: Field | <source 1> | <source 2> … | [Note]
    Status is used only for per-cell color; no Status column is shown.
    """
    th_sources = "".join(f"<th>{_E(lbl)}</th>" for lbl in source_labels)
    note_th = "<th>Note</th>" if show_note else ""
    header = (
        f'<table class="cmp-table"><thead><tr>'
        f'<th>Field</th>'
        f'{th_sources}'
        f'{note_th}'
        f'</tr></thead><tbody>'
    )
    body_parts = []
    for row in rows:
        label = row["label"]
        values = row["values"]
        status = row["status"]
        note = row.get("note", "")

        val_cells = "".join(
            _val_cell(values.get(lbl, "N/A"), status) for lbl in source_labels
        )
        note_td = f'<td class="cmp-note">{_E(note)}</td>' if show_note else ""
        body_parts.append(
            f'<tr>'
            f'<td class="cmp-label">{_E(label)}</td>'
            f'{val_cells}'
            f'{note_td}'
            f'</tr>'
        )
    return header + "".join(body_parts) + "</tbody></table>"


def _source_meta_caption(result: Dict[str, Any]) -> str:
    meta = result.get("comparison_meta") or {}
    parts = []
    src_type = meta.get("source_type")
    db_file = meta.get("database_filename")
    cat_count = meta.get("category_count")
    sql_server = meta.get("sql_server")
    sql_db = meta.get("sql_database")
    sql_items = meta.get("sql_item_count")
    if src_type:
        parts.append(f"Source: {src_type}")
    if db_file:
        parts.append(f"Database: {db_file}")
    if cat_count is not None:
        parts.append(f"Categories: {cat_count}")
    if sql_server:
        parts.append(f"SQL server: {sql_server}")
    if sql_db:
        parts.append(f"SQL database: {sql_db}")
    if sql_items is not None:
        parts.append(f"Loaded items: {sql_items}")
    return " | ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Source toggle row
# ---------------------------------------------------------------------------

# Stable session-state key that stores {source_label: bool} for the user's
# last toggle selection.  Persists across tab switches and reruns.
_CMP_SOURCES_KEY = "comparison_selected_sources"


def _init_source_selection() -> None:
    """Seed session state with default source selection if not already set."""
    if _CMP_SOURCES_KEY not in st.session_state:
        st.session_state[_CMP_SOURCES_KEY] = dict(SOURCE_DEFAULTS)
    # Also seed the individual widget keys so checkboxes render correctly
    # on the very first render (Streamlit reads widget value from the key).
    saved = st.session_state[_CMP_SOURCES_KEY]
    for src in ALL_SOURCES:
        widget_key = f"cmp_toggle_{src}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = saved.get(src, SOURCE_DEFAULTS.get(src, False))


def _render_source_toggles() -> Dict[str, bool]:
    """
    Render three toggle checkboxes and return the current selection dict.

    Widget state is stored under ``cmp_toggle_<source>`` keys (one per source)
    and also mirrored into the unified ``comparison_selected_sources`` dict so
    the selection survives tab switches and reruns without needing an
    interaction to restore it.
    """
    _init_source_selection()

    st.markdown("**Compare sources:**")
    cols = st.columns(len(ALL_SOURCES) + 2)  # extra cols for breathing room
    selected: Dict[str, bool] = {}
    for i, src in enumerate(ALL_SOURCES):
        widget_key = f"cmp_toggle_{src}"
        with cols[i]:
            # Do NOT pass value= when key= is provided; Streamlit reads from
            # session state automatically and passing value= can cause a
            # redundant-state-reset on some Streamlit versions.
            selected[src] = st.checkbox(src, key=widget_key)

    # Persist the current selection for next render
    st.session_state[_CMP_SOURCES_KEY] = dict(selected)
    return selected


# ---------------------------------------------------------------------------
# High-level summary section
# ---------------------------------------------------------------------------

def _render_summary_section(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    top_rows, _ = build_summary_comparison(source_results)
    html_table = _build_comparison_table_html(top_rows, source_labels, show_note=False)
    st.markdown(_comparison_styles(), unsafe_allow_html=True)
    st.markdown(html_table, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Detailed section: Quote Summary Details
# ---------------------------------------------------------------------------

def _render_quote_summary_details(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    _, all_rows = build_summary_comparison(source_results)
    html_table = _build_comparison_table_html(all_rows, source_labels, show_note=True)
    st.markdown(html_table, unsafe_allow_html=True)
    st.caption(
        "Formula: Final total = labor time × wage rate × movers + GST. "
        "Price range uses min/max hours."
    )


# ---------------------------------------------------------------------------
# Detailed section: Labor Time Breakdown
# ---------------------------------------------------------------------------

def _render_labor_breakdown(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    st.caption(
        "Total labor time is calculated from item loading/unloading times, "
        "stairs/elevator adjustments, crew effects, and final rounding."
    )
    rows = build_labor_comparison(source_results)
    html_table = _build_comparison_table_html(rows, source_labels, show_note=True)
    st.markdown(html_table, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Detailed section: Item Breakdown
# ---------------------------------------------------------------------------

def _fmt_time(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)


def _render_item_breakdown(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    st.caption(
        "Each item's total labor is: (base time + load time + unload time) × quantity, "
        "then adjusted for stairs/elevator and batching/stacking."
    )

    item_rows = build_item_comparison(source_results)

    if not item_rows:
        st.info("No item data available from selected sources.")
        return

    # Summary DataFrame (spreadsheet-style) — Status column intentionally omitted
    df_data = []
    for row in item_rows:
        record: Dict[str, Any] = {
            "Item": row["name"],
            "Qty": row["quantity"] if row["quantity"] is not None else "N/A",
        }
        for src in source_labels:
            item = row["source_items"].get(src)
            if item is None:
                record[f"{src} Total (min)"] = "—"
            else:
                record[f"{src} Total (min)"] = _fmt_time(item.get("totalTime"))
        df_data.append(record)

    df = pd.DataFrame(df_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Expandable per-item detail
    st.markdown("**Item details (expand each item):**")
    for row in item_rows:
        with st.expander(row["name"], expanded=False):
            detail_cols = st.columns(len(source_labels))
            for col_idx, src in enumerate(source_labels):
                with detail_cols[col_idx]:
                    st.markdown(f"**{src}**")
                    item = row["source_items"].get(src)
                    details = row["source_details"].get(src, {})
                    match_row = details.get("match")
                    time_row = details.get("time")

                    if item is None and match_row is None:
                        st.caption("Missing from this source.")
                        continue

                    detail_rows: List[tuple] = []
                    if item:
                        detail_rows += [
                            ("Name", item.get("name", "N/A")),
                            ("Category", item.get("category", "N/A")),
                            ("Size", item.get("size", "N/A")),
                            ("Qty", str(item.get("quantity", "N/A"))),
                            ("Load time (min)", _fmt_time(item.get("loadTime"))),
                            ("Unload time (min)", _fmt_time(item.get("unloadTime"))),
                            ("Time/item (min)", _fmt_time(item.get("timePerItem"))),
                            ("Total time (min)", _fmt_time(item.get("totalTime"))),
                        ]
                    if match_row:
                        detail_rows += [
                            ("Matched catalog", match_row.get("matchedCategoryName", "N/A")),
                            ("Match method", match_row.get("matchMethod", "N/A")),
                            ("Fallback used", str(match_row.get("unknownFallbackUsed", False))),
                        ]
                    if time_row:
                        detail_rows += [
                            ("Base time used (min)", _fmt_time(time_row.get("baseTimeUsed"))),
                            ("Total after qty (min)", _fmt_time(time_row.get("totalTimeAfterQuantity"))),
                        ]

                    for label, value in detail_rows:
                        st.text(f"{label}: {value}")


# ---------------------------------------------------------------------------
# Detailed section: Fees and Rates
# ---------------------------------------------------------------------------

def _render_fees_section(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    st.caption(
        "Service fee, transfer fee, business fee, and catalog/pricing settings."
    )
    rows = build_fees_comparison(source_results)
    html_table = _build_comparison_table_html(rows, source_labels, show_note=False)
    st.markdown(html_table, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Detailed section: Vehicle / Crew Details
# ---------------------------------------------------------------------------

def _render_vehicle_crew_section(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    st.caption(
        "Vehicle selection and crew sizing are determined by volume, weight, "
        "and the auto-mover algorithm."
    )
    rows = build_vehicle_crew_comparison(source_results)
    html_table = _build_comparison_table_html(rows, source_labels, show_note=False)
    st.markdown(html_table, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Detailed section: Warnings
# ---------------------------------------------------------------------------

def _render_warnings_section(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    warnings_map = build_warnings_comparison(source_results)
    any_warnings = any(bool(w) for w in warnings_map.values())

    if not any_warnings:
        st.success("No warnings from any selected source.")
        return

    warn_cols = st.columns(len(source_labels))
    for col_idx, src in enumerate(source_labels):
        with warn_cols[col_idx]:
            st.markdown(f"**{src}**")
            warns = warnings_map.get(src, [])
            if warns:
                for w in warns:
                    st.warning(w)
            else:
                st.success("No warnings.")


# ---------------------------------------------------------------------------
# Detailed section: Raw Source Diagnostics
# ---------------------------------------------------------------------------

def _render_diagnostics_section(
    source_results: Dict[str, Dict[str, Any]],
    source_labels: List[str],
) -> None:
    diag_cols = st.columns(len(source_labels))
    for col_idx, src in enumerate(source_labels):
        with diag_cols[col_idx]:
            st.markdown(f"**{src}**")
            result = source_results.get(src, {})
            error = result.get("error")
            meta = result.get("comparison_meta") or {}

            if error:
                st.error(error)
            else:
                st.success("Source loaded successfully.")

            caption = _source_meta_caption(result)
            if caption:
                st.caption(caption)

            if not error:
                calc = result.get("calculations") or {}
                items = calc.get("items") or []
                time_info = calc.get("time") or {}
                pricing = calc.get("pricing") or {}
                st.caption(
                    f"Items: {len(items)} | "
                    f"Total hrs: {time_info.get('totalHours', 'N/A')} | "
                    f"Price min: {pricing.get('totalExpectedPriceMin', 'N/A')}"
                )


# ---------------------------------------------------------------------------
# Source error banner
# ---------------------------------------------------------------------------

def _render_source_error_banners(
    source_results: Dict[str, Dict[str, Any]],
) -> None:
    """Show a small error card for any source that has an error."""
    st.markdown(_comparison_styles(), unsafe_allow_html=True)
    html_parts = []
    for src, result in source_results.items():
        if result.get("error"):
            html_parts.append(_source_error_html(src, result["error"]))
    if html_parts:
        st.markdown("".join(html_parts), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Session state flag used by the one-shot rerun guard (belt-and-suspenders).
# Avoids infinite rerun loops if comparison data is unavailable for any reason.
_CMP_RERUN_PENDING_KEY = "cmp_rerun_pending"


def render_comparison_tab() -> None:
    """
    Render the full Comparison tab.

    Called from app.py inside `with tab_comparison:` which is placed AFTER
    `with tab_analyze:` so that _store_comparison_results() has already run
    by the time this function executes on the same Streamlit rerun pass.

    This function is self-contained and does not import from app.py.
    """
    st.markdown("## Source Comparison")
    st.caption(
        "Compare calculation inputs and results across JSON, Spreadsheet, "
        "and Backend SQL sources side by side."
    )

    # ------------------------------------------------------------------
    # 1. Initialize + render source toggles
    # ------------------------------------------------------------------
    selected = _render_source_toggles()
    active_sources = [s for s in ALL_SOURCES if selected.get(s, False)]

    if len(active_sources) < 2:
        st.info("Select at least two sources to compare.")
        return

    # ------------------------------------------------------------------
    # 2. Belt-and-suspenders rerun guard
    #
    # Primary fix: tab_analyze renders before tab_comparison in app.py so
    # comparison results are always available on the same rerun.
    #
    # This guard handles any residual edge case where enriched analysis data
    # exists but the comparison result keys haven't been written yet (e.g.
    # a replay/batch path that stores enriched_items differently).
    # It triggers at most ONE extra rerun and then stands down.
    # ------------------------------------------------------------------
    analysis_data_exists = st.session_state.get("enriched_items") is not None
    comparison_results_exist = (
        st.session_state.get("json_comparison_result") is not None
        or st.session_state.get("spreadsheet_comparison_result") is not None
        or st.session_state.get("backend_sql_comparison_result") is not None
    )

    if analysis_data_exists and not comparison_results_exist:
        if not st.session_state.get(_CMP_RERUN_PENDING_KEY):
            # First time: set flag, show friendly message, request one rerun
            st.session_state[_CMP_RERUN_PENDING_KEY] = True
            st.info("Loading comparison data from the latest analysis…")
            st.rerun()
            return  # unreachable after rerun, but keeps linters happy
        # Second time (rerun happened but data still missing): clear flag
        # and fall through to show whatever error messages the loaders give.
        st.session_state[_CMP_RERUN_PENDING_KEY] = False
    else:
        # Normal path: clear the pending flag so it resets for next analysis
        st.session_state[_CMP_RERUN_PENDING_KEY] = False

    # ------------------------------------------------------------------
    # 3. Load sources (always reads latest session state)
    # ------------------------------------------------------------------
    source_results = load_selected_sources(selected)

    # Show error banners for unavailable sources (non-crashing)
    _render_source_error_banners(source_results)

    # Count sources with usable data
    usable_sources = [
        src for src, r in source_results.items() if not r.get("error")
    ]

    if not usable_sources:
        # Distinguish between "never ran" vs "data missing for another reason"
        if not analysis_data_exists:
            st.info(
                "No analysis has been run yet. "
                "Run an analysis in the Analyze move tab first, "
                "then return here to compare sources."
            )
        else:
            st.warning(
                "Analysis data found but comparison results could not be loaded "
                "for any selected source. Check the diagnostics expander below."
            )
            with st.expander("Raw Source Availability / Diagnostics", expanded=True):
                _render_diagnostics_section(source_results, active_sources)
        return

    # If only one source has data, we still need at least 2 for comparison
    if len(usable_sources) < 2:
        unavailable = [s for s in active_sources if s not in usable_sources]
        st.warning(
            f"Only {usable_sources[0]} has usable data. "
            + (
                f"{', '.join(unavailable)} "
                + ("is" if len(unavailable) == 1 else "are")
                + " unavailable. Select an additional source with data to compare."
                if unavailable
                else "Select an additional source with data to compare."
            )
        )
        with st.expander("Raw Source Availability / Diagnostics", expanded=True):
            _render_diagnostics_section(source_results, active_sources)
        return

    # ------------------------------------------------------------------
    # 4. High-level summary comparison
    # ------------------------------------------------------------------
    st.markdown("### Quick Summary")
    _render_summary_section(source_results, active_sources)

    st.markdown("---")

    # ------------------------------------------------------------------
    # 5. Collapsible detailed sections
    # ------------------------------------------------------------------
    with st.expander("Quote Summary Details", expanded=False):
        _render_quote_summary_details(source_results, active_sources)

    with st.expander("Labor Time Breakdown", expanded=False):
        _render_labor_breakdown(source_results, active_sources)

    with st.expander("Item Breakdown", expanded=False):
        _render_item_breakdown(source_results, active_sources)

    with st.expander("Fees and Rates", expanded=False):
        _render_fees_section(source_results, active_sources)

    with st.expander("Vehicle / Crew Details", expanded=False):
        _render_vehicle_crew_section(source_results, active_sources)

    with st.expander("Warnings", expanded=False):
        _render_warnings_section(source_results, active_sources)

    with st.expander("Raw Source Availability / Diagnostics", expanded=False):
        _render_diagnostics_section(source_results, active_sources)
