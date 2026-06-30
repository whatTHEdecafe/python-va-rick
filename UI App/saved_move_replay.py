"""
saved_move_replay.py — Helper functions for the Saved Move Replay feature.

Active saved moves  : Data/test_moves/
Deleted saved moves : Data/deleted_test_moves/

Each move is stored in its own sub-folder containing a single move.json file
and optional preview images (preview_00.jpg, preview_01.jpg, ...).
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    Image = None
    _PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURRENT_DIR)

TEST_MOVES_DIR = os.path.join(_PARENT_DIR, "Data", "test_moves")
DELETED_MOVES_DIR = os.path.join(_PARENT_DIR, "Data", "deleted_test_moves")

PREVIEW_MAX_DIM = 1200
PREVIEW_QUALITY = 75

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def ensure_test_moves_dir() -> None:
    """Create Data/test_moves/ and Data/deleted_test_moves/ if they do not exist."""
    os.makedirs(TEST_MOVES_DIR, exist_ok=True)
    os.makedirs(DELETED_MOVES_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def make_safe_filename(name: str) -> str:
    """Convert a human-readable name to a safe folder-name suffix (max 50 chars)."""
    safe = re.sub(r"[^\w\s-]", "", name.lower())
    safe = re.sub(r"[\s_]+", "_", safe).strip("_-")
    return safe[:50] if safe else "untitled"


# ---------------------------------------------------------------------------
# List / load
# ---------------------------------------------------------------------------


def list_saved_moves() -> List[Dict[str, Any]]:
    """
    Return a sorted list of active saved move metadata dicts from Data/test_moves/.
    Each dict includes the full parsed move.json plus '_folder' and '_folder_path'.
    Only active moves (not deleted) are returned.
    """
    ensure_test_moves_dir()
    moves: List[Dict[str, Any]] = []
    if not os.path.isdir(TEST_MOVES_DIR):
        return moves
    for folder_name in sorted(os.listdir(TEST_MOVES_DIR)):
        folder_path = os.path.join(TEST_MOVES_DIR, folder_name)
        move_json_path = os.path.join(folder_path, "move.json")
        if os.path.isdir(folder_path) and os.path.isfile(move_json_path):
            try:
                with open(move_json_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                data["_folder"] = folder_name
                data["_folder_path"] = folder_path
                moves.append(data)
            except Exception:
                pass
    return moves


def load_saved_move(move_id_or_folder: str) -> Optional[Dict[str, Any]]:
    """
    Load a single saved move by its folder name (or id).
    Returns the parsed dict (with '_folder' and '_folder_path') or None if not found.
    """
    ensure_test_moves_dir()
    folder_path = os.path.join(TEST_MOVES_DIR, move_id_or_folder)
    move_json_path = os.path.join(folder_path, "move.json")
    if not os.path.isfile(move_json_path):
        return None
    try:
        with open(move_json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["_folder"] = move_id_or_folder
        data["_folder_path"] = folder_path
        return data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_media_previews(uploaded_files, scenario_folder: str) -> List[str]:
    """
    Resize and save JPG previews from uploaded image files into scenario_folder.
    Videos are skipped (only metadata is stored elsewhere).
    Returns a list of saved preview filenames (e.g. ["preview_00.jpg", ...]).
    """
    if not _PIL_AVAILABLE or not uploaded_files:
        return []

    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic", ".heif"}
    saved: List[str] = []
    img_idx = 0

    for uf in uploaded_files:
        ext = os.path.splitext(uf.name)[1].lower()
        if ext not in _IMAGE_EXTS:
            continue
        try:
            uf.seek(0)
            img = Image.open(uf)
            img.load()
            w, h = img.size
            if w > PREVIEW_MAX_DIM or h > PREVIEW_MAX_DIM:
                ratio = min(PREVIEW_MAX_DIM / w, PREVIEW_MAX_DIM / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            preview_name = f"preview_{img_idx:02d}.jpg"
            img.save(os.path.join(scenario_folder, preview_name), "JPEG", quality=PREVIEW_QUALITY)
            saved.append(preview_name)
            img_idx += 1
        except Exception:
            continue

    return saved


def save_current_move(
    name: str,
    vision_result: Dict[str, Any],
    detected_items: List[Dict[str, Any]],
    logistics_params: Dict[str, Any],
    uploaded_files=None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Save a completed analysis as a test move.
    Creates Data/test_moves/<timestamp>_<safe_name>/move.json and preview images.
    Returns the folder name (used as the move id) on success, or None on failure.
    """
    ensure_test_moves_dir()
    now = datetime.now(timezone.utc)
    folder_id = now.strftime("%Y%m%d_%H%M%S") + "_" + make_safe_filename(name)
    folder_path = os.path.join(TEST_MOVES_DIR, folder_id)
    os.makedirs(folder_path, exist_ok=True)

    preview_names = save_media_previews(uploaded_files or [], folder_path)

    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic", ".heif"}
    original_names = [
        uf.name for uf in (uploaded_files or [])
        if os.path.splitext(uf.name)[1].lower() in _IMAGE_EXTS
    ]

    move_data: Dict[str, Any] = {
        "schemaVersion": "1.0",
        "id": folder_id,
        "name": name,
        "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Captured from live Gemini analysis",
        "vision_result": vision_result,
        "detected_items": detected_items,
        "default_logistics": logistics_params,
        "media": {
            "previews": preview_names,
            "original_names": original_names,
        },
        "metadata": metadata or {},
    }

    try:
        with open(os.path.join(folder_path, "move.json"), "w", encoding="utf-8") as fh:
            json.dump(move_data, fh, indent=2)
        return folder_id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def rename_saved_move(move_id_or_folder: str, new_name: str) -> bool:
    """
    Update the 'name' field inside move.json in-place.
    Does NOT rename the folder on disk (the folder id stays stable).
    Returns True on success, False otherwise.
    """
    folder_path = os.path.join(TEST_MOVES_DIR, move_id_or_folder)
    move_json_path = os.path.join(folder_path, "move.json")
    if not os.path.isfile(move_json_path):
        return False
    try:
        with open(move_json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["name"] = new_name.strip()
        with open(move_json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


def delete_saved_move(move_id_or_folder: str) -> bool:
    """
    Soft-delete: move the folder from Data/test_moves/ to Data/deleted_test_moves/.
    If the destination folder already exists, a timestamp suffix is appended to avoid
    collisions.  Returns True on success, False otherwise.
    """
    ensure_test_moves_dir()
    src = os.path.join(TEST_MOVES_DIR, move_id_or_folder)
    if not os.path.isdir(src):
        return False
    dst = os.path.join(DELETED_MOVES_DIR, move_id_or_folder)
    if os.path.exists(dst):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dst = f"{dst}_{ts}"
    try:
        shutil.move(src, dst)
        return True
    except Exception:
        return False
