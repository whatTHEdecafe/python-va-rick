"""
batch_test_runner.py — Batch Testing Report feature for Moovez Vision Analyzer.

Processes selected saved moves (no Gemini, no media upload) and writes results
into the batch testing CSV report (Data/test_reports/batch testing result.csv).

Each batch run appends a new 3-column block (JSON | Spreadsheet | Database) to
the right of existing data, with a plain-text date/time label in header row 0.

Matching is by exact file name (move["name"]) vs column B "File name".
"""

from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RUNNER_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_RUNNER_DIR)

REPORT_DIR = os.path.join(_PARENT_DIR, "Data", "test_reports")
BACKUP_DIR = os.path.join(REPORT_DIR, "backups")
REPORT_FILENAME = "batch testing result.csv"
REPORT_PATH = os.path.join(REPORT_DIR, REPORT_FILENAME)
LAST_SELECTION_FILE = os.path.join(REPORT_DIR, "last_batch_selection.json")

# Metric row names in spreadsheet order
METRIC_NAMES = [
    "Total Time",
    "Total Time - Range",
    "Travel Time",
    "Work Time",
    "# of Movers",
    "Price",
    "# of Items",
]
ROWS_PER_JOB = len(METRIC_NAMES)   # 7
HEADER_ROWS = 2                     # rows 0 + 1 (0-indexed)

# CSV fixed column indices
_COL_SECTION = 0   # col A – reserved / section label
_COL_FILENAME = 1  # col B – File name
_COL_METRIC   = 2  # col C – Metric name
_FIRST_DATA_COL = 3  # first dynamic data column

# ---------------------------------------------------------------------------
# Selection persistence
# ---------------------------------------------------------------------------


def load_last_batch_selection() -> List[str]:
    """Return list of previously selected folder IDs, or empty list."""
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        if not os.path.isfile(LAST_SELECTION_FILE):
            return []
        with open(LAST_SELECTION_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("selected_folders", [])
    except Exception:
        return []


def save_last_batch_selection(folder_ids: List[str]) -> None:
    """Persist the current selection of folder IDs."""
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(LAST_SELECTION_FILE, "w", encoding="utf-8") as fh:
            json.dump({"selected_folders": folder_ids}, fh, indent=2)
    except Exception:
        pass


def load_and_clean_batch_selection() -> List[str]:
    """
    Load the last batch selection and silently remove any folder IDs that no
    longer correspond to existing saved moves.

    If stale entries are found they are removed and the cleaned list is
    written back to ``last_batch_selection.json`` so the file stays current.
    This prevents stale-selection warnings from appearing on the very first
    render of the batch UI after a fresh app start.

    Falls back to returning the raw (uncleaned) list if saved-move discovery
    fails for any reason, so the UI's own stale-check can handle it.
    """
    raw = load_last_batch_selection()
    if not raw:
        return []

    try:
        from saved_move_replay import list_saved_moves  # local to avoid circular import
        existing: set = {m["_folder"].strip() for m in list_saved_moves()}
    except Exception:
        return raw  # discovery failed — return as-is, UI will handle it

    cleaned = [fid.strip() for fid in raw if fid.strip() in existing]

    if len(cleaned) != len(raw):
        # Stale entries removed — write the cleaned list back immediately
        save_last_batch_selection(cleaned)

    return cleaned


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_minutes_as_hours_minutes(total_minutes: float) -> str:
    """Convert decimal minutes to 'X hr Y min' or 'Y min' string."""
    if total_minutes is None:
        return ""
    total_min = round(total_minutes)
    if total_min < 60:
        return f"{total_min} min"
    hrs = total_min // 60
    mins = total_min % 60
    if mins == 0:
        return f"{hrs} hr"
    return f"{hrs} hr {mins} min"


def format_decimal_hours_as_hours_minutes(decimal_hours: float) -> str:
    """Convert decimal hours to 'X hr Y min' or 'Y min' string."""
    if decimal_hours is None:
        return ""
    return format_minutes_as_hours_minutes(decimal_hours * 60)


def _parse_range_value(val_str: str) -> Optional[float]:
    """Try to parse a numeric value from a range string like '5.00' or '6.50'."""
    try:
        return float(val_str.strip())
    except (ValueError, AttributeError):
        return None


def format_time_range(range_str: str) -> str:
    """
    Convert range string to readable format.
    Input:  '5.00 - 6.50 hrs' or '5.00 - 6.50'
    Output: '5 hr - 6 hr 30 min'
    """
    if not range_str:
        return ""
    cleaned = range_str.replace("hrs", "").replace("hr", "").strip()
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        lo = _parse_range_value(parts[0])
        hi = _parse_range_value(parts[1])
        if lo is not None and hi is not None:
            return (
                format_decimal_hours_as_hours_minutes(lo)
                + " - "
                + format_decimal_hours_as_hours_minutes(hi)
            )
    return range_str


def format_travel_time(pre_move: int, travel: int) -> str:
    """
    Format travel time as '30 + 15 = 45 min' or '30 + 75 = 1 hr 45 min'.
    """
    total = pre_move + travel
    total_formatted = format_minutes_as_hours_minutes(total)
    return f"{pre_move} + {travel} = {total_formatted}"


def format_price(pricing: Dict[str, Any]) -> str:
    """Format price with optional range."""
    if not pricing:
        return ""
    base = pricing.get("basePrice")
    lo = pricing.get("basePriceMin")
    hi = pricing.get("basePriceMax")
    if base is None:
        return ""
    if lo is not None and hi is not None and abs(hi - lo) > 0.01:
        return f"${lo:,.2f} - ${hi:,.2f}"
    return f"${base:,.2f}"


def count_total_items(enriched_items: List[Dict[str, Any]], logistics_result: Dict[str, Any]) -> int:
    """
    Return total item count from item_details in logistics, or enriched_items quantities.
    Preferred: sum of quantities from logistics['items'] (item breakdown).
    """
    calc_items = (logistics_result or {}).get("items", [])
    if calc_items:
        return sum(int(i.get("quantity", 1)) for i in calc_items)
    if enriched_items:
        return sum(int(i.get("quantity", 1)) for i in enriched_items)
    return 0


# ---------------------------------------------------------------------------
# Extract metrics from a source result bundle
# ---------------------------------------------------------------------------


def extract_metrics_from_bundle(
    bundle: Dict[str, Any],
    logistics_params: Dict[str, Any],
    *,
    warnings: List[str],
    source_label: str,
) -> Dict[str, str]:
    """
    Extract the 7 metric values from a result bundle.
    Returns a dict keyed by METRIC_NAMES.
    Appends to warnings for any missing values.
    """
    if not bundle or bundle.get("error"):
        err = (bundle or {}).get("error", "source unavailable")
        warnings.append(f"{source_label}: {err}")
        return {m: "" for m in METRIC_NAMES}

    calculations = bundle.get("calculations") or {}
    items = bundle.get("items") or []
    time_data = calculations.get("time") or {}
    material = calculations.get("material") or {}
    pricing = calculations.get("pricing") or {}

    total_minutes = time_data.get("totalMinutes")
    pre_move = (logistics_params or {}).get("pre_move_travel", 30)
    travel = (logistics_params or {}).get("travel_time", 30)
    labor_minutes = (total_minutes - pre_move - travel) if total_minutes is not None else None

    if total_minutes is not None:
        total_time_str = format_minutes_as_hours_minutes(total_minutes)
    else:
        total_time_str = ""
        warnings.append(f"{source_label}: totalMinutes missing")

    raw_range = time_data.get("estimatedRange", "")
    if raw_range:
        range_str = format_time_range(str(raw_range))
    else:
        range_str = ""
        warnings.append(f"{source_label}: estimatedRange missing")

    travel_str = format_travel_time(pre_move, travel)

    if labor_minutes is not None:
        work_time_str = format_minutes_as_hours_minutes(labor_minutes)
    else:
        work_time_str = ""
        warnings.append(f"{source_label}: work time could not be computed")

    movers = material.get("numberOfWorkers")
    movers_str = str(movers) if movers is not None else ""
    if not movers_str:
        warnings.append(f"{source_label}: numberOfWorkers missing")

    price_str = format_price(pricing)
    if not price_str:
        warnings.append(f"{source_label}: price missing")

    item_count = count_total_items(items, calculations)
    if item_count > 0:
        items_str = str(item_count)
    else:
        items_str = ""
        warnings.append(f"{source_label}: item count missing (using raw detected_items)")

    return {
        "Total Time": total_time_str,
        "Total Time - Range": range_str,
        "Travel Time": travel_str,
        "Work Time": work_time_str,
        "# of Movers": movers_str,
        "Price": price_str,
        "# of Items": items_str,
    }


# ---------------------------------------------------------------------------
# Run replay for a single saved move (no Gemini, no media upload)
# ---------------------------------------------------------------------------


def run_batch_replay_for_saved_move(
    analyzer,
    saved_move: Dict[str, Any],
    logistics_params: Dict[str, Any],
    *,
    errors: List[str],
    json_db_name: Optional[str] = None,
    spreadsheet_db_name: Optional[str] = None,
    backend_catalog_cache: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Dict[str, str]]]:
    """
    Replay one saved move (no Gemini, no media upload).
    Returns {'JSON': {metric: val}, 'Spreadsheet': {...}, 'Database': {...}}
    or None on total failure.
    """
    move_name = saved_move.get("name", saved_move.get("id", "unknown"))

    vision_result = saved_move.get("vision_result")
    detected_items = saved_move.get("detected_items")
    if not detected_items and vision_result:
        detected_items = [copy.deepcopy(i) for i in vision_result.get("items", [])]
    if not detected_items:
        errors.append(f"Replay failed for '{move_name}': no detected_items in saved move.")
        return None

    detected_items = [copy.deepcopy(i) for i in detected_items]
    lp = logistics_params

    # --- JSON source ---
    try:
        enriched_json = analyzer.enrich_items(detected_items)
        logistics_json = analyzer.compute_logistics(
            enriched_json,
            lp["pickup_access"],
            lp["dropoff_access"],
            lp["travel_time"],
            lp["pre_move_travel"],
            forced_movers=lp.get("forced_movers"),
        )
        if not logistics_json:
            errors.append(f"JSON logistics returned no result for '{move_name}'.")
            json_bundle = {}
        else:
            json_bundle = {"items": enriched_json, "calculations": logistics_json}
    except Exception as exc:
        errors.append(f"JSON replay failed for '{move_name}': {exc}")
        json_bundle = {}

    # --- Spreadsheet + Database sources ---
    try:
        from csv_json_compare_panel import compute_triple_source_results
        _, spreadsheet_bundle, backend_bundle = compute_triple_source_results(
            detected_items,
            logistics_params,
            vision_result,
            metrics=None,
            json_db_name=json_db_name,
            spreadsheet_db_name=spreadsheet_db_name,
            backend_catalog_cache=backend_catalog_cache,
        )
    except Exception as exc:
        errors.append(f"Spreadsheet/Database replay failed for '{move_name}': {exc}")
        spreadsheet_bundle = {"error": str(exc)}
        backend_bundle = {"error": str(exc)}

    warn_list: List[str] = []
    json_metrics = extract_metrics_from_bundle(
        json_bundle, lp, warnings=warn_list, source_label=f"'{move_name}' JSON"
    )
    sheet_metrics = extract_metrics_from_bundle(
        spreadsheet_bundle, lp, warnings=warn_list, source_label=f"'{move_name}' Spreadsheet"
    )
    db_metrics = extract_metrics_from_bundle(
        backend_bundle, lp, warnings=warn_list, source_label=f"'{move_name}' Database"
    )
    errors.extend(warn_list)

    return {
        "JSON": json_metrics,
        "Spreadsheet": sheet_metrics,
        "Database": db_metrics,
    }


# ---------------------------------------------------------------------------
# CSV report helpers
# ---------------------------------------------------------------------------


def find_report_csv() -> Optional[str]:
    """
    Return path to the batch report CSV.
    Prefers Data/test_reports/; falls back to project root.
    """
    if os.path.isfile(REPORT_PATH):
        return REPORT_PATH
    root_path = os.path.join(_PARENT_DIR, REPORT_FILENAME)
    if os.path.isfile(root_path):
        return root_path
    return None


def backup_report_csv(csv_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Create a timestamped backup of the CSV in Data/test_reports/backups/.
    Returns (backup_path, error_message).
    """
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d_%H%M")
        backup_name = f"batch_testing_result_before_{ts}.csv"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(csv_path, backup_path)
        return backup_path, None
    except Exception as exc:
        return None, f"Could not create backup: {exc}"


def _load_csv(path: str) -> List[List[str]]:
    """Load CSV file into a list of rows (list of lists). Returns [] if missing."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return [row for row in csv.reader(fh)]
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="latin-1", newline="") as fh:
                return [row for row in csv.reader(fh)]
        except Exception:
            return []
    except Exception:
        return []


def _save_csv(path: str, rows: List[List[str]]) -> None:
    """Write list-of-lists to a UTF-8 CSV file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)


def _init_empty_csv() -> List[List[str]]:
    """
    Return the two-row header structure for a brand-new CSV report.
    Row 0: batch timestamp headers (empty for fixed cols — filled when first batch runs)
    Row 1: fixed column labels
    """
    row0 = ["", "File name", "Metric"]   # batch labels appended in col 3+
    row1 = ["", "File name", "Metric"]   # JSON/Spreadsheet/Database appended in col 3+
    return [row0, row1]


def _is_valid_csv(rows: List[List[str]]) -> bool:
    """Return True if rows look like a real CSV (not binary xlsx data)."""
    if not rows:
        return True  # empty is valid — will be initialised
    first_cell = rows[0][0] if rows[0] else ""
    # xlsx files start with PK (ZIP magic)
    if first_cell.startswith("PK\x03\x04") or "\x00" in first_cell:
        return False
    return True


def _pad_row(row: List[str], length: int) -> List[str]:
    """Extend row in-place so it has at least `length` elements."""
    while len(row) < length:
        row.append("")
    return row


def _pad_all_rows(rows: List[List[str]], length: int) -> None:
    """Pad every row to at least `length` columns."""
    for row in rows:
        _pad_row(row, length)


def _find_next_batch_col(rows: List[List[str]]) -> int:
    """
    Return 0-based column index where the new 3-column batch block should start.
    Looks at row 1 (column headers) for the last non-empty entry.
    Never returns less than _FIRST_DATA_COL (3).
    """
    last = _FIRST_DATA_COL - 1
    if len(rows) >= 2:
        for i, val in enumerate(rows[1]):
            if val.strip():
                last = max(last, i)
    return last + 1


def _scan_job_sections(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """
    Scan rows for job sections.
    A section starts where col C (index 2) == "Total Time".
    Returns list of {file_name, start_row, metrics: {name: row_idx}}.
    """
    sections: List[Dict[str, Any]] = []
    i = HEADER_ROWS
    while i < len(rows):
        row = rows[i]
        metric_val = row[_COL_METRIC].strip() if len(row) > _COL_METRIC else ""
        if metric_val == "Total Time":
            file_name = row[_COL_FILENAME].strip() if len(row) > _COL_FILENAME else ""
            metric_map: Dict[str, int] = {}
            for offset in range(ROWS_PER_JOB):
                j = i + offset
                if j < len(rows):
                    mv = rows[j][_COL_METRIC].strip() if len(rows[j]) > _COL_METRIC else ""
                    if mv:
                        metric_map[mv] = j
            sections.append(
                {
                    "file_name": file_name,
                    "start_row": i,
                    "metrics": metric_map,
                }
            )
            i += ROWS_PER_JOB
        else:
            i += 1
    return sections


def _add_job_section(rows: List[List[str]], file_name: str) -> Dict[str, Any]:
    """
    Append a new blank job section (7 rows) to the CSV rows.
    Returns the new section dict so the caller can fill metric values immediately.
    """
    # Determine how many columns wide the current rows are
    width = max((len(r) for r in rows), default=_FIRST_DATA_COL)
    start_row = len(rows)
    metric_map: Dict[str, int] = {}
    for offset, metric_name in enumerate(METRIC_NAMES):
        row_idx = start_row + offset
        new_row = _pad_row(
            [
                "",
                file_name if offset == 0 else "",
                metric_name,
            ],
            width,
        )
        rows.append(new_row)
        metric_map[metric_name] = row_idx
    return {
        "file_name": file_name,
        "start_row": start_row,
        "metrics": metric_map,
    }


def _append_batch_headers(rows: List[List[str]], start_col: int, batch_label: str) -> None:
    """
    Write batch label and sub-column headers into rows 0 and 1
    at the given start_col (0-based).
    Row 0: batch_label repeated for 3 cols
    Row 1: JSON, Spreadsheet, Database
    """
    need = start_col + 3
    _pad_row(rows[0], need)
    _pad_row(rows[1], need)
    for offset, sub_label in enumerate(("JSON", "Spreadsheet", "Database")):
        rows[0][start_col + offset] = batch_label
        rows[1][start_col + offset] = sub_label


# ---------------------------------------------------------------------------
# CSV report preview for Streamlit
# ---------------------------------------------------------------------------


def _extract_current_batch_comparison(
    rows: List[List[str]],
) -> Dict[str, Any]:
    """
    Pure-data function. Reads the already-loaded CSV rows and returns a dict:

        {
            "success": bool,
            "df": pd.DataFrame | None,   # clean comparison table
            "batch_label": str,          # e.g. "Batch 2026-06-18 15:32"
            "error": str | None,
        }

    Logic:
    - Row 1 is the column-header row.
    - "File name" is at _COL_FILENAME (col 1).
    - "Metric"    is at _COL_METRIC   (col 2).
    - "Real Job Result" is found by case-insensitive scan of row 1.
    - The latest batch JSON/Spreadsheet/Database group is the rightmost
      occurrence of "json" (case-insensitive, stripped) in row 1.
    - File names are forward-filled: blank cells inherit from the most recent
      non-blank value above them in the same column (per job section).
    - Fully blank rows and rows with no metric are skipped.
    The CSV file is never modified.
    """
    import pandas as pd  # local import keeps module-level deps minimal

    if len(rows) < 2:
        return {"success": False, "df": None, "batch_label": "", "error": "Report has fewer than 2 rows."}

    header_row = rows[1]   # row 1 = column-name row
    timestamp_row = rows[0]  # row 0 = batch timestamp labels

    # ── Locate "Real Job Result" column ──────────────────────────────────────
    col_real_result: Optional[int] = None
    for i, v in enumerate(header_row):
        if "real job" in v.strip().lower():
            col_real_result = i
            break
    if col_real_result is None:
        return {
            "success": False,
            "df": None,
            "batch_label": "",
            "error": (
                "'Real Job Result' column not found in header row. "
                "Expected a cell containing 'real job' (case-insensitive)."
            ),
        }

    # ── Locate the latest JSON / Spreadsheet / Database group ────────────────
    # Scan row 1 right-to-left for the rightmost cell equal to "json".
    col_json_latest: Optional[int] = None
    for i in range(len(header_row) - 1, -1, -1):
        if header_row[i].strip().lower() == "json":
            col_json_latest = i
            break
    if col_json_latest is None:
        return {
            "success": False,
            "df": None,
            "batch_label": "",
            "error": (
                "No 'JSON' column found in header row. "
                "Run a batch first to generate batch result columns."
            ),
        }

    col_sheet_latest = col_json_latest + 1
    col_db_latest    = col_json_latest + 2
    if col_db_latest >= len(header_row):
        return {
            "success": False,
            "df": None,
            "batch_label": "",
            "error": (
                f"Latest batch JSON group starts at column {col_json_latest} "
                "but is incomplete (Spreadsheet or Database column missing)."
            ),
        }

    # ── Batch timestamp label ─────────────────────────────────────────────────
    batch_label = (
        timestamp_row[col_json_latest].strip()
        if col_json_latest < len(timestamp_row)
        else ""
    )

    # ── Extract data rows ─────────────────────────────────────────────────────
    table_rows: List[Dict[str, str]] = []
    last_filename = ""

    for row in rows[HEADER_ROWS:]:   # skip the two header rows
        # Forward-fill file name
        raw_fname = row[_COL_FILENAME].strip() if _COL_FILENAME < len(row) else ""
        if raw_fname:
            last_filename = raw_fname
        fname = last_filename

        metric      = row[_COL_METRIC].strip()      if _COL_METRIC < len(row)      else ""
        real_result = row[col_real_result].strip()   if col_real_result < len(row)  else ""
        json_val    = row[col_json_latest].strip()   if col_json_latest < len(row)  else ""
        sheet_val   = row[col_sheet_latest].strip()  if col_sheet_latest < len(row) else ""
        db_val      = row[col_db_latest].strip()     if col_db_latest < len(row)    else ""

        # Skip rows with no metric name
        if not metric:
            continue
        # Skip fully blank data cells (keeps the table tidy)
        if not any([fname, real_result, json_val, sheet_val, db_val]):
            continue

        table_rows.append(
            {
                "File name":       fname,
                "Metric":          metric,
                "Real Job Result": real_result,
                "JSON":            json_val,
                "Spreadsheet":     sheet_val,
                "Database":        db_val,
            }
        )

    if not table_rows:
        return {
            "success": False,
            "df": None,
            "batch_label": batch_label,
            "error": "No data rows found for the latest batch.",
        }

    return {
        "success": True,
        "df": pd.DataFrame(table_rows),
        "batch_label": batch_label,
        "error": None,
    }


def _batch_comparison_styles() -> str:
    """
    Scoped CSS for the grouped current-batch comparison HTML table.

    Renders a scrollable dark spreadsheet-style container that matches the
    existing raw CSV preview aesthetic: black background, thin cyan grid
    lines, compact rows, sticky header, fixed max-height with scroll.
    """
    return (
        "<style>"
        # Scrollable outer container — fixed height, dark border, rounded
        ".cbt-scroll{"
        "max-height:520px;"
        "overflow-y:auto;"
        "overflow-x:auto;"
        "border:1px solid rgba(0,255,249,0.35);"
        "border-radius:4px;"
        "background:rgba(8,4,18,0.95);"
        "margin:0.4rem 0;"
        "}"
        # Table fills the container; min-width prevents column squash
        ".cbt-table{"
        "width:100%;"
        "min-width:max-content;"
        "border-collapse:collapse;"
        "font-size:13px;"
        "font-family:'Segoe UI',Arial,sans-serif;"
        "}"
        # Sticky header so column labels stay visible while scrolling
        ".cbt-table thead th{"
        "position:sticky;"
        "top:0;"
        "z-index:2;"
        "background:rgba(0,50,80,0.98);"
        "color:#00fff9;"
        "padding:5px 10px;"
        "text-align:left;"
        "white-space:nowrap;"
        "border-bottom:1px solid rgba(0,255,249,0.4);"
        "border-right:1px solid rgba(0,255,249,0.15);"
        "font-size:13px;"
        "font-family:'Segoe UI',Arial,sans-serif;"
        "letter-spacing:0.02em;"
        "}"
        # Body cells: readable font, slightly looser than before
        ".cbt-table tbody td{"
        "padding:5px 8px;"
        "border-right:1px solid rgba(0,255,249,0.1);"
        "border-bottom:1px solid rgba(0,255,249,0.07);"
        "color:#d8eaf8;"
        "vertical-align:middle;"
        "white-space:nowrap;"
        "font-size:13px;"
        "line-height:1.3;"
        "}"
        # File name cell: amber, bold, readable font
        ".cbt-fname{"
        "color:#ffd93d !important;"
        "font-weight:700;"
        "font-family:'Segoe UI',Arial,sans-serif;"
        "vertical-align:top !important;"
        "background:rgba(10,4,22,0.9) !important;"
        "border-right:2px solid rgba(0,255,249,0.3) !important;"
        "padding-top:5px !important;"
        "min-width:8rem;"
        "}"
        # Metric cell: muted label, same readable font
        ".cbt-metric{"
        "color:#7a8fa8;"
        "font-family:'Segoe UI',Arial,sans-serif;"
        "}"
        # Even-row tint within a group (explicit class avoids rowspan issues)
        ".cbt-row-alt td{"
        "background:rgba(18,8,36,0.6);"
        "}"
        # Thick cyan separator line before every new job group (except the first)
        ".cbt-group-sep td{"
        "border-top:2px solid rgba(0,255,249,0.45) !important;"
        "}"
        "</style>"
    )


def _build_grouped_batch_html(table_rows: List[Dict[str, str]]) -> str:
    """
    Build an HTML table string with rowspan on the File name cell.

    Each unique file name gets a merged cell spanning all its metric rows.
    A thick top border ('cbt-group-sep') is added to the first row of every
    group except the very first one, creating a clear visual separator.
    """
    import html as _html

    def _e(s: str) -> str:
        return _html.escape(str(s))

    # ── Group rows by file name in CSV order ─────────────────────────────────
    groups: List[Tuple[str, List[Dict[str, str]]]] = []
    current_fname: Optional[str] = None
    current_group: List[Dict[str, str]] = []

    for row in table_rows:
        fname = row["File name"]
        if fname != current_fname:
            if current_group:
                groups.append((current_fname or "", current_group))
            current_fname = fname
            current_group = [row]
        else:
            current_group.append(row)
    if current_group:
        groups.append((current_fname or "", current_group))

    # ── Build HTML ────────────────────────────────────────────────────────────
    cols = ["Metric", "Real Job Result", "JSON", "Spreadsheet", "Database"]

    parts: List[str] = [
        '<div class="cbt-scroll"><table class="cbt-table">',
        "<thead><tr>",
        '<th>File name</th>',
    ]
    for col in cols:
        parts.append(f"<th>{_e(col)}</th>")
    parts.append("</tr></thead><tbody>")

    for g_idx, (fname, g_rows) in enumerate(groups):
        rowspan = len(g_rows)
        is_first_group = g_idx == 0

        for r_idx, row in enumerate(g_rows):
            is_first_row = r_idx == 0
            # Alternate tint within a group
            row_class = "cbt-row-alt" if r_idx % 2 == 1 else ""
            # Thick separator above every group start except the very first
            if is_first_row and not is_first_group:
                row_class = (row_class + " cbt-group-sep").strip()

            parts.append(f'<tr class="{row_class}">' if row_class else "<tr>")

            # File name cell: only on the first row of each group, spans all rows
            if is_first_row:
                parts.append(
                    f'<td class="cbt-fname" rowspan="{rowspan}">{_e(fname)}</td>'
                )

            # Metric cell
            parts.append(f'<td class="cbt-metric">{_e(row["Metric"])}</td>')

            # Value cells
            for col in cols[1:]:  # skip "Metric" already rendered
                parts.append(f"<td>{_e(row.get(col, ''))}</td>")

            parts.append("</tr>")

    parts.append("</tbody></table></div>")  # closes cbt-scroll
    return "".join(parts)


def render_current_batch_comparison(report_path: str) -> None:
    """
    Render the 'Current batch comparison' section.

    Displays a grouped HTML table where each job's file name appears once
    (rowspan), metric rows are listed beneath it, and a thick horizontal
    separator line appears between job groups.

    Only the latest/rightmost batch group is shown.
    The CSV file is never modified.
    """
    import streamlit as st

    rows = _load_csv(report_path)

    st.markdown("#### Current batch comparison")

    if not rows:
        st.info("Batch report is empty — run a batch first.")
        return
    if not _is_valid_csv(rows):
        st.warning("Report file appears to be corrupt. Cannot build clean comparison.")
        return

    result = _extract_current_batch_comparison(rows)

    if not result["success"]:
        st.warning(f"Could not build clean comparison: {result['error']}")
        return

    batch_label = result["batch_label"]
    caption = "Showing Real Job Result compared with the latest batch only."
    if batch_label:
        caption += f"  Batch: **{batch_label}**"
    st.caption(caption)

    # Build the grouped HTML table from the flat list of row dicts
    df = result["df"]
    if df is None or df.empty:
        st.info("No data rows to display.")
        return

    table_rows: List[Dict[str, str]] = df.to_dict(orient="records")

    st.markdown(_batch_comparison_styles(), unsafe_allow_html=True)
    st.markdown(_build_grouped_batch_html(table_rows), unsafe_allow_html=True)


def render_report_preview_for_streamlit(report_path: str) -> None:
    """
    Render the full batch report preview.

    Displays two sections:
    1. "Current batch comparison" — clean table with the latest batch only.
    2. "Full CSV report"          — raw grid showing every column/row in the file.

    The report uses intentional duplicate column names (JSON / Spreadsheet /
    Database repeat per batch group).  Pandas cannot use duplicates as DataFrame
    column names, so the raw grid assigns display-only letter labels (A, B, C …)
    and never modifies or rewrites the CSV file.
    """
    import streamlit as st
    import pandas as pd

    # ── 1. Clean current-batch comparison ────────────────────────────────────
    render_current_batch_comparison(report_path)

    st.markdown("---")

    # ── 2. Full raw CSV grid ──────────────────────────────────────────────────
    st.markdown("#### Full CSV report")
    try:
        rows = _load_csv(report_path)
        if not rows:
            st.info("Batch report is empty.")
            return
        if not _is_valid_csv(rows):
            st.error("Report file appears to be corrupt or not a valid CSV.")
            return

        # Find the widest row so we can pad everything uniformly
        max_cols = max((len(r) for r in rows), default=0)
        if max_cols == 0:
            st.info("Batch report has no columns.")
            return

        # Pad every row to max_cols without mutating the originals
        padded = [r + [""] * (max_cols - len(r)) for r in rows]

        # Build display-only column labels: A B C … Z AA AB …
        # These exist only in the preview widget and are never written to disk.
        def _col_label(i: int) -> str:
            label = ""
            i += 1  # 1-based
            while i > 0:
                i, rem = divmod(i - 1, 26)
                label = chr(ord("A") + rem) + label
            return label

        display_cols = [_col_label(i) for i in range(max_cols)]

        # All rows (including the two CSV header rows) appear as grid cells
        df = pd.DataFrame(padded, columns=display_cols)
        df = df.head(202)  # rows 0-1 are report headers; show up to 200 data rows

        st.caption(
            "Shows all batches and all columns in the full CSV report. "
            "Column letters (A, B, C …) are display-only labels. "
            "Rows 1–2 are the report header rows. "
            "The CSV file is not modified by this preview."
        )
        st.dataframe(df, use_container_width=True)
    except Exception as exc:
        st.error(f"Could not preview batch report: {exc}")


# ---------------------------------------------------------------------------
# Main batch runner
# ---------------------------------------------------------------------------


def run_batch(
    analyzer,
    selected_folders: List[str],
    logistics_params: Dict[str, Any],
    *,
    json_db_name: Optional[str] = None,
    spreadsheet_db_name: Optional[str] = None,
    backend_catalog_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run a full batch test across the selected saved moves and write results
    to the CSV report.

    Returns:
    {
        'success': bool,
        'report_path': str|None,
        'backup_path': str|None,
        'processed': int,
        'skipped': int,
        'errors': List[str],
    }
    """
    from saved_move_replay import load_saved_move

    result: Dict[str, Any] = {
        "success": False,
        "report_path": None,
        "backup_path": None,
        "processed": 0,
        "skipped": 0,
        "errors": [],
    }
    errors = result["errors"]

    # ── 1. Pre-flight ────────────────────────────────────────────────────────

    if not selected_folders:
        errors.append("No saved moves selected.")
        return result

    os.makedirs(REPORT_DIR, exist_ok=True)

    # Locate or create the CSV
    report_path = find_report_csv()
    if report_path is None:
        # Create a fresh CSV in canonical location
        report_path = REPORT_PATH
        _save_csv(report_path, _init_empty_csv())

    # Ensure canonical location
    if os.path.normpath(report_path) != os.path.normpath(REPORT_PATH):
        try:
            shutil.copy2(report_path, REPORT_PATH)
            report_path = REPORT_PATH
        except Exception as exc:
            errors.append(f"Could not copy report to canonical location: {exc}")
            return result

    # ── 2. Backup ────────────────────────────────────────────────────────────

    backup_path, bk_err = backup_report_csv(report_path)
    if bk_err:
        errors.append(bk_err)
    else:
        result["backup_path"] = backup_path

    # ── 3. Load CSV ──────────────────────────────────────────────────────────

    rows = _load_csv(report_path)

    # Re-initialise if missing, empty, or binary (old xlsx)
    if not rows or not _is_valid_csv(rows):
        if rows and not _is_valid_csv(rows):
            errors.append(
                "Existing report file is not a valid CSV (possibly an old Excel file). "
                "Starting a fresh CSV report."
            )
        rows = _init_empty_csv()

    # Ensure two header rows exist
    while len(rows) < HEADER_ROWS:
        rows.append(["", "File name", "Metric"])

    # ── 4. Validate header ───────────────────────────────────────────────────

    row1 = rows[1] if len(rows) > 1 else []
    has_filename_col = any("file name" in str(v).lower() for v in row1)
    if not has_filename_col:
        # Patch missing header
        _pad_row(row1, 3)
        row1[_COL_FILENAME] = "File name"
        row1[_COL_METRIC] = "Metric"

    # ── 5. Scan job sections ─────────────────────────────────────────────────

    sections = _scan_job_sections(rows)

    # ── 6. Determine new batch column position ───────────────────────────────

    start_col = _find_next_batch_col(rows)
    col_json = start_col
    col_sheet = start_col + 1
    col_db = start_col + 2
    needed_width = col_db + 1

    now = datetime.now()
    batch_label = f"Batch {now.strftime('%Y-%m-%d %H:%M')}"
    _append_batch_headers(rows, start_col, batch_label)

    # Pad all existing data rows
    _pad_all_rows(rows, needed_width)

    # ── 7. Process each selected saved move ──────────────────────────────────

    for folder_id in selected_folders:
        saved_move = load_saved_move(folder_id)
        if not saved_move:
            errors.append(f"Saved move file missing or unreadable: {folder_id}")
            result["skipped"] += 1
            continue

        move_name = saved_move.get("name") or folder_id

        saved_defaults = saved_move.get("default_logistics", {})
        effective_lp = _merge_logistics_params(saved_defaults, logistics_params)

        job_results = run_batch_replay_for_saved_move(
            analyzer,
            saved_move,
            effective_lp,
            errors=errors,
            json_db_name=json_db_name,
            spreadsheet_db_name=spreadsheet_db_name,
            backend_catalog_cache=backend_catalog_cache,
        )
        if job_results is None:
            result["skipped"] += 1
            continue

        # Find or create section for this move
        exact_matches = [s for s in sections if s["file_name"] == move_name]
        if len(exact_matches) > 1:
            errors.append(
                f"File name '{move_name}' appears {len(exact_matches)} times in report. Skipping."
            )
            result["skipped"] += 1
            continue
        elif len(exact_matches) == 1:
            section = exact_matches[0]
        else:
            # New file — create a new section at the bottom
            section = _add_job_section(rows, move_name)
            # Pad the newly added rows to the required width
            for r_idx in range(section["start_row"], section["start_row"] + ROWS_PER_JOB):
                if r_idx < len(rows):
                    _pad_row(rows[r_idx], needed_width)
            sections.append(section)

        # Write metric values into the appropriate row+column
        for metric_name in METRIC_NAMES:
            row_idx = section["metrics"].get(metric_name)
            if row_idx is None:
                errors.append(
                    f"Metric '{metric_name}' row missing in section for '{move_name}'."
                )
                continue
            _pad_row(rows[row_idx], needed_width)
            rows[row_idx][col_json]  = job_results["JSON"].get(metric_name, "")
            rows[row_idx][col_sheet] = job_results["Spreadsheet"].get(metric_name, "")
            rows[row_idx][col_db]    = job_results["Database"].get(metric_name, "")

        result["processed"] += 1

    # ── 8. Save CSV ──────────────────────────────────────────────────────────

    try:
        _save_csv(report_path, rows)
        result["report_path"] = report_path
        result["success"] = True
    except Exception as exc:
        errors.append(f"Could not write CSV report: {exc}")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merge_logistics_params(
    saved_defaults: Dict[str, Any], current_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Merge saved default logistics with current sidebar params.
    Current params take precedence.
    """
    merged = dict(saved_defaults)
    for key in ("pickup_access", "dropoff_access", "travel_time", "pre_move_travel", "forced_movers"):
        if key in current_params:
            merged[key] = current_params[key]
    merged.setdefault("pickup_access", {"type": "ground", "floors": 0})
    merged.setdefault("dropoff_access", {"type": "ground", "floors": 0})
    merged.setdefault("travel_time", 30)
    merged.setdefault("pre_move_travel", 30)
    return merged


def load_saved_moves() -> List[Dict[str, Any]]:
    """Thin wrapper used by batch UI — re-exports list_saved_moves."""
    from saved_move_replay import list_saved_moves
    return list_saved_moves()
