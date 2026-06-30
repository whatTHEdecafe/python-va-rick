"""
Comparison engine: normalize, compare, and build comparison data structures.

Pure data logic only — no Streamlit, no side effects, no database writes.
All functions accept pre-loaded result dicts and return plain Python dicts/lists.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tolerance used for CLOSE comparison of numeric values (5 % relative)
# ---------------------------------------------------------------------------
_CLOSE_TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Unicode / typography normalization tables
# ---------------------------------------------------------------------------

# Various dash and minus characters → ASCII hyphen
_DASH_MAP = {
    "\u2013": "-",   # en dash
    "\u2014": "-",   # em dash
    "\u2212": "-",   # minus sign
    "\u2015": "-",   # horizontal bar
    "\u2010": "-",   # hyphen (Unicode)
    "\u2011": "-",   # non-breaking hyphen
    "\ufe58": "-",   # small em dash
    "\ufe63": "-",   # small hyphen-minus
    "\uff0d": "-",   # fullwidth hyphen-minus
}

# Smart / curly quotes → straight ASCII equivalents
_QUOTE_MAP = {
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark
    "\u201a": "'",   # single low-9 quotation mark
    "\u201b": "'",   # single high-reversed-9 quotation mark
    "\u02bc": "'",   # modifier letter apostrophe
    "\u2032": "'",   # prime
    "\u2035": "'",   # reversed prime
    "\u201c": '"',   # left double quotation mark
    "\u201d": '"',   # right double quotation mark
    "\u201e": '"',   # double low-9 quotation mark
    "\u201f": '"',   # double high-reversed-9 quotation mark
    "\u2033": '"',   # double prime
    "\u2036": '"',   # reversed double prime
}

# Pre-compiled pattern: spaces around a hyphen → bare hyphen ("16' - 20'" → "16'-20'")
_SPACED_HYPHEN_RE = re.compile(r"\s*-\s*")
# Collapse runs of spaces
_MULTI_SPACE_RE = re.compile(r" {2,}")


def normalize_value(v: Any) -> str:
    """
    Return a canonical string form of *v* suitable for equality comparison.

    Applied transforms (in order):
    1. None / float short-circuit
    2. NFC unicode normalization
    3. Dash characters → ASCII hyphen
    4. Smart/curly quotes → ASCII straight quotes
    5. Spaces around hyphens removed ("16' - 20'" → "16'-20'")
    6. Repeated spaces collapsed
    7. Strip + lowercase
    """
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    if not isinstance(v, str):
        v = str(v)
    v = unicodedata.normalize("NFC", v)
    for ch, repl in _DASH_MAP.items():
        v = v.replace(ch, repl)
    for ch, repl in _QUOTE_MAP.items():
        v = v.replace(ch, repl)
    v = _SPACED_HYPHEN_RE.sub("-", v)
    v = _MULTI_SPACE_RE.sub(" ", v)
    return v.strip().lower()


# ---------------------------------------------------------------------------
# Difference status
# ---------------------------------------------------------------------------

def build_difference_status(values: List[Any]) -> str:
    """
    Given a list of values (one per selected source, ``None`` = missing),
    return one of: ``"SAME"``, ``"CLOSE"``, ``"DIFFERENT"``, ``"MISSING"``.
    """
    present = [v for v in values if v is not None and str(v).strip() != ""]
    if not present:
        return "MISSING"

    normalized = [normalize_value(v) for v in present]

    if len(set(normalized)) == 1 and len(present) == len(values):
        return "SAME"

    if len(set(normalized)) == 1:
        # Values that are present all match, but some sources are missing
        return "MISSING"

    floats = [_to_float(v) for v in present]
    if all(f is not None for f in floats):
        base = floats[0]
        if base == 0.0:
            if all(f == 0.0 for f in floats):
                return "SAME" if len(present) == len(values) else "MISSING"
            return "DIFFERENT"
        if all(abs(f - base) / abs(base) <= _CLOSE_TOLERANCE for f in floats[1:]):
            return "CLOSE" if len(present) == len(values) else "MISSING"

    if len(present) < len(values):
        return "MISSING"
    return "DIFFERENT"


def compare_values(values: Dict[str, Any]) -> str:
    """Convenience wrapper — *values* is ``{source_label: value}``."""
    return build_difference_status(list(values.values()))


# ---------------------------------------------------------------------------
# Value formatting helpers (no Streamlit)
# ---------------------------------------------------------------------------

def _fmt_money(v: Any) -> str:
    if v is None:
        return "N/A"
    f = _to_float(v)
    return f"${f:.2f}" if f is not None else str(v)


def _fmt_float2(v: Any) -> str:
    if v is None:
        return "N/A"
    f = _to_float(v)
    return f"{f:.2f}" if f is not None else str(v)


def _fmt_int(v: Any) -> str:
    if v is None:
        return "N/A"
    f = _to_float(v)
    return str(int(f)) if f is not None else str(v)


def _fmt_vehicles(v: Any) -> str:
    if not v:
        return "N/A"
    if isinstance(v, list):
        parts = [
            f"{veh.get('quantity', 1)}x {veh.get('title', 'Unknown')}"
            for veh in v
        ]
        return ", ".join(parts) if parts else "N/A"
    return str(v)


def _format_value(v: Any, fmt: str) -> str:
    if fmt == "money":
        return _fmt_money(v)
    if fmt == "float2":
        return _fmt_float2(v)
    if fmt == "int":
        return _fmt_int(v)
    if fmt == "vehicles":
        return _fmt_vehicles(v)
    if v is None:
        return "N/A"
    return str(v)


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _safe_get(obj: Any, *keys: str) -> Any:
    """Nested dict traversal that returns ``None`` on any miss."""
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _get_from_result(result: Dict[str, Any], *path: str) -> Any:
    """
    Get a value from a result bundle using a path.

    Top-level keys resolved against ``result["calculations"]`` unless the
    first key is ``"summary"`` or ``"metrics"`` (resolved against result root).
    """
    if not result or result.get("error"):
        return None
    root_keys = ("summary", "metrics", "comparison_meta")
    if path and path[0] in root_keys:
        return _safe_get(result, *path)
    calc = result.get("calculations") or {}
    return _safe_get(calc, *path)


# ---------------------------------------------------------------------------
# Summary comparison
# ---------------------------------------------------------------------------

# Each entry: label, path tuple (relative to calculations), format, optional note
_SUMMARY_FIELDS: List[Dict[str, Any]] = [
    {
        "label": "Total Price (min)",
        "path": ("pricing", "totalExpectedPriceMin"),
        "fmt": "money",
        "note": "Minimum expected total price (incl. GST)",
    },
    {
        "label": "Total Price (max)",
        "path": ("pricing", "totalExpectedPriceMax"),
        "fmt": "money",
        "note": "Maximum expected total price (incl. GST)",
    },
    {
        "label": "Final Total",
        "path": ("calculationDebug", "pricing", "finalTotalExpectedPrice"),
        "fmt": "money",
        "note": "Single expected price used in quote",
    },
    {
        "label": "Total Time (hrs)",
        "path": ("time", "totalHours"),
        "fmt": "float2",
        "note": "Total billable time in hours",
    },
    {
        "label": "Total Time (min)",
        "path": ("calculationDebug", "pricing", "totalTimeMinutes"),
        "fmt": "int",
        "note": "Total billable time in minutes",
    },
    {
        "label": "Labor Time (min)",
        "path": ("calculationDebug", "pricing", "laborMinutes"),
        "fmt": "int",
        "note": "Labor minutes (loading + unloading + stairs/elevator)",
    },
    {
        "label": "Loading Time (min)",
        "path": ("time", "loadingTime"),
        "fmt": "int",
        "note": "Time to load items",
    },
    {
        "label": "Unloading Time (min)",
        "path": ("time", "unloadingTime"),
        "fmt": "int",
        "note": "Time to unload items",
    },
    {
        "label": "Travel Time (min)",
        "path": ("time", "travelBetweenLocations"),
        "fmt": "int",
        "note": "Drive time between locations",
    },
    {
        "label": "Pre-Move Travel (min)",
        "path": ("time", "preMoveTravel"),
        "fmt": "int",
        "note": "Fixed pre-move travel time",
    },
    {
        "label": "Movers / Crew",
        "path": ("material", "numberOfWorkers"),
        "fmt": "int",
        "note": "Number of movers on the job",
    },
    {
        "label": "Vehicle",
        "path": ("material", "vehicles"),
        "fmt": "vehicles",
        "note": "Selected truck(s)",
    },
    {
        "label": "Base Price (before GST)",
        "path": ("calculationDebug", "pricing", "basePriceBeforeGst"),
        "fmt": "money",
        "note": "Base price before tax",
    },
    {
        "label": "GST Amount",
        "path": ("calculationDebug", "pricing", "gstAmount"),
        "fmt": "money",
        "note": "GST (5%)",
    },
    {
        "label": "Wage Rate ($/hr/mover)",
        "path": ("calculationDebug", "pricing", "wageRatePerHourPerMover"),
        "fmt": "money",
        "note": "Hourly rate per mover",
    },
    {
        "label": "Wage Rate ($/min/mover)",
        "path": ("calculationDebug", "pricing", "wageRatePerMinute"),
        "fmt": "money",
        "note": "Per-minute rate per mover",
    },
    {
        "label": "Min Hours",
        "path": ("calculationDebug", "pricing", "minHours"),
        "fmt": "float2",
        "note": "Minimum billable hours",
    },
    {
        "label": "Max Hours",
        "path": ("calculationDebug", "pricing", "maxHours"),
        "fmt": "float2",
        "note": "Maximum billable hours",
    },
]

# Subset shown in the high-level summary (first section)
_SUMMARY_TOP_LABELS = {
    "Total Price (min)",
    "Total Price (max)",
    "Total Time (hrs)",
    "Labor Time (min)",
    "Travel Time (min)",
    "Movers / Crew",
    "Vehicle",
    "Base Price (before GST)",
    "GST Amount",
}


# Formats where comparison should use the *formatted display string*, not the
# raw Python value.  For "vehicles" the raw value is a list of dicts whose
# non-display fields (utilisation %, vehicleId, …) may differ between sources
# even when the displayed truck string is identical.  For "str" the raw value
# is already a string but may contain unicode typography that looks the same
# on screen but compares unequal byte-by-byte.
_STRING_COMPARE_FORMATS = frozenset({"str", "vehicles"})


def _build_summary_rows(
    source_results: Dict[str, Dict[str, Any]],
    fields: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for field in fields:
        label = field["label"]
        fmt = field["fmt"]
        path = field["path"]
        note = field.get("note", "")

        raw_vals: Dict[str, Any] = {}
        for src_label, result in source_results.items():
            raw_vals[src_label] = _get_from_result(result, *path)

        formatted_vals = {
            src: _format_value(v, fmt) for src, v in raw_vals.items()
        }

        # For string-like formats compare using the formatted display strings so
        # that visually identical values (e.g. vehicle titles with different dash
        # characters or hidden extra fields in the raw list) are treated as SAME.
        if fmt in _STRING_COMPARE_FORMATS:
            compare_vals: List[Any] = [
                None if fv == "N/A" else fv
                for fv in formatted_vals.values()
            ]
        else:
            compare_vals = list(raw_vals.values())

        status = build_difference_status(compare_vals)

        rows.append(
            {
                "label": label,
                "values": formatted_vals,
                "raw_values": raw_vals,
                "status": status,
                "note": note,
            }
        )
    return rows


def build_summary_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Return (top_rows, detail_rows) where:
    - top_rows   — high-level summary fields (fast scan)
    - detail_rows — all fields (for the collapsible details section)
    """
    all_rows = _build_summary_rows(source_results, _SUMMARY_FIELDS)
    top_rows = [r for r in all_rows if r["label"] in _SUMMARY_TOP_LABELS]
    return top_rows, all_rows


# ---------------------------------------------------------------------------
# Warnings comparison
# ---------------------------------------------------------------------------

def build_warnings_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Return {source_label: [warning_str, ...]} for each source."""
    result = {}
    for src_label, res in source_results.items():
        if res.get("error"):
            result[src_label] = [f"Source error: {res['error']}"]
        else:
            warnings = _get_from_result(res, "calculationDebug", "warnings") or []
            result[src_label] = [str(w) for w in warnings]
    return result


# ---------------------------------------------------------------------------
# Item comparison
# ---------------------------------------------------------------------------

def _normalize_item_name(name: str) -> str:
    return str(name).strip().lower()


def _get_calc_items(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the items list from calculations.items."""
    if not result or result.get("error"):
        return []
    return (result.get("calculations") or {}).get("items") or []


def _get_debug_matching(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return calculationDebug.matching for detailed per-item info."""
    if not result or result.get("error"):
        return []
    debug = (result.get("calculations") or {}).get("calculationDebug") or {}
    return debug.get("matching") or []


def _get_debug_item_times(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return calculationDebug.itemTimes for detailed per-item timing."""
    if not result or result.get("error"):
        return []
    debug = (result.get("calculations") or {}).get("calculationDebug") or {}
    return debug.get("itemTimes") or []


def build_item_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build a list of item comparison rows, one per unique item name.

    Each row::

        {
            "name": str,                   # display name
            "quantity": int | None,
            "source_items": {src: item_dict | None},   # from calculations.items
            "source_details": {src: {match, time}},   # from calculationDebug
            "status": str,                 # SAME / CLOSE / DIFFERENT / MISSING
        }
    """
    # Collect all item names and per-source item maps
    all_names: Dict[str, str] = {}  # norm_name -> display_name
    src_item_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    src_match_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    src_time_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for src_label, result in source_results.items():
        src_item_maps[src_label] = {}
        src_match_maps[src_label] = {}
        src_time_maps[src_label] = {}

        items = _get_calc_items(result)
        for item in items:
            raw_name = item.get("name") or "Unknown"
            norm = _normalize_item_name(raw_name)
            if norm not in all_names:
                all_names[norm] = raw_name
            src_item_maps[src_label][norm] = item

        matching = _get_debug_matching(result)
        item_times = _get_debug_item_times(result)
        for idx, m in enumerate(matching):
            raw_name = m.get("inputName") or m.get("name") or "Unknown"
            norm = _normalize_item_name(raw_name)
            if norm not in all_names:
                all_names[norm] = raw_name
            src_match_maps[src_label][norm] = m
            it = item_times[idx] if idx < len(item_times) else {}
            src_time_maps[src_label][norm] = it

    rows: List[Dict[str, Any]] = []
    for norm_name, display_name in sorted(all_names.items()):
        source_items: Dict[str, Optional[Dict[str, Any]]] = {}
        source_details: Dict[str, Dict[str, Any]] = {}

        for src_label in source_results:
            source_items[src_label] = src_item_maps[src_label].get(norm_name)
            source_details[src_label] = {
                "match": src_match_maps[src_label].get(norm_name),
                "time": src_time_maps[src_label].get(norm_name),
            }

        labor_vals = [
            (item.get("totalTime") if item else None)
            for item in source_items.values()
        ]
        status = build_difference_status(labor_vals)

        qty: Optional[int] = None
        for item in source_items.values():
            if item is not None:
                qty = item.get("quantity", 1)
                break

        rows.append(
            {
                "name": display_name,
                "quantity": qty,
                "source_items": source_items,
                "source_details": source_details,
                "status": status,
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Fees/rates comparison
# ---------------------------------------------------------------------------

_FEES_FIELDS: List[Dict[str, Any]] = [
    {
        "label": "Service Fee",
        "path": ("calculationDebug", "pricing", "serviceFee"),
        "fmt": "money",
    },
    {
        "label": "Transfer Fee",
        "path": ("calculationDebug", "pricing", "transferFee"),
        "fmt": "money",
    },
    {
        "label": "Business Fee",
        "path": ("calculationDebug", "pricing", "businessFee"),
        "fmt": "money",
    },
    {
        "label": "Pricing Breakdown",
        "path": ("calculationDebug", "pricing", "pricingBreakdown"),
        "fmt": "str",
    },
    {
        "label": "Catalog Filename",
        "path": ("calculationDebug", "catalog", "filename"),
        "fmt": "str",
    },
    {
        "label": "Category Count",
        "path": ("calculationDebug", "catalog", "categoryCount"),
        "fmt": "int",
    },
]


def build_fees_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _build_summary_rows(source_results, _FEES_FIELDS)


# ---------------------------------------------------------------------------
# Vehicle / crew comparison
# ---------------------------------------------------------------------------

_VEHICLE_FIELDS: List[Dict[str, Any]] = [
    {
        "label": "Vehicle Title",
        "path": ("calculationDebug", "vehicle", "vehicleTitle"),
        "fmt": "str",
    },
    {
        "label": "Vehicle Quantity",
        "path": ("calculationDebug", "vehicle", "quantity"),
        "fmt": "int",
    },
    {
        "label": "Volume Utilization (%)",
        "path": ("calculationDebug", "vehicle", "volumeUtilization"),
        "fmt": "float2",
    },
    {
        "label": "Weight Utilization (%)",
        "path": ("calculationDebug", "vehicle", "weightUtilization"),
        "fmt": "float2",
    },
    {
        "label": "Final Movers Used",
        "path": ("calculationDebug", "crew", "finalMoversUsed"),
        "fmt": "int",
    },
    {
        "label": "Recommended Movers",
        "path": ("calculationDebug", "crew", "autoRecommendedMovers"),
        "fmt": "int",
    },
    {
        "label": "Baseline 2-Mover Time (min)",
        "path": ("calculationDebug", "crew", "baseline2MoverTimeMinutes"),
        "fmt": "float2",
    },
    {
        "label": "Small Job Flag",
        "path": ("calculationDebug", "crew", "smallJobFlag"),
        "fmt": "str",
    },
]


def build_vehicle_crew_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _build_summary_rows(source_results, _VEHICLE_FIELDS)


# ---------------------------------------------------------------------------
# Labor time breakdown comparison
# ---------------------------------------------------------------------------

_LABOR_FIELDS: List[Dict[str, Any]] = [
    {
        "label": "Labor Minutes",
        "path": ("calculationDebug", "pricing", "laborMinutes"),
        "fmt": "int",
        "note": "Total labor time (loading + unloading + adjustments)",
    },
    {
        "label": "Loading Time (min)",
        "path": ("time", "loadingTime"),
        "fmt": "int",
    },
    {
        "label": "Unloading Time (min)",
        "path": ("time", "unloadingTime"),
        "fmt": "int",
    },
    {
        "label": "Stairs/Elevator Adjustment (min)",
        "path": ("calculationDebug", "access", "stairsElevatorAdjustmentMinutes"),
        "fmt": "float2",
    },
    {
        "label": "Effective Teams",
        "path": ("calculationDebug", "access", "effectiveTeams"),
        "fmt": "float2",
    },
    {
        "label": "Bottleneck Factor",
        "path": ("calculationDebug", "access", "bottleneckFactor"),
        "fmt": "float2",
    },
    {
        "label": "Job Labor Minutes",
        "path": ("calculationDebug", "access", "jobLaborMinutes"),
        "fmt": "float2",
    },
]


def build_labor_comparison(
    source_results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _build_summary_rows(source_results, _LABOR_FIELDS)
