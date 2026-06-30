"""
Read-only VisionItems catalog client — direct SQL Server access.

Loads the VisionItems table from the remote database used by the C# backend.
SELECT queries only; no writes.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

_PASSWORD_PLACEHOLDER = "FILL_FROM_CSHARP_BACKEND_APPSETTINGS_DEFAULTCONNECTION_PASSWORD"
_DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"
_FALLBACK_DRIVER = "ODBC Driver 17 for SQL Server"
_CONNECTION_TIMEOUT_SECONDS = 30

VISION_ITEMS_SELECT = """
SELECT
    Id,
    CanonicalItem,
    Aliases,
    CuFtS,
    CuFtM,
    CuFtL,
    WeightSLb,
    WeightMLb,
    WeightLLb,
    TwoPersonFlag,
    StackableFlag,
    StackableSavingsPct,
    FitsElevatorHint,
    BaseTimeSMin,
    BaseTimeMMin,
    BaseTimeLMin,
    DisassemblyAdderSMin,
    DisassemblyAdderMMin,
    DisassemblyAdderLMin,
    BulkyAdderSMin,
    BulkyAdderMMin,
    BulkyAdderLMin,
    HeavyAdderSMin,
    HeavyAdderMMin,
    HeavyAdderLMin,
    StairsAdderPerFlightSMin,
    StairsAdderPerFlightMMin,
    StairsAdderPerFlightLMin,
    ElevatorAdderPerRideSMin,
    ElevatorAdderPerRideMMin,
    ElevatorAdderPerRideLMin,
    UnloadMultiplierMainFloor,
    UnloadMultiplierElevator,
    UnloadMultiplierStairs,
    ClassificationLogicNotes,
    CreatedAt,
    UpdatedAt
FROM VisionItems
ORDER BY CanonicalItem
""".strip()


class VisionCatalogSqlError(Exception):
    """Raised when VisionItems cannot be loaded from SQL Server."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_database_config() -> Dict[str, Any]:
    """Load SQL Server connection settings from environment / .env."""
    load_dotenv(os.path.join(_repo_root(), ".env"))

    server = (os.getenv("DATABASE_SERVER") or "209.59.182.143").strip()
    port = (os.getenv("DATABASE_PORT") or "1433").strip()
    database = (os.getenv("DATABASE_NAME") or "movez-db-dev").strip()
    user = (os.getenv("DATABASE_USER") or "sa").strip()
    password = os.getenv("DATABASE_PASSWORD") or ""
    driver = (os.getenv("DATABASE_DRIVER") or _DEFAULT_DRIVER).strip()
    trust_cert = (os.getenv("DATABASE_TRUST_CERTIFICATE") or "true").strip().lower() in (
        "1", "true", "yes", "on",
    )
    mars = (os.getenv("DATABASE_MARS") or "true").strip().lower() in (
        "1", "true", "yes", "on",
    )

    return {
        "server": server,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "driver": driver,
        "trust_certificate": trust_cert,
        "mars": mars,
        "server_with_port": f"{server},{port}",
    }


def validate_database_password(config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return an error message if DATABASE_PASSWORD is missing or still a placeholder."""
    cfg = config or load_database_config()
    password = (cfg.get("password") or "").strip()
    if not password:
        return (
            "DATABASE_PASSWORD is blank in .env. Copy the Password value from the C# backend "
            "appsettings.json ConnectionStrings:DefaultConnection into .env."
        )
    if password == _PASSWORD_PLACEHOLDER:
        return (
            "DATABASE_PASSWORD is still the placeholder in .env. Replace it with the Password "
            "value from the C# backend appsettings.json ConnectionStrings:DefaultConnection."
        )
    return None


def _sanitize_error_message(message: str, config: Dict[str, Any]) -> str:
    """Remove password fragments from error text before showing in UI/logs."""
    sanitized = message or ""
    password = config.get("password") or ""
    if password:
        sanitized = sanitized.replace(password, "***")
    sanitized = re.sub(r"PWD=[^;]*", "PWD=***", sanitized, flags=re.IGNORECASE)
    return sanitized


def _resolve_odbc_driver(preferred_driver: str) -> str:
    import pyodbc

    installed = {driver.strip() for driver in pyodbc.drivers()}
    if preferred_driver in installed:
        return preferred_driver
    if preferred_driver != _FALLBACK_DRIVER and _FALLBACK_DRIVER in installed:
        return _FALLBACK_DRIVER
    if _DEFAULT_DRIVER in installed:
        return _DEFAULT_DRIVER

    available = ", ".join(sorted(installed)) or "(none detected)"
    raise VisionCatalogSqlError(
        f"ODBC SQL Server driver not found. Configured driver: '{preferred_driver}'. "
        f"Install 'ODBC Driver 18 for SQL Server' (or 17). Installed drivers: {available}"
    )


def build_connection_string(config: Optional[Dict[str, Any]] = None, *, driver: Optional[str] = None) -> str:
    """Build a pyodbc connection string. Never log or print the return value."""
    cfg = config or load_database_config()
    chosen_driver = driver or _resolve_odbc_driver(cfg["driver"])
    parts = [
        f"DRIVER={{{chosen_driver}}}",
        f"SERVER={cfg['server_with_port']}",
        f"DATABASE={cfg['database']}",
        f"UID={cfg['user']}",
        f"PWD={cfg['password']}",
        f"TrustServerCertificate={'yes' if cfg['trust_certificate'] else 'no'}",
    ]
    if cfg["mars"]:
        parts.append("MARS_Connection=yes")
    parts.append(f"Connection Timeout={_CONNECTION_TIMEOUT_SECONDS}")
    return ";".join(parts)


def _row_to_dict(cursor, row) -> Dict[str, Any]:
    columns = [col[0] for col in cursor.description]
    return {columns[idx]: row[idx] for idx in range(len(columns))}


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).strip()


def _coerce_aliases(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_safe_text(item) for item in value if _safe_text(item))
    return _safe_text(value)


def normalize_sql_item_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a VisionItems SQL row to CSV-style keys used by MovingCalculator.

    CanonicalItem is used as the catalog category name (no separate Category column).
    """
    def pick(*keys: str, default: Any = "") -> Any:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return default

    two_person_raw = pick("TwoPersonFlag", default="")
    if isinstance(two_person_raw, bool):
        two_person = "Yes" if two_person_raw else "No"
    else:
        two_person = _safe_text(two_person_raw)

    stackable_raw = pick("StackableFlag", default="")
    if isinstance(stackable_raw, bool):
        stackable = "Yes" if stackable_raw else "No"
    else:
        stackable = _safe_text(stackable_raw)

    return {
        "Id": pick("Id"),
        "CanonicalItem": _safe_text(pick("CanonicalItem", default="")),
        "Aliases": _coerce_aliases(pick("Aliases", default="")),
        "CuFtS": pick("CuFtS"),
        "CuFtM": pick("CuFtM"),
        "CuFtL": pick("CuFtL"),
        "WeightSLb": pick("WeightSLb"),
        "WeightMLb": pick("WeightMLb"),
        "WeightLLb": pick("WeightLLb"),
        "TwoPersonFlag": two_person,
        "StackableFlag": stackable,
        "StackableSavingsPct": pick("StackableSavingsPct"),
        "FitsElevatorHint": _safe_text(pick("FitsElevatorHint", default="")),
        "BaseTimeSMin": pick("BaseTimeSMin"),
        "BaseTimeMMin": pick("BaseTimeMMin"),
        "BaseTimeLMin": pick("BaseTimeLMin"),
        "DisassemblyAdderSMin": pick("DisassemblyAdderSMin"),
        "DisassemblyAdderMMin": pick("DisassemblyAdderMMin"),
        "DisassemblyAdderLMin": pick("DisassemblyAdderLMin"),
        "BulkyAdderSMin": pick("BulkyAdderSMin"),
        "BulkyAdderMMin": pick("BulkyAdderMMin"),
        "BulkyAdderLMin": pick("BulkyAdderLMin"),
        "HeavyAdderSMin": pick("HeavyAdderSMin"),
        "HeavyAdderMMin": pick("HeavyAdderMMin"),
        "HeavyAdderLMin": pick("HeavyAdderLMin"),
        "StairsAdderPerFlightSMin": pick("StairsAdderPerFlightSMin"),
        "StairsAdderPerFlightMMin": pick("StairsAdderPerFlightMMin"),
        "StairsAdderPerFlightLMin": pick("StairsAdderPerFlightLMin"),
        "ElevatorAdderPerRideSMin": pick("ElevatorAdderPerRideSMin"),
        "ElevatorAdderPerRideMMin": pick("ElevatorAdderPerRideMMin"),
        "ElevatorAdderPerRideLMin": pick("ElevatorAdderPerRideLMin"),
        "UnloadMultiplierMainFloor": pick("UnloadMultiplierMainFloor"),
        "UnloadMultiplierElevator": pick("UnloadMultiplierElevator"),
        "UnloadMultiplierStairs": pick("UnloadMultiplierStairs"),
        "ClassificationLogicNotes": _safe_text(pick("ClassificationLogicNotes", default="")),
        "CreatedAt": _safe_text(pick("CreatedAt", default="")),
        "UpdatedAt": _safe_text(pick("UpdatedAt", default="")),
    }


def normalize_sql_items_to_catalog_rows(sql_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize all SQL VisionItem rows to CSV-style catalog rows."""
    return [normalize_sql_item_row(row) for row in (sql_items or []) if isinstance(row, dict)]


def _translate_sql_error(exc: Exception, config: Dict[str, Any]) -> str:
    import pyodbc

    raw = _sanitize_error_message(str(exc), config)
    lower = raw.lower()

    if isinstance(exc, pyodbc.Error):
        if "28000" in raw or "login failed" in lower or "18456" in raw:
            return (
                "SQL login failed. Check DATABASE_USER and DATABASE_PASSWORD in .env "
                "(copy Password from C# appsettings ConnectionStrings:DefaultConnection)."
            )
        if "08001" in raw or "connection" in lower and "failed" in lower:
            return (
                f"Could not connect to SQL Server at {config['server_with_port']}. "
                f"Check DATABASE_SERVER, DATABASE_PORT, firewall, and VPN access. Details: {raw}"
            )
        if "42s02" in lower or "invalid object name" in lower and "visionitems" in lower:
            return "VisionItems table was not found in the configured database."
        if "42s22" in lower or "invalid column name" in lower:
            return f"VisionItems query failed because a column is missing: {raw}"

    return raw


def fetch_vision_items_from_sql(
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Read VisionItems from SQL Server using SELECT only.

    Returns (items_list, fetch_meta). Raises VisionCatalogSqlError on failure.
    """
    import pyodbc

    cfg = config or load_database_config()
    password_error = validate_database_password(cfg)
    if password_error:
        raise VisionCatalogSqlError(password_error)

    conn = None
    try:
        conn_str = build_connection_string(cfg)
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(VISION_ITEMS_SELECT)
        rows = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        if not rows:
            raise VisionCatalogSqlError("VisionItems table returned no rows.")

        meta = {
            "server": cfg["server"],
            "port": cfg["port"],
            "database": cfg["database"],
            "server_with_port": cfg["server_with_port"],
            "item_count": len(rows),
            "driver": _resolve_odbc_driver(cfg["driver"]),
        }
        return rows, meta
    except VisionCatalogSqlError:
        raise
    except pyodbc.Error as exc:
        raise VisionCatalogSqlError(_translate_sql_error(exc, cfg)) from exc
    except Exception as exc:
        raise VisionCatalogSqlError(_sanitize_error_message(str(exc), cfg)) from exc
    finally:
        if conn is not None:
            conn.close()


def test_backend_catalog() -> Dict[str, Any]:
    """
    Load VisionItems for UI test button / status display.
    Returns a status dict (never raises).
    """
    cfg = load_database_config()
    source_label = f"{cfg['server_with_port']}/{cfg['database']}"
    try:
        items, meta = fetch_vision_items_from_sql(cfg)
        return {
            "success": True,
            "message": (
                f"Loaded {meta['item_count']} VisionItems from SQL Server "
                f"({cfg['server']}/{cfg['database']})."
            ),
            "item_count": meta["item_count"],
            "sql_server": cfg["server"],
            "sql_port": cfg["port"],
            "sql_database": cfg["database"],
            "sql_source": source_label,
            "odbc_driver": meta.get("driver"),
            "last_error": None,
            "raw_items": items,
        }
    except VisionCatalogSqlError as exc:
        return {
            "success": False,
            "message": exc.message,
            "item_count": 0,
            "sql_server": cfg["server"],
            "sql_port": cfg["port"],
            "sql_database": cfg["database"],
            "sql_source": source_label,
            "odbc_driver": None,
            "last_error": exc.message,
            "raw_items": None,
        }
