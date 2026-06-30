"""Time algorithm breakdown flowchart for Streamlit (self-contained HTML, no CDN)."""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

ALGORITHM_NARRATIVE = (
    "Stairs make the whole move take longer (a percent-style bump per floor at pickup and dropoff). "
    "Elevator adds extra minutes for riding and waiting per trip—not as a percent of item time."
)

_FLOWCHART_DOC_PATH = "docs/calculator-algorithm-flowchart.html"
_IFRAME_HEIGHT = 620


def _access_short(access: Dict[str, Any]) -> str:
    kind = (access.get("type") or "ground").lower()
    floors = access.get("floors", 0)
    if kind == "stairs" and floors:
        return f"stairs {floors} fl"
    if kind == "elevator" and floors:
        return f"elevator {floors} fl"
    if kind == "elevator":
        return "elevator"
    if kind == "stairs":
        return "stairs"
    return "ground"


def build_flowchart_step_labels(
    breakdown: Dict[str, Any],
    time_info: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Plain-English step labels with this job's live numbers."""
    time_info = time_info or {}
    num_tasks = breakdown.get("numTasks", 0)
    total_labor = breakdown.get("totalLaborMinutes", 0)
    movers = breakdown.get("movers", 0)
    parallel_base = breakdown.get("parallelBaseMinutes", 0)
    stair_mult = breakdown.get("stairFrictionMultiplier", 1.0)
    after_stairs = breakdown.get("minutesAfterStairs", 0)
    elev_total = breakdown.get("elevatorMinutesTotal", 0)
    job_labor = breakdown.get("jobLaborMinutes", 0)
    loading = breakdown.get(
        "loadingMinutes", time_info.get("loadingTime", 0)
    )
    unloading = breakdown.get(
        "unloadingMinutes", time_info.get("unloadingTime", 0)
    )
    pre_move = breakdown.get(
        "preMoveTravel", time_info.get("preMoveTravel", 0)
    )
    drive = breakdown.get(
        "travelBetweenLocations", time_info.get("travelBetweenLocations", 0)
    )
    total = breakdown.get("totalMinutes", time_info.get("totalMinutes", 0))

    pickup = _access_short(breakdown.get("pickupAccess", {}))
    dropoff = _access_short(breakdown.get("dropoffAccess", {}))
    teams = breakdown.get("effectiveTeams", movers / 2)
    elev_note = " (elevator cap)" if breakdown.get("elevatorCappedTeams") else ""

    steps = [
        f"Sum {num_tasks} items → {total_labor} min labor",
        (
            f"{movers} movers → {parallel_base} min shared work{elev_note} "
            f"({teams} effective teams)"
        ),
        (
            f"Stairs ×{stair_mult} → {after_stairs} min "
            f"(pickup: {pickup}, dropoff: {dropoff})"
        ),
    ]

    if elev_total > 0:
        elev_pickup = breakdown.get("elevatorMinutesPickup", 0)
        elev_drop = breakdown.get("elevatorMinutesDropoff", 0)
        steps.append(
            f"+ elevator {elev_total} min ({elev_pickup} + {elev_drop}) "
            f"→ {job_labor} min job labor"
        )
    else:
        steps.append(f"Job labor → {job_labor} min")

    steps.extend(
        [
            f"Load/unload split → loading {loading} min",
            f"Unloading → {unloading} min",
            f"+ pre-move {pre_move} + drive {drive} → {total} min total",
        ]
    )
    return steps


def build_time_flowchart_mermaid(
    breakdown: Dict[str, Any],
    time_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Mermaid source (kept for docs/tests); Streamlit renders HTML steps instead."""
    steps = build_flowchart_step_labels(breakdown, time_info)
    node_ids = [
        "sumItems",
        "crewShare",
        "stairStep",
        "elevator",
        "jobLabor",
        "loadSplit",
        "unloadSplit",
        "travel",
    ]
    lines = ["flowchart TB"]
    for idx, label in enumerate(steps):
        safe = label.replace('"', "'")
        node_id = node_ids[idx] if idx < len(node_ids) else f"step{idx}"
        lines.append(f'  {node_id}["{safe}"]')
        if idx > 0:
            prev_id = node_ids[idx - 1] if idx - 1 < len(node_ids) else f"step{idx - 1}"
            lines.append(f"  {prev_id} --> {node_id}")
    return "\n".join(lines)


def _flowchart_iframe_html(steps: List[str]) -> str:
    """Self-contained vertical flowchart; works inside Streamlit's sandboxed iframe."""
    step_html = []
    for label in steps:
        step_html.append(
            f'<div class="step"><span class="step-text">{html.escape(label)}</span></div>'
        )
        step_html.append('<div class="arrow" aria-hidden="true">↓</div>')
    if step_html:
        step_html.pop()  # trailing arrow

    steps_markup = "\n".join(step_html)
    narrative = html.escape(ALGORITHM_NARRATIVE)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #ffffff;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      font-size: 15px;
      color: #0f172a;
    }}
    body {{
      padding: 8px 12px 20px;
      box-sizing: border-box;
    }}
    .subtitle {{
      font-size: 14px;
      color: #475569;
      margin: 0 0 16px;
      line-height: 1.45;
      max-width: 72ch;
    }}
    .flow {{
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0;
      width: 100%;
      max-width: 640px;
      margin: 0 auto;
    }}
    .step {{
      width: 100%;
      box-sizing: border-box;
      padding: 12px 14px;
      border: 1.5px solid #94a3b8;
      border-radius: 8px;
      background: #f8fafc;
      text-align: center;
      line-height: 1.4;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    }}
    .step-text {{
      display: inline-block;
      max-width: 58ch;
    }}
    .arrow {{
      color: #64748b;
      font-size: 18px;
      line-height: 1;
      padding: 4px 0;
      user-select: none;
    }}
  </style>
</head>
<body>
  <p class="subtitle">{narrative}</p>
  <div class="flow">
    {steps_markup}
  </div>
</body>
</html>"""


def render_time_algorithm_flowchart(
    steps: List[str],
    height: int = _IFRAME_HEIGHT,
) -> None:
    """Render step flowchart inside an isolated iframe."""
    components.html(_flowchart_iframe_html(steps), height=height, scrolling=True)


def render_time_algorithm_breakdown(
    time_info: Dict[str, Any],
    *,
    height: int = _IFRAME_HEIGHT,
) -> bool:
    """
    Show narrative + flowchart when algorithmBreakdown is present.
    Returns True if rendered, False if fallback was shown.
    """
    breakdown = time_info.get("algorithmBreakdown")
    if not breakdown:
        st.info(
            "Step-by-step time breakdown is available after you run a fresh analysis. "
            f"See [{_FLOWCHART_DOC_PATH}]({_FLOWCHART_DOC_PATH}) for the full algorithm."
        )
        return False

    steps = build_flowchart_step_labels(breakdown, time_info)
    render_time_algorithm_flowchart(steps, height=height)
    return True


def breakdown_step_rows(breakdown: Dict[str, Any]) -> Dict[str, Any]:
    """Flat key/value map for optional step table expander."""
    return {
        "Item labor sum (min)": breakdown.get("totalLaborMinutes"),
        "Tasks": breakdown.get("numTasks"),
        "Movers": breakdown.get("movers"),
        "Effective teams": breakdown.get("effectiveTeams"),
        "Bottleneck factor": breakdown.get("bottleneckFactor"),
        "Shared work after crew (min)": breakdown.get("parallelBaseMinutes"),
        "Stair multiplier": breakdown.get("stairFrictionMultiplier"),
        "After stairs (min)": breakdown.get("minutesAfterStairs"),
        "Elevator pickup (min)": breakdown.get("elevatorMinutesPickup"),
        "Elevator dropoff (min)": breakdown.get("elevatorMinutesDropoff"),
        "Job labor (min)": breakdown.get("jobLaborMinutes"),
        "Load ratio": breakdown.get("loadRatio"),
        "Loading (min)": breakdown.get("loadingMinutes"),
        "Unloading (min)": breakdown.get("unloadingMinutes"),
        "Pre-move travel (min)": breakdown.get("preMoveTravel"),
        "Drive (min)": breakdown.get("travelBetweenLocations"),
        "Total (min)": breakdown.get("totalMinutes"),
    }
