#!/usr/bin/env python3
"""
Standalone read-only test for VisionItems direct SQL catalog load.

Usage (from repo root, after filling DATABASE_PASSWORD in .env):
    pip install -r requirements.txt
    python test_vision_catalog_sql.py
"""

from __future__ import annotations

import os
import sys

UI_APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "UI App")
if UI_APP_DIR not in sys.path:
    sys.path.insert(0, UI_APP_DIR)

from vision_catalog_sql_client import (  # noqa: E402
    VISION_ITEMS_SELECT,
    VisionCatalogSqlError,
    build_connection_string,
    load_database_config,
    validate_database_password,
)


def main() -> int:
    cfg = load_database_config()
    password_error = validate_database_password(cfg)
    if password_error:
        print(f"Success: False")
        print(f"Message: {password_error}")
        return 1

    try:
        import pyodbc
    except ImportError:
        print("Success: False")
        print("Message: pyodbc is not installed. Run: pip install -r requirements.txt")
        return 1

    conn = None
    try:
        conn_str = build_connection_string(cfg)
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("SELECT DB_NAME()")
        db_name = cursor.fetchone()[0]
        print(f"Connected database: {db_name}")

        cursor.execute("SELECT COUNT(*) FROM VisionItems")
        total_count = int(cursor.fetchone()[0])
        print(f"VisionItems count: {total_count}")

        cursor.execute(VISION_ITEMS_SELECT)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchmany(3)]

        print("Success: True")
        print(f"Message: Loaded sample rows from VisionItems on {cfg['server']}/{cfg['database']}.")
        print("")
        print("First 3 VisionItems:")

        for idx, item in enumerate(rows, start=1):
            print(f"--- Item {idx} ---")
            print(f"  Id: {item.get('Id')}")
            print(f"  CanonicalItem: {item.get('CanonicalItem')}")
            print(f"  Aliases: {item.get('Aliases')}")
            print(f"  BaseTimeSMin: {item.get('BaseTimeSMin')}")
            print(f"  BaseTimeMMin: {item.get('BaseTimeMMin')}")
            print(f"  BaseTimeLMin: {item.get('BaseTimeLMin')}")
            print(f"  StairsAdderPerFlightSMin: {item.get('StairsAdderPerFlightSMin')}")
            print(f"  StairsAdderPerFlightMMin: {item.get('StairsAdderPerFlightMMin')}")
            print(f"  StairsAdderPerFlightLMin: {item.get('StairsAdderPerFlightLMin')}")
            print(f"  ElevatorAdderPerRideSMin: {item.get('ElevatorAdderPerRideSMin')}")
            print(f"  ElevatorAdderPerRideMMin: {item.get('ElevatorAdderPerRideMMin')}")
            print(f"  ElevatorAdderPerRideLMin: {item.get('ElevatorAdderPerRideLMin')}")
            print(f"  UnloadMultiplierMainFloor: {item.get('UnloadMultiplierMainFloor')}")
            print(f"  UnloadMultiplierElevator: {item.get('UnloadMultiplierElevator')}")
            print(f"  UnloadMultiplierStairs: {item.get('UnloadMultiplierStairs')}")

        return 0
    except VisionCatalogSqlError as exc:
        print("Success: False")
        print(f"Message: {exc.message}")
        return 1
    except pyodbc.Error as exc:
        print("Success: False")
        print(f"Message: {exc}")
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
