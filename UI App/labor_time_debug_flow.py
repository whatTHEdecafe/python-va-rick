"""
Display-only labor time flow for CSV vs JSON comparison debug panels.

Extracts values from existing calculationDebug / algorithmBreakdown objects.
Does not change calculation logic.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

_BATCH_NAME_RE = re.compile(r"^(.+?) \(x(\d+)\)$")


def format_item_time_value(value: Any) -> str:
    """Item row time: whole numbers without .0; one decimal when needed (no int rounding)."""
    if value is None or value == "" or value == "N/A":
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    rounded_one = round(number, 1)
    if rounded_one == int(rounded_one):
        return str(int(rounded_one))
    return f"{rounded_one:.1f}"


def format_item_time_total_lines(value: Any) -> Tuple[str, str]:
    """Item breakdown totals: '299 minutes' and '4 hr 59 min' on separate lines."""
    if value is None or value == "" or value == "N/A":
        return "Not available", ""
    try:
        total = float(value)
    except (TypeError, ValueError):
        return "Not available", ""

    minutes_line = f"{format_item_time_value(total)} minutes"
    hours = int(total // 60)
    remainder = round(total - (hours * 60), 1)
    if remainder == int(remainder):
        rem_str = str(int(remainder))
    else:
        rem_str = f"{remainder:.1f}"
    return minutes_line, f"{hours} hr {rem_str} min"


def format_item_time_total_html(value: Any) -> str:
    """HTML for two-line total cells in item breakdown grid."""
    minutes_line, hours_line = format_item_time_total_lines(value)
    if not hours_line:
        return minutes_line
    return f"{minutes_line}<br>{hours_line}"


def format_debug_minutes(value: Any) -> str:
    """Format minutes: whole numbers without .0; preserve meaningful decimals."""
    if value is None or value == "" or value == "N/A":
        return "Not available"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if number == int(number):
        return str(int(number))
    text = f"{number:.4f}".rstrip("0").rstrip(".")
    return text


def format_total_minutes_two_lines(value: Any) -> Tuple[str, str]:
    """Return (minutes_line, hours_line) for important totals."""
    if value is None or value == "" or value == "N/A":
        return "Not available", ""
    try:
        total = float(value)
    except (TypeError, ValueError):
        return "Not available", ""

    minutes_line = f"{format_debug_minutes(total)} minutes"
    hours = int(total // 60)
    remainder = total - (hours * 60)
    if remainder == int(remainder):
        hours_line = f"{hours} hours {int(remainder)} minutes"
    else:
        hours_line = f"{hours} hours {format_debug_minutes(remainder)} minutes"
    return minutes_line, hours_line


def _parse_batch_task_name(name: str) -> Tuple[str, Optional[int]]:
    match = _BATCH_NAME_RE.match(name or "")
    if match:
        return match.group(1), int(match.group(2))
    return name, None


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "N/A"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _allocate_stackable_savings(
    item_rows: List[Dict[str, Any]],
    task_debug: List[Dict[str, Any]],
) -> None:
    """Display-only: distribute batch savings across stackable item rows."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in item_rows:
        if row.get("stackable") and _safe_float(row.get("savings_pct")) > 0:
            key = (row.get("name", ""), row.get("size", ""))
            groups.setdefault(key, []).append(row)

    batch_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for task in task_debug:
        if not task.get("batchingApplied"):
            continue
        base_name, _ = _parse_batch_task_name(task.get("taskName", ""))
        for key in groups:
            if key[0] == base_name:
                batch_by_key[key] = task
                break

    for key, rows in groups.items():
        group_raw = sum(_safe_float(r.get("raw_total")) for r in rows)
        batch_task = batch_by_key.get(key)
        if not batch_task or group_raw <= 0:
            for row in rows:
                row["stackable_savings"] = 0.0
                row["adjusted_total"] = _safe_float(row.get("raw_total"))
            continue

        adjusted_group = _safe_float(batch_task.get("taskCombinedTime"))
        group_savings = max(group_raw - adjusted_group, 0.0)
        for row in rows:
            share = _safe_float(row.get("raw_total")) / group_raw
            row_savings = group_savings * share
            row["stackable_savings"] = row_savings
            row["adjusted_total"] = _safe_float(row.get("raw_total")) - row_savings

    for row in item_rows:
        if "adjusted_total" not in row:
            row["stackable_savings"] = 0.0
            row["adjusted_total"] = _safe_float(row.get("raw_total"))


def extract_labor_flow_model(calculations: Dict[str, Any]) -> Dict[str, Any]:
    """Build a display model from existing calculator debug output."""
    debug = calculations.get("calculationDebug") or {}
    matching = debug.get("matching") or []
    item_times = debug.get("itemTimes") or []
    task_debug = debug.get("taskDebug") or []
    algo = calculations.get("time", {}).get("algorithmBreakdown") or {}
    access = debug.get("access") or {}

    item_rows: List[Dict[str, Any]] = []
    for idx, item_time in enumerate(item_times):
        match_row = matching[idx] if idx < len(matching) else {}
        unload_time = _safe_float(item_time.get("unloadTime"))
        load_time = _safe_float(item_time.get("loadTime"))
        item_rows.append({
            "name": item_time.get("name", "Unknown"),
            "category": match_row.get("matchedCategoryName", "Unknown"),
            "size": item_time.get("size", "Unknown"),
            "qty": int(item_time.get("quantity", 1)),
            "base_time": _safe_float(item_time.get("baseTimeUsed")),
            "load_time": load_time,
            "unload_time": unload_time,
            "unload_added": unload_time > 0,
            "item_total": _safe_float(item_time.get("totalTimePerItem")),
            "raw_total": _safe_float(item_time.get("totalTimeAfterQuantity")),
            "stackable": bool(item_time.get("stackable")),
            "savings_pct": item_time.get("stackableSavings"),
            "stackable_savings": 0.0,
            "adjusted_total": _safe_float(item_time.get("totalTimeAfterQuantity")),
        })

    _allocate_stackable_savings(item_rows, task_debug)

    raw_item_sum = sum(row["raw_total"] for row in item_rows)
    task_sum = sum(_safe_float(task.get("taskCombinedTime")) for task in task_debug)
    batching_savings = max(raw_item_sum - task_sum, 0.0) if task_debug else 0.0

    labor_steps: List[Dict[str, Any]] = [
        {
            "step": "1. Sum item totals (before crew/stairs/elevator)",
            "detail": "Raw per-item totals summed before stackable batching",
            "minutes": raw_item_sum,
            "available": bool(item_times),
        },
        {
            "step": "2. After stackable batching",
            "detail": "Task times after identical stackable items are grouped",
            "minutes": task_sum if task_debug else None,
            "available": bool(task_debug),
        },
        {
            "step": "3. Task labor sum",
            "detail": "Sum of task combined times used as total labor input",
            "minutes": algo.get("totalLaborMinutes"),
            "available": algo.get("totalLaborMinutes") is not None,
        },
        {
            "step": "4. Shared crew work",
            "detail": (
                f"{format_debug_minutes(algo.get('movers'))} movers, "
                f"{format_debug_minutes(algo.get('effectiveTeams'))} effective teams, "
                f"bottleneck ×{format_debug_minutes(algo.get('bottleneckFactor'))}"
            ),
            "minutes": algo.get("parallelBaseMinutes"),
            "available": algo.get("parallelBaseMinutes") is not None,
        },
        {
            "step": "5. After stairs friction",
            "detail": f"Stair multiplier ×{format_debug_minutes(algo.get('stairFrictionMultiplier'))}",
            "minutes": algo.get("minutesAfterStairs"),
            "available": algo.get("minutesAfterStairs") is not None,
        },
        {
            "step": "6. Elevator adder",
            "detail": (
                f"Pickup {format_debug_minutes(algo.get('elevatorMinutesPickup'))} min + "
                f"dropoff {format_debug_minutes(algo.get('elevatorMinutesDropoff'))} min"
            ),
            "minutes": algo.get("elevatorMinutesTotal"),
            "available": algo.get("elevatorMinutesTotal") is not None,
        },
        {
            "step": "7. Final job labor",
            "detail": "Labor time before travel split (load/unload allocation happens next)",
            "minutes": algo.get("jobLaborMinutes") or access.get("jobLaborMinutes"),
            "available": (algo.get("jobLaborMinutes") or access.get("jobLaborMinutes")) is not None,
        },
    ]

    return {
        "item_rows": item_rows,
        "task_debug": task_debug,
        "raw_item_sum": raw_item_sum,
        "task_sum": task_sum,
        "batching_savings": batching_savings,
        "labor_steps": labor_steps,
        "final_labor": algo.get("jobLaborMinutes") or access.get("jobLaborMinutes"),
        "algo": algo,
    }


def _render_item_breakdown_time_totals_summary(
    totals: Dict[str, Any],
    *,
    widget_key_prefix: str = "",
    key_suffix: str = "breakdown",
) -> None:
    """Compact totals block: minutes on line 1, hr/min on line 2."""
    st.markdown("**Item time totals**")
    cols = st.columns(4)
    for col, label in zip(cols, ("Base", "Load", "Unload", "Total")):
        with col:
            minutes_line, hours_line = format_item_time_total_lines(totals.get(label))
            st.markdown(f"**{label}**")
            st.markdown(minutes_line)
            if hours_line:
                st.markdown(hours_line)


def _render_total_block(label: str, minutes_value: Any) -> None:
    st.markdown(f"**{label}**")
    minutes_line, hours_line = format_total_minutes_two_lines(minutes_value)
    st.markdown(minutes_line)
    if hours_line:
        st.markdown(hours_line)


def _sum_column(rows: List[Dict[str, Any]], key: str) -> float:
    return sum(_safe_float(row.get(key)) for row in rows)


def render_labor_time_flow_section(
    calculations: Dict[str, Any],
    comparison_meta: Optional[Dict[str, Any]] = None,
    *,
    section_title: str,
    widget_key_prefix: str = "",
) -> None:
    """Render full labor-time trace from spreadsheet/JSON debug data."""
    debug = calculations.get("calculationDebug")
    if not debug:
        st.info("Labor time flow is available after a calculation with debug data.")
        return

    model = extract_labor_flow_model(calculations)
    meta = comparison_meta or {}
    source_type = meta.get("source_type", "Unknown")
    db_name = meta.get("database_filename", "Unknown")
    category_count = meta.get("category_count", "Not available")

    st.markdown(f"## {section_title}")
    st.caption(
        "Trace how catalog base times become item totals, task totals, and final labor time. "
        "Values come from the existing calculator debug output."
    )

    st.markdown(
        "| Label | Value |\n| --- | --- |\n"
        f"| Source | {source_type} |\n"
        f"| Database | {db_name} |\n"
        f"| Category count | {category_count} |"
    )
    st.markdown("---")

    st.markdown("### Item times from catalog")
    st.caption(
        "Base time is from the database. Load includes disassembly adders when applicable. "
        "Unload is added using the catalog unload ratio (unused CSV unloadMultiplier is not activated)."
    )

    item_rows = model["item_rows"]
    if not item_rows:
        st.warning("No item time rows available.")
    else:
        table_rows = []
        for row in item_rows:
            table_rows.append({
                "Item": row["name"],
                "Category": row["category"],
                "Size": row["size"],
                "Qty": row["qty"],
                "Base (min)": format_item_time_value(row["base_time"]),
                "Load (min)": format_item_time_value(row["load_time"]),
                "Unload (min)": format_item_time_value(row["unload_time"]),
                "Unload added": "Yes" if row["unload_added"] else "No",
                "Item Total (min)": format_item_time_value(row["item_total"]),
                "Raw Total (min)": format_item_time_value(row["raw_total"]),
                "Stackable": "Yes" if row["stackable"] else "No",
                "Savings %": (
                    format_debug_minutes(row["savings_pct"])
                    if row.get("savings_pct") not in (None, "", 0, 0.0)
                    else "—"
                ),
                "Stackable Savings (min)": format_debug_minutes(row["stackable_savings"]),
                "Adjusted Item Total (min)": format_debug_minutes(row["adjusted_total"]),
            })

        df_kwargs = {"use_container_width": True, "hide_index": True}
        if widget_key_prefix:
            df_kwargs["key"] = f"{widget_key_prefix}labor_flow_item_table"
        st.dataframe(pd.DataFrame(table_rows), **df_kwargs)

        _render_item_breakdown_time_totals_summary(
            {
                "Base": sum(_safe_float(r["base_time"]) * r["qty"] for r in item_rows),
                "Load": sum(_safe_float(r["load_time"]) * r["qty"] for r in item_rows),
                "Unload": sum(_safe_float(r["unload_time"]) * r["qty"] for r in item_rows),
                "Total": model["raw_item_sum"],
            },
            widget_key_prefix=widget_key_prefix,
            key_suffix="item_flow",
        )

    st.markdown("---")
    st.markdown("### Task layer after stackable batching")
    task_debug = model["task_debug"]
    if not task_debug:
        st.caption("Not available — no task debug rows.")
    else:
        if model["batching_savings"] > 0:
            st.info(
                f"Stackable batching saved {format_debug_minutes(model['batching_savings'])} min "
                f"({format_debug_minutes(model['raw_item_sum'])} → "
                f"{format_debug_minutes(model['task_sum'])})."
            )
        task_rows = []
        for task in task_debug:
            task_rows.append({
                "Task": task.get("taskName", "Unknown"),
                "Qty": task.get("taskQuantity", 1),
                "Load (min)": format_item_time_value(task.get("taskLoadTime")),
                "Unload (min)": format_item_time_value(task.get("taskUnloadTime")),
                "Combined (min)": format_item_time_value(task.get("taskCombinedTime")),
                "Stackable": "Yes" if task.get("isStackable") else "No",
                "Batching applied": "Yes" if task.get("batchingApplied") else "No",
                "Savings %": (
                    format_debug_minutes(task.get("stackableSavings"))
                    if task.get("stackableSavings") not in (None, "", 0, 0.0)
                    else "—"
                ),
            })
        task_df_kwargs = {"use_container_width": True, "hide_index": True}
        if widget_key_prefix:
            task_df_kwargs["key"] = f"{widget_key_prefix}labor_flow_task_table"
        st.dataframe(pd.DataFrame(task_rows), **task_df_kwargs)
        _render_total_block("Total task time (labor input)", model["task_sum"])

    st.markdown("---")
    st.markdown("### Labor adjustments after item totals")
    st.caption("Crew sharing, stairs friction, and elevator minutes applied to task labor sum.")

    step_rows = []
    for step in model["labor_steps"]:
        minutes = step["minutes"]
        step_rows.append({
            "Step": step["step"],
            "Detail": step["detail"],
            "Minutes": format_debug_minutes(minutes) if step["available"] else "Not available",
        })
    step_df_kwargs = {"use_container_width": True, "hide_index": True}
    if widget_key_prefix:
        step_df_kwargs["key"] = f"{widget_key_prefix}labor_flow_steps_table"
    st.dataframe(pd.DataFrame(step_rows), **step_df_kwargs)

    st.markdown("---")
    st.markdown("### Final labor time")
    _render_total_block("Final job labor time", model["final_labor"])

    algo = model.get("algo") or {}
    load_split = algo.get("baseLoadMinutes")
    unload_split = algo.get("baseUnloadMinutes")
    if load_split is not None or unload_split is not None:
        st.caption(
            "Load/unload split used for loading/unloading display totals "
            f"(load {format_debug_minutes(load_split)} min, "
            f"unload {format_debug_minutes(unload_split)} min)."
        )


def _keyed_expander(
    label: str,
    *,
    widget_key_prefix: str = "",
    key_name: str,
    expanded: bool = False,
):
    """Expander with optional source-prefixed Streamlit key."""
    kwargs = {"expanded": expanded}
    if widget_key_prefix:
        kwargs["key"] = f"{widget_key_prefix}{key_name}"
    return st.expander(label, **kwargs)


def _fmt_min_cell(value: Any) -> str:
    """Format a minute value for bridge tables."""
    if value is None or value == "" or value == "N/A":
        return "Not available"
    formatted = format_debug_minutes(value)
    if formatted == "Not available":
        return formatted
    return f"{formatted} min"


def extract_labor_bridge_model(
    calculations: Dict[str, Any],
    comparison_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact bridge model: item totals → labor → travel → billable."""
    debug = calculations.get("calculationDebug") or {}
    item_times = debug.get("itemTimes") or []
    task_debug = debug.get("taskDebug") or []
    pricing_dbg = debug.get("pricing") or {}
    catalog = debug.get("catalog") or {}
    access = debug.get("access") or {}
    algo = calculations.get("time", {}).get("algorithmBreakdown") or {}
    time_info = calculations.get("time") or {}

    flow = extract_labor_flow_model(calculations)

    raw_load = sum(
        _safe_float(it.get("loadTime")) * int(it.get("quantity", 1)) for it in item_times
    ) if item_times else None
    raw_unload = sum(
        _safe_float(it.get("unloadTime")) * int(it.get("quantity", 1)) for it in item_times
    ) if item_times else None
    raw_item_total = flow["raw_item_sum"] if item_times else None
    batching_savings = flow["batching_savings"] if task_debug else None
    post_batch_total = flow["task_sum"] if task_debug else None

    meta = comparison_meta or {}
    source_type = meta.get("source_type")
    if not source_type:
        source_type = "Not available"
    db_filename = meta.get("database_filename") or catalog.get("filename") or "Not available"
    category_count = meta.get("category_count")
    if category_count is None:
        category_count = catalog.get("categoryCount", "Not available")

    total_labor = algo.get("totalLaborMinutes")
    parallel_base = algo.get("parallelBaseMinutes")
    after_stairs = algo.get("minutesAfterStairs")
    elevator_total = algo.get("elevatorMinutesTotal")
    final_labor = algo.get("jobLaborMinutes") or access.get("jobLaborMinutes") or pricing_dbg.get("laborMinutes")

    pre_move = pricing_dbg.get("preMoveTravel")
    if pre_move is None:
        pre_move = algo.get("preMoveTravel")
    travel_between = pricing_dbg.get("travelTime")
    if travel_between is None:
        travel_between = algo.get("travelBetweenLocations")

    travel_minutes = None
    if pre_move is not None and travel_between is not None:
        travel_minutes = _safe_float(pre_move) + _safe_float(travel_between)

    total_billable = pricing_dbg.get("totalTimeMinutes")
    if total_billable is None:
        total_billable = time_info.get("totalMinutes")
    if total_billable is None:
        total_billable = algo.get("totalMinutes")

    chain_steps = [
        {
            "stage": "Raw item total before batching",
            "minutes": raw_item_total,
            "note": f"Load {_fmt_min_cell(raw_load)}, unload {_fmt_min_cell(raw_unload)}",
        },
        {
            "stage": "Stackable / batching adjustment",
            "minutes": batching_savings,
            "note": (
                f"Saves {_fmt_min_cell(batching_savings)}"
                if batching_savings and batching_savings > 0
                else "No batching savings"
            ),
            "show_as_savings": True,
        },
        {
            "stage": "Post-batching task total",
            "minutes": post_batch_total,
            "note": "Sum of taskDebug combined times",
        },
        {
            "stage": "totalLaborMinutes",
            "minutes": total_labor,
            "note": "Task labor sum input to crew model",
        },
        {
            "stage": "parallelBaseMinutes",
            "minutes": parallel_base,
            "note": "After crew sharing / bottleneck",
        },
        {
            "stage": "minutesAfterStairs",
            "minutes": after_stairs,
            "note": f"Stair multiplier ×{format_debug_minutes(algo.get('stairFrictionMultiplier'))}",
        },
        {
            "stage": "elevatorMinutesTotal",
            "minutes": elevator_total,
            "note": "Elevator trip adder (not proportional)",
        },
        {
            "stage": "Final labor minutes (jobLaborMinutes)",
            "minutes": final_labor,
            "note": "Labor before travel adders",
        },
        {
            "stage": "Travel minutes",
            "minutes": travel_minutes,
            "note": (
                f"Pre-move {_fmt_min_cell(pre_move)} + "
                f"between locations {_fmt_min_cell(travel_between)}"
            ),
        },
        {
            "stage": "Total billable minutes",
            "minutes": total_billable,
            "note": "Final labor + travel",
        },
    ]

    return {
        "source_type": source_type,
        "database_filename": db_filename,
        "category_count": category_count,
        "raw_load": raw_load,
        "raw_unload": raw_unload,
        "raw_item_total": raw_item_total,
        "batching_savings": batching_savings,
        "post_batch_total": post_batch_total,
        "total_labor": total_labor,
        "parallel_base": parallel_base,
        "after_stairs": after_stairs,
        "elevator_total": elevator_total,
        "final_labor": final_labor,
        "travel_minutes": travel_minutes,
        "total_billable": total_billable,
        "chain_steps": chain_steps,
    }


def render_labor_time_bridge_section(
    calculations: Dict[str, Any],
    comparison_meta: Optional[Dict[str, Any]] = None,
    *,
    widget_key_prefix: str = "",
) -> None:
    """Compact Debug Panel bridge from item totals to labor and billable time."""
    if not calculations.get("calculationDebug"):
        return

    model = extract_labor_bridge_model(calculations, comparison_meta)

    with _keyed_expander(
        "Item totals → Labor time bridge",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_labor_bridge",
        expanded=True,
    ):
        st.caption(
            "How item minutes become task labor, crew-adjusted labor, travel, and total billable time. "
            "Values are read from calculationDebug and algorithmBreakdown only."
        )

        st.markdown(
            "| Field | Value |\n| --- | --- |\n"
            f"| Source type | {model['source_type']} |\n"
            f"| Database filename | {model['database_filename']} |\n"
            f"| Category count | {model['category_count']} |\n"
            f"| Raw item load total (before batching) | {_fmt_min_cell(model['raw_load'])} |\n"
            f"| Raw item unload total (before batching) | {_fmt_min_cell(model['raw_unload'])} |\n"
            f"| Raw item total (before batching) | {_fmt_min_cell(model['raw_item_total'])} |\n"
            f"| Stackable / batching savings | {_fmt_min_cell(model['batching_savings'])} |\n"
            f"| Post-batching task total | {_fmt_min_cell(model['post_batch_total'])} |\n"
            f"| totalLaborMinutes | {_fmt_min_cell(model['total_labor'])} |\n"
            f"| parallelBaseMinutes | {_fmt_min_cell(model['parallel_base'])} |\n"
            f"| minutesAfterStairs | {_fmt_min_cell(model['after_stairs'])} |\n"
            f"| elevatorMinutesTotal | {_fmt_min_cell(model['elevator_total'])} |\n"
            f"| Final labor minutes | {_fmt_min_cell(model['final_labor'])} |\n"
            f"| Travel minutes | {_fmt_min_cell(model['travel_minutes'])} |\n"
            f"| Total billable minutes | {_fmt_min_cell(model['total_billable'])} |"
        )

        st.markdown("**Labor time chain**")
        chain_rows = []
        for step in model["chain_steps"]:
            minutes = step["minutes"]
            if minutes is None:
                display_min = "Not available"
            elif step.get("show_as_savings"):
                savings = _safe_float(minutes)
                display_min = f"−{_fmt_min_cell(savings)}" if savings > 0 else "0 min"
            else:
                display_min = _fmt_min_cell(minutes)
            chain_rows.append({
                "Stage": step["stage"],
                "Minutes": display_min,
                "Detail": step.get("note", ""),
            })

        chain_df_kwargs = {"use_container_width": True, "hide_index": True}
        if widget_key_prefix:
            chain_df_kwargs["key"] = f"{widget_key_prefix}labor_bridge_chain_df"
        st.dataframe(pd.DataFrame(chain_rows), **chain_df_kwargs)

        st.markdown("**Key totals**")
        col1, col2, col3 = st.columns(3)
        with col1:
            _render_total_block("Raw item total (before batching)", model["raw_item_total"])
        with col2:
            _render_total_block("Final labor minutes", model["final_labor"])
        with col3:
            _render_total_block("Total billable minutes", model["total_billable"])
