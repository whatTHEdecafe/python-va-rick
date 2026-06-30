"""
Moovez Vision Analyzer - Streamlit UI Application (Version 9)

Entry points (same app):
  - From repo root:  streamlit run app.py
  - From this dir:   streamlit run app.py

This application provides a user-friendly web interface for the Moovez Vision Analyzer.
Uses Gemini 2.5 AI models with File API for efficient multi-image and video analysis.

Features:
- Single API call for multiple images and/or videos using File API
- Video file support (.mp4, .mov, .avi, .mkv, .webm, etc.)
- Gemini 2.5 Flash model (recommended) with thinking mode disabled
- Real-time moving cost and logistics estimation
- Comprehensive item detection and categorization
- Modular architecture with abstraction, inheritance, and polymorphism
"""

import streamlit as st
import html
import json
import os
import time
import hashlib
import copy
from pathlib import Path
import tempfile
import pandas as pd
import sys
from typing import Optional

# Import HEIC support for iPhone images - MUST be before PIL import
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIC support is optional

from PIL import Image

from pipeline_utils import hash_uploaded_files, will_need_vision
from time_estimate_ui import (
    breakdown_step_rows,
    render_time_algorithm_breakdown,
)
from loading_ui import (
    LOGISTICS_SPINNER_MSG,
    inject_vision_loading_styles,
    vision_loading_panel,
)
from csv_json_compare_panel import (
    COMPARE_JSON_DB,
    COMPARE_SPREADSHEET_DB,
    compute_dual_source_results,
    render_csv_json_comparison_sections,
)
from labor_time_debug_flow import (
    format_item_time_total_html,
    format_item_time_value,
    render_labor_time_bridge_section,
    _render_item_breakdown_time_totals_summary,
)

# --------------- Version Registry & Dynamic Loader ---------------
import importlib.util

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

VERSION_REGISTRY = {
    "Version 9": ("Version 9", "MoovEZVisionAnalyzerV7"),
}
DEFAULT_VERSION = "Version 9"

# Discover available item databases in /Data/ and the project root
DATA_DIR = os.path.join(parent_dir, "Data")


def is_supported_item_database(filename: str, directory: str) -> bool:
    """Return True for JSON catalogs or CSVs with the expected item-database header."""
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        return False
    if filename.lower().endswith(".json"):
        return True
    if not filename.lower().endswith(".csv"):
        return False
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return "CanonicalItem" in (f.readline() or "").split(",")
    except OSError:
        return False


_item_db_files = sorted([
    f for f in os.listdir(DATA_DIR)
    if is_supported_item_database(f, DATA_DIR)
]) if os.path.isdir(DATA_DIR) else []
if os.path.isdir(parent_dir):
    for f in sorted(os.listdir(parent_dir)):
        if is_supported_item_database(f, parent_dir) and f not in _item_db_files:
            _item_db_files.append(f)
DEFAULT_DB = "moving_items_logistics_v2.json" if "moving_items_logistics_v2.json" in _item_db_files else (_item_db_files[0] if _item_db_files else None)


def resolve_item_database_path(db_name: Optional[str]) -> Optional[str]:
    """Resolve selected item database names from /Data first, then project root."""
    if not db_name:
        return None
    data_path = os.path.join(DATA_DIR, db_name)
    if os.path.isfile(data_path):
        return data_path
    root_path = os.path.join(parent_dir, db_name)
    if os.path.isfile(root_path):
        return root_path
    return data_path

def load_analyzer_class(version_key: str):
    """Dynamically import and return the analyzer class for the chosen version."""
    dir_name, class_name = VERSION_REGISTRY[version_key]
    gemini_dir = os.path.join(parent_dir, dir_name, "Gemini")
    agent_path = os.path.join(gemini_dir, "vision-agent.py")

    if gemini_dir not in sys.path:
        sys.path.insert(0, gemini_dir)

    module_alias = f"vision_agent_{dir_name.replace(' ', '_').lower()}"
    spec = importlib.util.spec_from_file_location(module_alias, agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)

# Page configuration
st.set_page_config(
    page_title="Moovez Vision Analyzer",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)


def st_image_compat(image, caption=None):
    """st.image across Streamlit versions (use_column_width vs use_container_width)."""
    try:
        st.image(image, caption=caption, use_container_width=True)
    except TypeError:
        st.image(image, caption=caption, use_column_width=True)


# Custom CSS — 80s arcade / CRT vibe (chrome only; uploaded images stay unfiltered)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Press+Start+2P&family=VT323&display=swap');

    :root {
        --retro-bg-deep: #0a0518;
        --retro-panel: #16082e;
        --retro-border: #00fff9;
        --retro-cyan: #00fff9;
        --retro-magenta: #ff2eea;
        --retro-amber: #ffd93d;
        --retro-orange: #ff6b35;
        --retro-text: #e8f4ff;
        --retro-muted: #8899aa;
    }

    .stApp {
        background-color: var(--retro-bg-deep);
        /* Horizon glow + subtle wire grid + main gradient (images unaffected — not applied to img) */
        background-image:
            radial-gradient(ellipse 130% 55% at 50% 100%, rgba(255, 46, 234, 0.16) 0%, transparent 52%),
            repeating-linear-gradient(
                90deg,
                transparent,
                transparent 46px,
                rgba(0, 255, 249, 0.04) 46px,
                rgba(0, 255, 249, 0.04) 47px
            ),
            repeating-linear-gradient(
                0deg,
                transparent,
                transparent 28px,
                rgba(255, 46, 234, 0.028) 28px,
                rgba(255, 46, 234, 0.028) 29px
            ),
            linear-gradient(165deg, var(--retro-bg-deep) 0%, #1a0a38 45%, #0d0630 78%, #060214 100%);
        background-attachment: fixed;
        color: var(--retro-text);
    }

    @keyframes retro-scan-drift {
        0%, 100% { opacity: 0.32; }
        50% { opacity: 0.41; }
    }

    /* CRT scanlines — decorative overlay, pointer-events none */
    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 999;
        background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.17),
            rgba(0, 0, 0, 0.17) 1px,
            transparent 1px,
            transparent 3px
        );
        opacity: 0.35;
        animation: retro-scan-drift 5s ease-in-out infinite;
    }

    /* Tube vignette — sits under scanlines, above page content */
    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 998;
        background: radial-gradient(
            ellipse 82% 72% at 50% 44%,
            transparent 42%,
            rgba(0, 0, 0, 0.52) 100%
        );
    }

    @keyframes retro-pulse-border {
        0%, 100% { box-shadow: 4px 0 24px rgba(255, 46, 234, 0.14); }
        50% { box-shadow: 4px 0 30px rgba(0, 255, 249, 0.22); }
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #12081f 0%, #1c1038 100%) !important;
        border-right: 4px solid var(--retro-magenta);
        box-shadow: 4px 0 24px rgba(255, 46, 234, 0.12);
        animation: retro-pulse-border 6s ease-in-out infinite;
    }

    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span {
        font-family: 'VT323', monospace !important;
        font-size: 1.2rem !important;
        color: var(--retro-text) !important;
    }

    [data-testid="stHeader"] {
        background: rgba(10, 5, 24, 0.92);
        border-bottom: 2px solid var(--retro-border);
    }

    /* Hide Streamlit header toolbar buttons (keyboard shortcuts, deploy, etc.) */
    [data-testid="stToolbar"] {
        display: none !important;
    }
    .stDeployButton,
    [data-testid="stDeployButton"] {
        display: none !important;
    }

    /* Hide sidebar collapse button */
    button[data-testid="stBaseButton-headerNoPadding"][aria-label=""] {
        display: none !important;
    }

    .main .block-container {
        font-family: 'VT323', monospace !important;
        font-size: 1.25rem;
        padding-top: 2rem;
    }

    .main-header {
        font-family: 'Press Start 2P', monospace !important;
        font-size: clamp(1rem, 2.5vw, 1.35rem);
        color: var(--retro-amber);
        text-align: center;
        padding: 1rem 0;
        text-shadow:
            0 0 8px var(--retro-magenta),
            2px 2px 0 #330066,
            -1px -1px 0 var(--retro-border);
        letter-spacing: 0.06em;
        line-height: 1.6;
    }

    .metric-card {
        background: rgba(22, 8, 46, 0.85);
        border: 3px solid var(--retro-border);
        border-radius: 2px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: inset 0 0 20px rgba(0, 255, 249, 0.06), 4px 4px 0 rgba(0, 0, 0, 0.4);
    }

    .item-card {
        background: rgba(22, 8, 46, 0.75);
        border: 2px solid rgba(255, 46, 234, 0.45);
        padding: 1rem;
        border-radius: 2px;
        margin: 0.5rem 0;
    }

    .success-box {
        background: rgba(0, 80, 60, 0.45);
        border: 3px solid #00ff88;
        border-left-width: 6px;
        padding: 1rem;
        margin: 1rem 0;
        font-family: 'VT323', monospace !important;
        color: #bfffdf !important;
        box-shadow: 0 0 16px rgba(0, 255, 136, 0.25);
    }

    /* Section titles — sci-fi display font (main title keeps .main-header / Press Start 2P) */
    h2, h3 {
        font-family: 'Orbitron', 'VT323', monospace !important;
        font-weight: 700 !important;
        color: var(--retro-cyan) !important;
        text-shadow: 1px 1px 0 #440088, 0 0 12px rgba(0, 255, 249, 0.15);
        letter-spacing: 0.04em;
    }

    h1:not(.main-header) {
        font-family: 'Orbitron', 'VT323', monospace !important;
        color: var(--retro-cyan) !important;
        text-shadow: 1px 1px 0 #440088;
    }

    /* Tabs — chunky arcade tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(10, 5, 30, 0.6);
        padding: 8px;
        border-radius: 4px;
        border: 2px solid rgba(0, 255, 249, 0.35);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: 'Press Start 2P', monospace !important;
        font-size: 0.52rem !important;
        color: var(--retro-muted) !important;
        background: rgba(30, 15, 60, 0.9) !important;
        border: 2px solid rgba(255, 46, 234, 0.35) !important;
        border-radius: 2px !important;
        padding: 10px 12px !important;
    }

    .stTabs [aria-selected="true"] {
        color: var(--retro-amber) !important;
        background: rgba(80, 20, 100, 0.95) !important;
        border-color: var(--retro-border) !important;
        box-shadow: 0 0 12px rgba(0, 255, 249, 0.35);
    }

    /* Primary buttons — chunky retro */
    .stButton > button[kind="primary"],
    div[data-testid="column"] .stButton > button {
        font-family: 'VT323', monospace !important;
        font-size: 1.3rem !important;
        background: linear-gradient(180deg, var(--retro-orange) 0%, #c43d1a 100%) !important;
        color: #fff !important;
        font-weight: bold !important;
        border-radius: 2px !important;
        padding: 0.45rem 1.5rem !important;
        border: 4px solid #ffd93d !important;
        box-shadow: 4px 4px 0 #330066, inset 0 -3px 0 rgba(0, 0, 0, 0.25);
    }

    .stButton > button[kind="primary"]:hover {
        filter: brightness(1.08);
        transform: translate(-1px, -1px);
        box-shadow: 5px 5px 0 #330066;
    }

    /* Metrics / dataframe chrome — do NOT target img (uploaded media stays crisp) */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        font-family: 'VT323', monospace !important;
    }

    [data-testid="stMetricDelta"] {
        font-family: 'VT323', monospace !important;
    }

    div[data-testid="stExpander"], div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(0, 255, 249, 0.25);
    }

    .stAlert {
        font-family: 'VT323', monospace !important;
        border-radius: 2px !important;
        border-width: 2px !important;
    }

    [data-testid="stCaption"], .stCaption {
        font-family: 'VT323', monospace !important;
        color: var(--retro-muted) !important;
    }

    /* ----- Base Web widgets (select, slider, inputs, checkbox, radio) ----- */
    .stTextInput label, .stSelectbox label, .stSlider label, .stNumberInput label,
    .stCheckbox label, .stRadio label, .stMultiSelect label, .stDateInput label,
    .stTimeInput label, .stTextArea label {
        font-family: 'VT323', monospace !important;
        font-size: 1.15rem !important;
        color: var(--retro-cyan) !important;
    }

    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        font-family: 'VT323', monospace !important;
        font-size: 1.25rem !important;
        background-color: rgba(22, 8, 46, 0.94) !important;
        color: var(--retro-text) !important;
        border: 2px solid rgba(0, 255, 249, 0.48) !important;
        border-radius: 2px !important;
        caret-color: var(--retro-amber);
    }

    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        border-color: var(--retro-magenta) !important;
        box-shadow: 0 0 0 1px var(--retro-magenta), 0 0 14px rgba(255, 46, 234, 0.28) !important;
    }

    [data-baseweb="select"] > div {
        font-family: 'VT323', monospace !important;
        font-size: 1.2rem !important;
        background-color: rgba(22, 8, 46, 0.96) !important;
        border: 2px solid rgba(255, 46, 234, 0.52) !important;
        border-radius: 2px !important;
        color: var(--retro-text) !important;
    }

    [data-baseweb="select"]:focus-within > div {
        border-color: var(--retro-border) !important;
        box-shadow: 0 0 12px rgba(0, 255, 249, 0.22) !important;
    }

    ul[data-baseweb="menu"], div[data-baseweb="popover"] ul {
        font-family: 'VT323', monospace !important;
        background-color: #16082e !important;
        border: 2px solid var(--retro-border) !important;
        border-radius: 2px !important;
    }

    li[data-baseweb="menu-item"], [role="option"] {
        font-family: 'VT323', monospace !important;
        color: var(--retro-text) !important;
        background-color: transparent !important;
    }

    li[data-baseweb="menu-item"]:hover, [role="option"]:hover {
        background-color: rgba(255, 46, 234, 0.18) !important;
    }

    [data-baseweb="slider"] div[class*="Track"],
    [data-baseweb="slider"] [data-testid="stSliderTrack"] {
        background: rgba(0, 255, 249, 0.15) !important;
        border-radius: 2px !important;
    }

    [data-baseweb="slider"] [role="slider"] {
        background-color: var(--retro-amber) !important;
        border: 3px solid #2a1048 !important;
        box-shadow: 0 0 10px rgba(255, 217, 61, 0.45);
    }

    [data-baseweb="slider"] [data-testid="stThumbValue"] {
        font-family: 'VT323', monospace !important;
        color: var(--retro-amber) !important;
    }

    [data-baseweb="checkbox"] label, [data-baseweb="radio"] label {
        font-family: 'VT323', monospace !important;
        font-size: 1.15rem !important;
        color: var(--retro-text) !important;
    }

    [data-baseweb="checkbox"] div[class*="Checkmark"], [data-baseweb="radio"] div[class*="RadioMarkOuter"] {
        border-color: var(--retro-border) !important;
        border-radius: 2px !important;
    }

    /* Secondary / default Streamlit buttons */
    .stButton > button[kind="secondary"] {
        font-family: 'VT323', monospace !important;
        font-size: 1.15rem !important;
        background: rgba(36, 18, 62, 0.95) !important;
        color: var(--retro-text) !important;
        border: 2px solid rgba(0, 255, 249, 0.55) !important;
        border-radius: 2px !important;
        box-shadow: 3px 3px 0 rgba(0, 0, 0, 0.35);
    }

    .stDownloadButton button {
        font-family: 'VT323', monospace !important;
        border-radius: 2px !important;
        border: 2px solid var(--retro-magenta) !important;
        background: rgba(22, 8, 46, 0.9) !important;
        color: var(--retro-text) !important;
    }

    /* File upload drop zone */
    [data-testid="stFileUploader"] section[data-testid="stFileUploadDropzone"] {
        background: rgba(22, 8, 46, 0.55) !important;
        border: 2px dashed rgba(0, 255, 249, 0.42) !important;
        border-radius: 2px !important;
    }

    [data-testid="stFileUploader"] button {
        font-family: 'VT323', monospace !important;
    }

    /* Dataframes & data editor — terminal-adjacent chrome (does not affect images) */
    [data-testid="stDataFrame"] {
        outline: 2px solid rgba(0, 255, 249, 0.35);
        outline-offset: 2px;
        border-radius: 2px;
    }

    [data-testid="stDataFrame"] div, [data-testid="stDataEditor"] div {
        font-family: 'VT323', monospace !important;
    }

    .glide-data-grid-container, .dvn-scroller {
        font-family: 'VT323', monospace !important;
    }

    .stExpander summary, details summary {
        font-family: 'VT323', monospace !important;
        color: var(--retro-cyan) !important;
    }
</style>
""", unsafe_allow_html=True)
inject_vision_loading_styles()

# Initialize session state
if 'analyzer' not in st.session_state:
    st.session_state.analyzer = None
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = []
if 'selected_model' not in st.session_state:
    st.session_state.selected_model = 'gemini-2.5-flash'
if 'performance_test_results' not in st.session_state:
    st.session_state.performance_test_results = []
if 'enable_performance_test' not in st.session_state:
    st.session_state.enable_performance_test = False
if 'active_version' not in st.session_state:
    st.session_state.active_version = DEFAULT_VERSION
st.session_state.active_version = DEFAULT_VERSION
if 'selected_db' not in st.session_state:
    st.session_state.selected_db = DEFAULT_DB
if 'vision_result' not in st.session_state:
    st.session_state.vision_result = None
if 'detected_items' not in st.session_state:
    st.session_state.detected_items = None
if 'enriched_items' not in st.session_state:
    st.session_state.enriched_items = None
if 'logistics_result' not in st.session_state:
    st.session_state.logistics_result = None
if 'logistics_params' not in st.session_state:
    st.session_state.logistics_params = None
if 'media_fingerprint' not in st.session_state:
    st.session_state.media_fingerprint = None
if 'debug_simulation_active' not in st.session_state:
    st.session_state.debug_simulation_active = False
if 'debug_simulation_calculations' not in st.session_state:
    st.session_state.debug_simulation_calculations = None
if 'debug_simulation_movers' not in st.session_state:
    st.session_state.debug_simulation_movers = None
if 'debug_simulation_vehicle' not in st.session_state:
    st.session_state.debug_simulation_vehicle = None
if 'json_comparison_result' not in st.session_state:
    st.session_state.json_comparison_result = None
if 'spreadsheet_comparison_result' not in st.session_state:
    st.session_state.spreadsheet_comparison_result = None


def build_logistics_params(pickup_type, pickup_floors, dropoff_type, dropoff_floors,
                           travel_time, pre_move_travel, forced_movers=None):
    return {
        'pickup_access': {'type': pickup_type, 'floors': int(pickup_floors)},
        'dropoff_access': {'type': dropoff_type, 'floors': int(dropoff_floors)},
        'travel_time': int(travel_time),
        'pre_move_travel': int(pre_move_travel),
        'forced_movers': forced_movers,
    }


def logistics_params_differ(current, previous):
    if not previous:
        return False
    return json.dumps(current, sort_keys=True) != json.dumps(previous, sort_keys=True)


def build_analysis_result(vision_result, enriched_items, logistics_result, analyzer, extra_metrics=None):
    """Bundle for tabs / JSON download."""
    metrics = dict(getattr(analyzer, 'metrics', {}))
    if vision_result and vision_result.get('metrics'):
        metrics.update(vision_result['metrics'])
    if extra_metrics:
        metrics.update(extra_metrics)
    if hasattr(analyzer, 'current_model'):
        metrics['model_name'] = analyzer.current_model
    metrics['api_method'] = 'File API (single call for multiple images/videos)'
    return {
        'items': enriched_items,
        'summary': (vision_result or {}).get('summary', {}),
        'vision': vision_result,
        'calculations': logistics_result,
        'metrics': metrics,
        'apiMethod': metrics['api_method'],
    }


def run_analyze_move(
    analyzer,
    file_paths,
    logistics_params,
    *,
    upload_fingerprint: str,
    force_vision: bool = False,
):
    """
    Analyze Move: Gemini only if upload content changed; always enrich + logistics.
    Returns (analysis bundle or None, used_vision: bool).
    """
    need_vision = will_need_vision(upload_fingerprint, force_vision=force_vision)

    if need_vision:
        vision = analyzer.analyze_media(file_paths)
        if not vision or not vision.get('items'):
            return None, need_vision
        st.session_state.vision_result = vision
        st.session_state.media_fingerprint = upload_fingerprint
        st.session_state.detected_items = [copy.deepcopy(i) for i in vision['items']]
    elif not st.session_state.detected_items and st.session_state.vision_result:
        st.session_state.detected_items = [copy.deepcopy(i) for i in st.session_state.vision_result['items']]

    items = st.session_state.detected_items or []
    if not items:
        return None

    enriched = analyzer.enrich_items(items)
    lp = logistics_params
    logistics = analyzer.compute_logistics(
        enriched,
        lp['pickup_access'],
        lp['dropoff_access'],
        lp['travel_time'],
        lp['pre_move_travel'],
        forced_movers=lp.get('forced_movers'),
    )
    if not logistics:
        return None, need_vision

    st.session_state.enriched_items = enriched
    st.session_state.logistics_result = logistics
    st.session_state.logistics_params = copy.deepcopy(logistics_params)
    bundle = build_analysis_result(st.session_state.vision_result, enriched, logistics, analyzer)
    return bundle, need_vision


def clear_analysis_cache():
    st.session_state.vision_result = None
    st.session_state.detected_items = None
    st.session_state.enriched_items = None
    st.session_state.logistics_result = None
    st.session_state.logistics_params = None
    st.session_state.media_fingerprint = None
    st.session_state.analysis_result = None
    st.session_state.debug_simulation_active = False
    st.session_state.debug_simulation_calculations = None
    st.session_state.debug_simulation_movers = None
    st.session_state.debug_simulation_vehicle = None
    st.session_state.json_comparison_result = None
    st.session_state.spreadsheet_comparison_result = None


def _reset_debug_simulation():
    st.session_state.debug_simulation_active = False
    st.session_state.debug_simulation_calculations = None
    st.session_state.debug_simulation_movers = None
    st.session_state.debug_simulation_vehicle = None


def _store_comparison_results(detected_items, logistics_params, vision_result, metrics=None):
    """Compute and cache JSON vs spreadsheet comparison outputs (temporary debug panel)."""
    try:
        json_result, spreadsheet_result = compute_dual_source_results(
            detected_items,
            logistics_params,
            vision_result,
            metrics,
        )
        st.session_state.json_comparison_result = json_result
        st.session_state.spreadsheet_comparison_result = spreadsheet_result
    except Exception as exc:
        st.session_state.json_comparison_result = {
            "error": f"JSON comparison calculation failed: {exc}",
            "comparison_meta": {
                "source_type": "JSON",
                "database_filename": COMPARE_JSON_DB,
                "category_count": None,
            },
        }
        st.session_state.spreadsheet_comparison_result = {
            "error": f"Spreadsheet comparison calculation failed: {exc}",
            "comparison_meta": {
                "source_type": "Spreadsheet CSV",
                "database_filename": COMPARE_SPREADSHEET_DB,
                "category_count": None,
            },
        }


def _run_debug_simulation(forced_movers):
    """Debug-only recalculation via existing compute_logistics + forced_movers."""
    analyzer = st.session_state.get("analyzer")
    enriched = st.session_state.get("enriched_items")
    lp = st.session_state.get("logistics_params")
    if not analyzer or not enriched or not lp:
        return None
    return analyzer.compute_logistics(
        enriched,
        lp["pickup_access"],
        lp["dropoff_access"],
        lp["travel_time"],
        lp["pre_move_travel"],
        forced_movers=int(forced_movers),
    )


def _to_float(value):
    if value in (None, "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_item_totals(matching, item_times):
    total_base = total_load = total_unload = total_item_time = total_qty = 0.0
    for idx, m in enumerate(matching):
        it = item_times[idx] if idx < len(item_times) else {}
        qty = int(m.get("quantity", 1) or 1)
        total_qty += qty
        try:
            if it.get("baseTimeUsed") is not None:
                total_base += float(it["baseTimeUsed"]) * qty
            if it.get("loadTime") is not None:
                total_load += float(it["loadTime"]) * qty
            if it.get("unloadTime") is not None:
                total_unload += float(it["unloadTime"]) * qty
            if it.get("totalTimeAfterQuantity") is not None:
                total_item_time += float(it["totalTimeAfterQuantity"])
            elif it.get("totalTimePerItem") is not None:
                total_item_time += float(it["totalTimePerItem"]) * qty
        except (TypeError, ValueError):
            pass
    return {
        "total_base": total_base,
        "total_load": total_load,
        "total_unload": total_unload,
        "total_item_time": total_item_time,
        "total_qty": total_qty,
        "item_rows": len(matching),
    }


_ITEM_GRID_HEADERS = (
    "Status", "Item", "Matched category", "Match method", "Qty", "Size",
    "Base", "Load", "Unload", "Total", "Note",
)

_ITEM_GRID_COL_TEMPLATE = (
    "70px minmax(150px,1.5fr) minmax(150px,1.4fr) 90px 50px 80px "
    "90px 90px 90px 110px minmax(80px,1fr)"
)


def _format_item_time_cell(value):
    """Format a time value for item grid cells (one decimal when needed)."""
    return format_item_time_value(value)


def _item_breakdown_grid_styles():
    """CSS for dense clickable spreadsheet-style item breakdown grid."""
    cols = _ITEM_GRID_COL_TEMPLATE
    return (
        "<style>"
        ".ib-sheet{width:100%;border:1px solid rgba(0,255,249,0.35);border-radius:2px;"
        "overflow-x:auto;font-family:'VT323',monospace;font-size:1.25rem;}"
        ".debug-item-grid{display:grid;grid-template-columns:"
        + cols + ";width:100%;margin:0;}"
        ".debug-item-grid .ib-hdr{background:rgba(0,70,110,0.55);color:#00fff9;"
        "font-weight:bold;font-size:1.25rem;padding:4px 6px;border-bottom:1px solid rgba(0,255,249,0.35);"
        "border-right:1px solid rgba(0,255,249,0.18);}"
        ".debug-item-grid .ib-cell{padding:3px 6px;border-right:1px solid rgba(0,255,249,0.08);"
        "color:#e8f4ff;font-size:1.25rem;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}"
        ".ib-row{margin:0;padding:0;border-bottom:1px solid rgba(0,255,249,0.1);}"
        ".ib-row summary{list-style:none;cursor:pointer;margin:0;padding:0;}"
        ".ib-row summary::-webkit-details-marker{display:none;}"
        ".ib-row summary::marker{content:'';}"
        ".ib-row .ib-summary-grid{border:none;border-radius:0;}"
        ".ib-row.ib-even .ib-cell{background:rgba(14,5,30,0.45);}"
        ".ib-row.ib-alt .ib-cell{background:rgba(22,8,46,0.55);}"
        ".ib-row:hover .ib-cell{background:rgba(40,18,70,0.65);}"
        ".ib-row[open] .ib-cell{background:rgba(50,22,80,0.7);}"
        ".ib-detail-panel{padding:6px 10px 8px;background:rgba(8,4,18,0.92);"
        "border-top:1px solid rgba(0,255,249,0.15);font-size:0.98rem;}"
        ".ib-detail-cols{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px;}"
        ".ib-detail-line{margin:1px 0;color:#e8f4ff;line-height:1.3;}"
        ".ib-detail-lbl{color:#8899aa;}"
        ".ib-formula{margin-top:6px;color:#8899aa;font-size:0.94rem;}"
        ".ib-warn{margin-top:5px;color:#ffd93d;font-size:0.96rem;}"
        ".debug-item-grid.ib-total .ib-cell{background:rgba(70,35,10,0.55);color:#ffd93d;"
        "font-weight:bold;font-size:1.25rem;border-top:2px solid rgba(255,217,61,0.45);padding:4px 6px;}"
        ".debug-item-grid.ib-total .ib-cell.ib-time-total{white-space:normal;line-height:1.3;"
        "overflow:visible;text-overflow:unset;min-height:2.5em;}"
        ".debug-item-grid .ib-status-used{color:#00ff88;}"
        ".debug-item-grid .ib-status-fallback{color:#ffd93d;}"
        "</style>"
    )


def _item_grid_row_html(cells, row_class="ib-even", cell_class="ib-cell"):
    """Build one complete grid row HTML block from a list of cell values."""
    parts = [f'<div class="debug-item-grid {row_class}">']
    for cell in cells:
        parts.append(f'<div class="{cell_class}">{_escape_html(cell)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _item_grid_header_html():
    """Spreadsheet header row."""
    parts = ['<div class="debug-item-grid ib-header">']
    for cell in _ITEM_GRID_HEADERS:
        parts.append(f'<div class="ib-hdr">{_escape_html(cell)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _item_row_cells(match_row, time_row):
    """Extract aligned column values for one item row."""
    status = "Fallback" if match_row.get("unknownFallbackUsed") else "Used"
    note = "fallback" if match_row.get("unknownFallbackUsed") else "—"
    return [
        status,
        match_row.get("inputName", "Unknown"),
        match_row.get("matchedCategoryName", "N/A"),
        match_row.get("matchMethod", "N/A"),
        str(match_row.get("quantity", 1)),
        match_row.get("selectedSize") or time_row.get("size", "N/A"),
        _format_item_time_cell(time_row.get("baseTimeUsed")),
        _format_item_time_cell(time_row.get("loadTime")),
        _format_item_time_cell(time_row.get("unloadTime")),
        _format_item_time_cell(time_row.get("totalTimePerItem")),
        note,
    ]


def _item_summary_grid_html(cells, status_value):
    """Grid row used as the clickable summary inside a details element."""
    parts = ['<div class="debug-item-grid ib-summary-grid">']
    for idx, cell in enumerate(cells):
        cls = "ib-cell"
        if idx == 0:
            if status_value == "Fallback":
                cls += " ib-status-fallback"
            else:
                cls += " ib-status-used"
        parts.append(f'<div class="{cls}">{_escape_html(cell)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _item_detail_line(label, value):
    """One escaped detail line for the expanded panel."""
    return (
        f'<div class="ib-detail-line">'
        f'<span class="ib-detail-lbl">{_escape_html(label)}:</span> '
        f'{_escape_html(value)}</div>'
    )


def _item_details_html(match_row, time_row):
    """HTML detail panel shown when an item row is expanded."""
    status = "Fallback" if match_row.get("unknownFallbackUsed") else "Used"
    qty = match_row.get("quantity", 1)
    load_t = time_row.get("loadTime", "N/A")
    unload_t = time_row.get("unloadTime", "N/A")
    note = "Unknown catalog fallback" if match_row.get("unknownFallbackUsed") else ""

    left = [
        _item_detail_line("Item name", match_row.get("inputName")),
        _item_detail_line("Raw AI name", match_row.get("inputName")),
        _item_detail_line("Input category", match_row.get("inputCategory") or "N/A"),
        _item_detail_line("Lookup key", match_row.get("lookupKey")),
        _item_detail_line("Matched category", match_row.get("matchedCategoryName")),
        _item_detail_line("Matched id/key", match_row.get("matchedCategoryId") or "N/A"),
        _item_detail_line("Match method", match_row.get("matchMethod")),
        _item_detail_line("Selected size", match_row.get("selectedSize")),
        _item_detail_line("Quantity", qty),
        _item_detail_line("Status", status),
    ]
    if note:
        left.append(_item_detail_line("Problem / note", note))

    right = [
        _item_detail_line("Base time used", f"{time_row.get('baseTimeUsed', 'N/A')} min"),
        _item_detail_line("Disassembly adder", time_row.get("disassemblyAdderUsed") or "N/A"),
        _item_detail_line("Heavy adder", time_row.get("heavyAdderUsed") or "N/A"),
        _item_detail_line("Load time", f"{time_row.get('loadTime', 'N/A')} min"),
        _item_detail_line("Unload ratio", time_row.get("unloadRatio", "N/A")),
        _item_detail_line("Unload time", f"{time_row.get('unloadTime', 'N/A')} min"),
        _item_detail_line("Total item contribution", f"{time_row.get('totalTimeAfterQuantity', 'N/A')} min"),
        _item_detail_line("Required movers", time_row.get("requiredMovers") or "N/A"),
        _item_detail_line("Stackable", "Yes" if time_row.get("stackable") else "No"),
        _item_detail_line("Weight used", time_row.get("weightUsed", "N/A")),
        _item_detail_line("Volume used", time_row.get("volumeUsed", "N/A")),
    ]

    formula_html = ""
    if load_t not in (None, "N/A") and unload_t not in (None, "N/A"):
        try:
            per_item = float(load_t) + float(unload_t)
            formula_text = (
                f"Load time {load_t} min + unload time {unload_t} min = {per_item:.1f} min per item. "
                f"Quantity {qty} makes {per_item * qty:.1f} min total."
            )
            formula_html = f'<div class="ib-formula">{_escape_html(formula_text)}</div>'
        except (TypeError, ValueError):
            pass

    warn_html = ""
    if match_row.get("unknownFallbackUsed"):
        warn_html = '<div class="ib-warn">Unknown fallback was used for this item.</div>'

    return (
        '<div class="ib-detail-panel">'
        '<div class="ib-detail-cols">'
        f'<div>{"".join(left)}</div>'
        f'<div>{"".join(right)}</div>'
        '</div>'
        f'{formula_html}{warn_html}'
        '</div>'
    )


def _item_expandable_row_html(match_row, time_row, row_idx):
    """One clickable item row using native HTML details/summary."""
    row_class = "ib-alt" if row_idx % 2 else "ib-even"
    cells = _item_row_cells(match_row, time_row)
    status = cells[0]
    return (
        f'<details class="ib-row {row_class}">'
        f'<summary>{_item_summary_grid_html(cells, status)}</summary>'
        f'{_item_details_html(match_row, time_row)}'
        '</details>'
    )


def _item_grid_total_row_html(totals):
    """Integrated TOTAL row aligned to item grid columns."""
    cells = [
        ("TOTAL", False),
        (f"{totals['item_rows']} items", False),
        ("—", False),
        ("—", False),
        (format_number(totals["total_qty"], 0), False),
        ("—", False),
        (format_item_time_total_html(totals["total_base"]), True),
        (format_item_time_total_html(totals["total_load"]), True),
        (format_item_time_total_html(totals["total_unload"]), True),
        (format_item_time_total_html(totals["total_item_time"]), True),
        ("—", False),
    ]
    parts = ['<div class="debug-item-grid ib-total">']
    for text, is_time_total in cells:
        cls = "ib-cell ib-time-total" if is_time_total else "ib-cell"
        if is_time_total:
            parts.append(f'<div class="{cls}">{text}</div>')
        else:
            parts.append(f'<div class="{cls}">{_escape_html(text)}</div>')
    parts.append("</div>")
    return "".join(parts)


def _build_item_breakdown_sheet_html(matching, item_times, totals):
    """Single dense HTML block: header, clickable rows, TOTAL row."""
    parts = [
        _item_breakdown_grid_styles(),
        '<div class="ib-sheet">',
        _item_grid_header_html(),
    ]
    for idx, m in enumerate(matching):
        it = item_times[idx] if idx < len(item_times) else {}
        parts.append(_item_expandable_row_html(m, it, idx))
    parts.append(_item_grid_total_row_html(totals))
    parts.append("</div>")
    return "".join(parts)


def _render_item_breakdown_grid(matching, item_times, item_rows, *, widget_key_prefix: str = ""):
    """Dense spreadsheet-style item breakdown with clickable rows."""
    totals = _compute_item_totals(matching, item_times)

    if item_rows > 50:
        st.warning("Large item list. Showing summary table; full details are available in raw JSON.")
        summary_rows = []
        for idx, m in enumerate(matching):
            it = item_times[idx] if idx < len(item_times) else {}
            cells = _item_row_cells(m, it)
            summary_rows.append({
                "Status": cells[0],
                "Item": cells[1],
                "Matched category": cells[2],
                "Match method": cells[3],
                "Qty": cells[4],
                "Size": cells[5],
                "Base": cells[6],
                "Load": cells[7],
                "Unload": cells[8],
                "Total": cells[9],
                "Note": cells[10],
            })
        st.markdown(_item_breakdown_grid_styles(), unsafe_allow_html=True)
        df_kwargs = {"use_container_width": True, "height": 420, "hide_index": True}
        df_key = _streamlit_widget_key(widget_key_prefix, "item_breakdown_summary_df")
        if df_key:
            df_kwargs["key"] = df_key
        st.dataframe(pd.DataFrame(summary_rows), **df_kwargs)
        st.markdown(
            f'<div class="ib-sheet">{_item_grid_total_row_html(totals)}</div>',
            unsafe_allow_html=True,
        )
        _render_item_breakdown_time_totals_summary(
            {
                "Base": totals["total_base"],
                "Load": totals["total_load"],
                "Unload": totals["total_unload"],
                "Total": totals["total_item_time"],
            },
            widget_key_prefix=widget_key_prefix,
            key_suffix="grid_large",
        )
        return

    if item_rows <= 0:
        st.caption("No item breakdown rows available.")
        return

    st.markdown(_build_item_breakdown_sheet_html(matching, item_times, totals), unsafe_allow_html=True)
    _render_item_breakdown_time_totals_summary(
        {
            "Base": totals["total_base"],
            "Load": totals["total_load"],
            "Unload": totals["total_unload"],
            "Total": totals["total_item_time"],
        },
        widget_key_prefix=widget_key_prefix,
        key_suffix="grid",
    )


def _render_final_total_formula(base_before_gst, gst_amt, backend_total):
    _debug_kv_rows([
        ("Base price before GST", format_money(base_before_gst)),
        ("GST amount", format_money(gst_amt)),
        ("Final total", format_money(backend_total)),
    ])
    b, g, t = _to_float(base_before_gst), _to_float(gst_amt), _to_float(backend_total)
    st.markdown("**Formula:** Final total = base price before GST + GST")
    if b is not None and g is not None and t is not None:
        st.markdown(f"**Example:** {format_money(b)} + {format_money(g)} = {format_money(t)}")
    else:
        st.caption("N/A — some values missing.")


def _render_price_range_formula(calc_pricing, price_min, price_max, min_hours, max_hours):
    base_min = calc_pricing.get("basePriceMin")
    base_max = calc_pricing.get("basePriceMax")
    gst_min = calc_pricing.get("GSTMin")
    gst_max = calc_pricing.get("GSTMax")
    _debug_kv_rows([
        ("basePriceMin", format_money(base_min)),
        ("basePriceMax", format_money(base_max)),
        ("GSTMin", format_money(gst_min)),
        ("GSTMax", format_money(gst_max)),
        ("totalExpectedPriceMin", format_money(price_min)),
        ("totalExpectedPriceMax", format_money(price_max)),
        ("Min hours", format_number(min_hours, 2) if min_hours != "N/A" else "N/A"),
        ("Max hours", format_number(max_hours, 2) if max_hours != "N/A" else "N/A"),
    ])
    st.markdown("**Minimum total = minimum base price + minimum GST**")
    bm, gm, pm = _to_float(base_min), _to_float(gst_min), _to_float(price_min)
    if bm is not None and gm is not None and pm is not None:
        st.markdown(f"**Example:** {format_money(bm)} + {format_money(gm)} = {format_money(pm)}")
    else:
        st.caption("N/A — minimum values missing.")
    st.markdown("**Maximum total = maximum base price + maximum GST**")
    bx, gx, px = _to_float(base_max), _to_float(gst_max), _to_float(price_max)
    if bx is not None and gx is not None and px is not None:
        st.markdown(f"**Example:** {format_money(bx)} + {format_money(gx)} = {format_money(px)}")
    else:
        st.caption("N/A — maximum values missing.")
    if min_hours not in (None, "N/A") and max_hours not in (None, "N/A"):
        st.caption(f"Price range is based on Python's min/max hour range: {min_hours} hr to {max_hours} hr")


def _render_total_time_formula(labor_min, pre_move, travel, total_time_min):
    _debug_kv_rows([
        ("Labor / job minutes", format_minutes(labor_min)),
        ("Pre-move travel", format_minutes(pre_move)),
        ("Travel between locations", format_minutes(travel)),
        ("Total time minutes", format_minutes(total_time_min)),
    ])
    st.markdown("**Formula:** Total time = labor time + pre-move travel + travel between locations")
    l, p, tr, tot = _to_float(labor_min), _to_float(pre_move), _to_float(travel), _to_float(total_time_min)
    if l is not None and p is not None and tr is not None and tot is not None:
        st.markdown(
            f"**Example:** {int(round(l))} min + {int(round(p))} min + {int(round(tr))} min "
            f"= {int(round(tot))} min / {format_minutes(tot)}"
        )
    else:
        st.caption("N/A — some values missing.")


def _render_labor_time_formula(algo, access, movers_used):
    rows = [
        ("totalLaborMinutes", format_minutes(algo.get("totalLaborMinutes"))),
        ("numTasks", format_number(algo.get("numTasks"), 0)),
        ("movers", format_number(algo.get("movers") or movers_used, 0)),
        ("effectiveTeams", format_number(access.get("effectiveTeams") or algo.get("effectiveTeams"), 2)),
        ("effectiveTeamsBeforeElevatorCap", format_number(algo.get("effectiveTeamsBeforeElevatorCap"), 2)),
        ("elevatorCappedTeams", str(algo.get("elevatorCappedTeams", access.get("elevatorCappedTeams", "N/A")))),
        ("bottleneckFactor", format_number(access.get("bottleneckFactor") or algo.get("bottleneckFactor"), 2)),
        ("parallelBaseMinutes", format_minutes(algo.get("parallelBaseMinutes"))),
        ("pickupStairDelta", format_number(access.get("pickupStairDelta") or algo.get("pickupStairDelta"), 3)),
        ("dropoffStairDelta", format_number(access.get("dropoffStairDelta") or algo.get("dropoffStairDelta"), 3)),
        ("stairFrictionMultiplier", format_number(access.get("stairFrictionMultiplier") or algo.get("stairFrictionMultiplier"), 3)),
        ("minutesAfterStairs", format_minutes(algo.get("minutesAfterStairs"))),
        ("elevatorMinutesPickup", format_minutes(access.get("elevatorMinutesPickup") or algo.get("elevatorMinutesPickup"))),
        ("elevatorMinutesDropoff", format_minutes(access.get("elevatorMinutesDropoff") or algo.get("elevatorMinutesDropoff"))),
        ("elevatorMinutesTotal", format_minutes(access.get("elevatorMinutesTotal") or algo.get("elevatorMinutesTotal"))),
        ("jobLaborMinutes", format_minutes(access.get("jobLaborMinutes") or algo.get("jobLaborMinutes"))),
    ]
    _debug_kv_rows(rows)

    total_labor = _to_float(algo.get("totalLaborMinutes"))
    eff = _to_float(access.get("effectiveTeams") or algo.get("effectiveTeams"))
    bottleneck = _to_float(access.get("bottleneckFactor") or algo.get("bottleneckFactor"))
    parallel = _to_float(algo.get("parallelBaseMinutes"))
    stair_mult = _to_float(access.get("stairFrictionMultiplier") or algo.get("stairFrictionMultiplier"))
    after_stairs = _to_float(algo.get("minutesAfterStairs"))
    elev_pickup = _to_float(access.get("elevatorMinutesPickup") or algo.get("elevatorMinutesPickup"))
    elev_dropoff = _to_float(access.get("elevatorMinutesDropoff") or algo.get("elevatorMinutesDropoff"))
    job_labor = _to_float(access.get("jobLaborMinutes") or algo.get("jobLaborMinutes"))

    st.markdown("**Step formulas (Python values):**")
    if total_labor is not None and eff is not None and bottleneck is not None and parallel is not None and eff > 0:
        st.markdown("Parallel base minutes = total item labor minutes ÷ effective teams × bottleneck factor")
        st.markdown(
            f"**Example:** {format_minutes(total_labor)} ÷ {eff} × {bottleneck} "
            f"≈ {format_minutes(parallel)}"
        )
    if after_stairs is not None and parallel is not None and stair_mult is not None:
        st.markdown("Minutes after stairs = parallel base minutes × stair friction multiplier")
        st.markdown(f"**Example:** {format_minutes(parallel)} × {stair_mult} ≈ {format_minutes(after_stairs)}")
    if job_labor is not None and after_stairs is not None:
        ep = elev_pickup or 0
        ed = elev_dropoff or 0
        st.markdown("Final labor time = minutes after stairs + pickup elevator minutes + dropoff elevator minutes")
        st.markdown(
            f"**Example:** {format_minutes(after_stairs)} + {int(round(ep))} min + {int(round(ed))} min "
            f"= {format_minutes(job_labor)}"
        )
    elif not any(v is not None for v in (total_labor, parallel, job_labor)):
        st.caption("Some intermediate values are not available in debug data.")


def _render_debug_recalc_controls(default_movers, vehicle_title):
    """Debug-only movers recalculation controls (vehicle read-only)."""
    st.markdown("### Debug Recalculation Controls")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        movers_default = int(st.session_state.get("debug_simulation_movers") or default_movers or 2)
        movers_default = max(2, min(6, movers_default))
        debug_movers = st.number_input(
            "Movers used",
            min_value=2,
            max_value=6,
            value=movers_default,
            step=1,
            key="debug_panel_movers_input",
            help="Debug simulation only. Uses existing forced_movers recalculation path.",
        )
    with c2:
        st.selectbox(
            "Vehicle selected",
            options=["Auto selected"],
            index=0,
            disabled=True,
            key="debug_panel_vehicle_select",
            help="Read-only — Python auto-selects vehicles.",
        )
        st.caption(
            "Vehicle override is not available yet because Python currently auto-selects vehicles."
        )
        if vehicle_title not in (None, "N/A"):
            st.caption(f"Current auto selection: {vehicle_title}")
    with c3:
        b1, b2 = st.columns(2)
        with b1:
            apply_clicked = st.button("Apply Debug Recalculation", key="debug_apply_recalc")
        with b2:
            reset_clicked = st.button("Reset Debug Recalculation", key="debug_reset_recalc")

    if apply_clicked:
        sim = _run_debug_simulation(debug_movers)
        if sim:
            st.session_state.debug_simulation_active = True
            st.session_state.debug_simulation_calculations = sim
            st.session_state.debug_simulation_movers = int(debug_movers)
            st.session_state.debug_simulation_vehicle = None
            st.rerun()
        else:
            st.error("Could not run debug recalculation. Run Analyze Move first.")

    if reset_clicked:
        _reset_debug_simulation()
        st.rerun()


def _version9_gemini_dir() -> str:
    return os.path.join(parent_dir, "Version 9", "Gemini")


def resolve_vision_prompt_text() -> str:
    """Return the exact Gemini vision prompt for the selected item database."""
    gemini_dir = _version9_gemini_dir()
    if gemini_dir not in sys.path:
        sys.path.insert(0, gemini_dir)

    from modules.ai_client import build_vision_prompt
    from modules.calculator import MovingCalculator

    selected_db_path = resolve_item_database_path(st.session_state.selected_db)
    analyzer = st.session_state.get("analyzer")
    if analyzer is not None:
        return build_vision_prompt(analyzer.calculator)

    calculator = MovingCalculator(items_file=selected_db_path)
    return build_vision_prompt(calculator)


def display_vision_prompt_tab(active_version: str, model_name: str) -> None:
    """Show the Version 9 Gemini vision prompt (language and wording)."""
    st.markdown("## Vision prompt")
    st.caption(
        "Exact instructions sent to Gemini when you run **Analyze Move**. "
        "Updates when you change the JSON database in the sidebar."
    )

    db_name = st.session_state.get("selected_db") or "(default database)"
    st.info(
        f"**Version:** {active_version} · **Model:** {model_name} · **Database:** `{db_name}`"
    )

    try:
        prompt_text = resolve_vision_prompt_text()
    except Exception as exc:
        st.error(f"Could not load vision prompt: {exc}")
        return

    words = len(prompt_text.split())
    category_count = prompt_text.count("\n- ")

    m1, m2, m3 = st.columns(3)
    m1.metric("Characters", f"{len(prompt_text):,}")
    m2.metric("Words (approx.)", f"{words:,}")
    m3.metric("Catalog lines", category_count)

    st.warning(
        "Rules 4 and the “Name” bullet above disagree on whether size hints belong in item names. "
        "This is how the prompt is defined today—edit `Version 9/Gemini/modules/ai_client.py` to align them."
    )

    st.text_area(
        "Prompt text",
        value=prompt_text,
        height=560,
        label_visibility="collapsed",
    )

    st.download_button(
        label="Download prompt (.txt)",
        data=prompt_text,
        file_name="gemini_vision_prompt.txt",
        mime="text/plain",
    )


def initialize_analyzer(version_key: str = DEFAULT_VERSION, model_name='gemini-2.5-flash', items_file: str = None):
    """Initialize the analyzer for the chosen version and model"""
    try:
        AnalyzerClass = load_analyzer_class(version_key)
        analyzer = AnalyzerClass(items_file=items_file)
        # Update the model name if different from default
        if model_name != 'gemini-2.5-flash':
            analyzer.model_name = model_name
        analyzer.current_model = model_name
        st.session_state.analyzer = analyzer
        st.session_state.active_version = version_key
        return True
    except Exception as e:
        st.error(f"❌ Failed to initialize analyzer: {e}")
        st.error("Please make sure your GEMINI_API_KEY is set in the .env file")
        return False

def display_metrics(metrics):
    """Display performance metrics in a nice layout"""
    st.markdown("### ⏱️ Performance Metrics")
    
    # Display model info if available
    if 'model_name' in metrics:
        st.info(f"🤖 **AI Model Used:** {metrics['model_name']}")
    
    # Display API method if available
    if 'api_method' in metrics:
        st.success(f"🔧 **API Method:** File API (single call for all media files)")
    
    # Display Total Elapsed Time (Wall Clock)
    if 'total_elapsed_time' in metrics:
        st.warning(f"🕒 **Total Elapsed Time:** {metrics['total_elapsed_time']:.2f}s (Wall Clock)")
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="File Analysis Time",
            value=f"{metrics.get('file_analysis_time', 0):.2f}s"
        )
    
    with col2:
        st.metric(
            label="Calculation Time",
            value=f"{metrics.get('calculation_time', 0):.2f}s"
        )
    
    with col3:
        st.metric(
            label="Total Processing Time",
            value=f"{metrics.get('total_time', 0):.2f}s"
        )
    
    with col4:
        st.metric(
            label="API Calls",
            value=f"{metrics.get('api_calls', 0)} (all files)"
        )
    
    # Display media file counts if available
    if 'images_processed' in metrics or 'videos_processed' in metrics:
        st.markdown("---")
        col5, col6 = st.columns(2)
        
        with col5:
            st.metric(
                label="📸 Images Processed",
                value=metrics.get('images_processed', 0)
            )
        
        with col6:
            st.metric(
                label="📹 Videos Processed",
                value=metrics.get('videos_processed', 0)
            )

def recalculate_logistics(edited_df, original_items):
    """Recalculate logistics based on edited dataframe"""
    try:
        updated_items = []
        for index, row in edited_df.iterrows():
            # Find original item to preserve other properties
            if index < len(original_items):
                original = original_items[index]
                updated_item = original.copy()
                updated_item['disassemble'] = row['Disassemble']
                updated_items.append(updated_item)
        
        # Access calculator from session state
        analyzer = st.session_state.analyzer
        
        # We need access info for recalculation - get from session state or UI widgets?
        # Since we are inside a callback/function, accessing UI widgets might be tricky if not in session state.
        # But wait, we passed pickup_access etc to process_moving_request.
        # Let's retrieve them from the previous calculations if stored, or we need to pass them in.
        # Easier approach: Just run the calculator here if we have the inputs.
        
        # Re-construct access info from current UI state
        pickup_access = {
            'type': st.session_state.get('pickup_type', 'ground'),
            'floors': st.session_state.get('pickup_floors', 0)
        }
        dropoff_access = {
            'type': st.session_state.get('dropoff_type', 'ground'),
            'floors': st.session_state.get('dropoff_floors', 0)
        }
        # Travel time from widget is not in session state by default unless key is set?
        # We didn't set key for travel_time input. Let's fix that in the UI part first?
        # Actually travel_time widget returns value, but here we are in a function called presumably during rerun.
        
        # NOTE: For simplicity, we will assume the main script runs, detects changes in data_editor, and calls this.
        # So we just return the updated items list, and let the main script handle recalculation?
        # Or better: data_editor returns the edited DF. We process it in the main flow.
        pass
    except Exception as e:
        st.error(f"Error recalculating: {e}")

def display_interactive_breakdown(items, *, widget_key_prefix: str = ""):
    """Display items in an interactive table with time breakdown"""
    st.markdown("### ⏱️ Time Breakdown & Disassembly")
    st.caption("✏️ Edit quantity (or set to 0 to remove item) | ☑️ Check 'Disassemble' to include disassembly time")
    
    if not items:
        st.warning("No items detected")
        return None

    editor_key = _streamlit_widget_key(widget_key_prefix, "items_editor") or "items_editor"
    apply_key = _streamlit_widget_key(widget_key_prefix, "apply_item_changes") or "apply_item_changes"
    
    # Create DataFrame for display
    items_data = []
    for item in items:
        items_data.append({
            'Disassemble': item.get('disassemble', False),
            'Name': item.get('name', 'Unknown'),
            'Qty': item.get('quantity', 1),
            'Category': item.get('category', 'Unknown'),
            'Size': item.get('size', 'Unknown'),
            'Load Time (min)': f"{item.get('loadTime', 0):.1f}",
            'Unload Time (min)': f"{item.get('unloadTime', 0):.1f}",
            'Disassembly Time': item.get('disassemblyTime', 'N/A'),
            'Time/Item (min)': f"{item.get('timePerItem', 0):.1f}", 
            'Total Time (min)': f"{item.get('totalTime', 0):.1f}",
            'Details': item.get('breakdown', ''),
            'Can Disassemble': item.get('can_disassemble', False), # Hidden column for config
            '_original_index': items.index(item) # Keep track
        })
    
    df = pd.DataFrame(items_data)
    
    # Configure columns - Qty is now EDITABLE
    column_config = {
        "Disassemble": st.column_config.CheckboxColumn(
            "Disassemble?",
            help="Check to include disassembly time/cost",
            default=False
        ),
        "Name": st.column_config.TextColumn("Item Name", disabled=True),
        "Qty": st.column_config.NumberColumn(
            "Qty",
            disabled=False,  # ENABLE EDITING
            min_value=0,
            max_value=100,
            step=1,
            help="Edit quantity or set to 0 to remove item"
        ),
        "Category": st.column_config.TextColumn("Category", disabled=True),
        "Size": st.column_config.TextColumn("Size", disabled=True),
        "Load Time (min)": st.column_config.TextColumn("Load Time", disabled=True),
        "Unload Time (min)": st.column_config.TextColumn("Unload Time", disabled=True),
        "Disassembly Time": st.column_config.TextColumn("Disassembly Time", disabled=True),
        "Time/Item (min)": st.column_config.TextColumn("Time/Item", disabled=True),
        "Total Time (min)": st.column_config.TextColumn("Total Time", disabled=True),
        "Details": st.column_config.TextColumn("Breakdown Details", width="large", disabled=True),
        "Can Disassemble": None,
        "_original_index": None,
    }
    
    edited_df = st.data_editor(
        df,
        column_config=column_config,
        disabled=["Name", "Category", "Size", "Load Time (min)", "Unload Time (min)", "Disassembly Time", "Time/Item (min)", "Total Time (min)", "Details"],
        hide_index=True,
        key=editor_key,
        use_container_width=True
    )
    
    # Detect changes (Disassemble flag and/or Qty changes)
    has_changes = False
    if st.session_state.get(editor_key):
        edited_rows = st.session_state[editor_key].get('edited_rows', {})
        if edited_rows:
            has_changes = True
    
    # Show indicator if there are unsaved changes
    if has_changes:
        st.info("📝 You have unsaved changes. Click **Apply Changes**, then **Analyze Move** to refresh the quote.")
    
    # Add "Apply Changes" button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        apply_clicked = st.button(
            "✅ Apply Changes",
            type="primary",
            use_container_width=True,
            key=apply_key,
        )
    
    with col2:
        st.caption("Then click **Analyze Move** in the sidebar to refresh time, pricing, and logistics")
    
    # Process changes when "Apply Changes" is clicked
    if apply_clicked:
        try:
            updated_items_list = []
            changes_detected = False
            validation_errors = []
            
            for index, row in edited_df.iterrows():
                original_index = int(row['_original_index'])
                original_item = items[original_index]
                
                # Validate quantity
                try:
                    new_qty = int(row['Qty'])
                    if new_qty < 0:
                        validation_errors.append(f"❌ {row['Name']}: Quantity cannot be negative")
                        continue
                except (ValueError, TypeError):
                    validation_errors.append(f"❌ {row['Name']}: Quantity must be a whole number")
                    continue
                
                # Skip items with Qty=0 (user deleted them)
                if new_qty == 0:
                    changes_detected = True
                    continue  # Don't add to updated_items_list
                
                # Handle disassemble flag
                should_disassemble = row['Disassemble']
                if not row['Can Disassemble'] and should_disassemble:
                    should_disassemble = False
                
                # Check if quantity or disassemble flag changed
                if new_qty != original_item.get('quantity', 1) or should_disassemble != original_item.get('disassemble', False):
                    changes_detected = True
                
                # Create updated copy
                new_item = original_item.copy()
                new_item['quantity'] = new_qty
                new_item['disassemble'] = should_disassemble
                updated_items_list.append(new_item)
            
            # Show validation errors if any
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
                st.warning("⚠️ Please fix errors above before applying changes")
                return None
            
            # Check if we have at least one item left
            if len(updated_items_list) == 0:
                st.error("❌ Cannot remove all items. Please keep at least one item in the list.")
                return None
            
            if changes_detected:
                st.success("✅ Changes saved. Click **Analyze Move** to refresh logistics.")
                return updated_items_list
            else:
                st.info("ℹ️ No changes detected.")
                return None
                
        except Exception as e:
            st.error(f"❌ Error processing changes: {e}")
            return None
    
    # Check for disassemble-only changes (keep old behavior for backward compatibility)
    if st.session_state.get(editor_key):
        edited_rows = st.session_state[editor_key].get('edited_rows', {})
        if edited_rows and not apply_clicked:
            # Only process disassemble changes if Apply Changes wasn't clicked
            # This allows disassemble to work without explicit button (for now)
            # But with Apply Changes button, we prefer explicit action
            pass
    
    return None

def display_logistics_summary(calculations):
    """Display logistics summary"""
    st.markdown("### 🚛 Moving Logistics Summary")
    
    # Vehicle and Workers
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Vehicle Information")
        material = calculations.get('material', {})
        vehicles = material.get('vehicles', [])
        
        if vehicles:
            if len(vehicles) == 1:
                # Single vehicle
                vehicle = vehicles[0]
                st.info(f"**Vehicle:** {vehicle.get('quantity', 1)}x {vehicle.get('title', 'Unknown')}")
                st.caption(f"Volume: {vehicle.get('volumeUtilization', 0)}% | Weight: {vehicle.get('weightUtilization', 0)}%")
            else:
                # Multi-vehicle solution
                st.info("**Multi-Vehicle Solution:**")
                for idx, vehicle in enumerate(vehicles, 1):
                    st.write(f"{idx}. {vehicle.get('quantity', 1)}x {vehicle.get('title', 'Unknown')}")
                    st.caption(f"   Vol: {vehicle.get('volumeUtilization', 0)}% | Weight: {vehicle.get('weightUtilization', 0)}%")
            
            st.caption(material.get('vehicleReason', 'N/A'))
    
    with col2:
        st.markdown("#### Crew Size")
        workers = calculations.get('material', {}).get('numberOfWorkers', 0)
        st.info(f"**Number of Movers:** {workers}")
        st.caption(calculations.get('material', {}).get('workersReason', 'N/A'))
    
    # Volume and Weight
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("#### Volume")
        volume = calculations.get('volume', {})
        st.write(f"Total: **{volume.get('totalCubicFeet', 0)} cu ft**")
        st.write(f"With Buffer: **{volume.get('withBuffer', 0)} cu ft**")
    
    with col4:
        st.markdown("#### Weight")
        weight = calculations.get('weight', {})
        st.write(f"Total: **{weight.get('totalPounds', 0)} lbs**")
        st.write(f"With Buffer: **{weight.get('withBuffer', 0)} lbs**")

def display_time_estimate(calculations, *, widget_key_prefix: str = ""):
    """Display time estimate breakdown"""
    st.markdown("### ⏰ Time Estimate")
    
    time_info = calculations.get('time', {})
    breakdown = time_info.get('algorithmBreakdown')
    if breakdown:
        st.caption(
            "How the four time buckets add up for this job—stairs multiply total labor; "
            "elevator adds trip minutes on top."
        )
    render_time_algorithm_breakdown(time_info)
    if breakdown:
        with _debug_expander(
            "Step numbers",
            widget_key_prefix=widget_key_prefix,
            key_name="time_step_numbers",
            expanded=False,
        ):
            st.table(
                [{"Step": k, "Value": v} for k, v in breakdown_step_rows(breakdown).items()]
            )
    st.markdown("---")
    
    # Time breakdown
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Pre-Move Travel", f"{time_info.get('preMoveTravel', 0)} min", help="Fixed 30-minute travel fee")
    
    with col2:
        st.metric("Loading Time", f"{time_info.get('loadingTime', 0)} min")
    
    with col3:
        st.metric("Driving Time", f"{time_info.get('travelBetweenLocations', 0)} min", help="Time to drive between locations (User Input)")
    
    with col4:
        st.metric("Unloading Time", f"{time_info.get('unloadingTime', 0)} min")
    
    # Total time
    st.markdown("---")
    col5, col6 = st.columns(2)
    
    with col5:
        st.success(f"**Total Time:** {time_info.get('totalHours', 0):.2f} hours ({time_info.get('totalMinutes', 0)} minutes)")
    
    with col6:
        st.info(f"**Estimated Range:** {time_info.get('estimatedRange', 'N/A')}")

def display_pricing(calculations):
    """Display pricing breakdown"""
    st.markdown("### 💰 Pricing Breakdown")
    
    pricing = calculations.get('pricing', {})
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write(f"**Base Price:** ${pricing.get('basePriceMin', 0):.2f} - ${pricing.get('basePriceMax', 0):.2f}")
        st.write(f"**GST (5%):** ${pricing.get('GSTMin', 0):.2f} - ${pricing.get('GSTMax', 0):.2f}")
        st.caption(pricing.get('breakdown', 'N/A'))
    
    with col2:
        st.success(f"## ${pricing.get('totalExpectedPriceMin', 0):.2f} - ${pricing.get('totalExpectedPriceMax', 0):.2f}")
        st.caption("Total Expected Price (range)")


def render_result_overview_tab(result, *, include_metrics: bool = True):
    """Original Overview tab layout."""
    st.markdown("## 📊 Move Overview")

    summary = result.get("summary", {})
    if summary:
        st.info(
            f"**📦 Total Items:** {summary.get('totalItems', 0)} | "
            f"**📦 Total Boxes:** {summary.get('totalBoxes', 0)} | "
            f"**🏠 Clutter Level:** {summary.get('clutterLevel', 'Unknown').title()}"
        )
        if summary.get("notes"):
            st.caption(f"📝 Notes: {summary.get('notes')}")
        st.markdown("---")

    calculations = result.get("calculations", {})
    col1, col2, col3 = st.columns(3)

    with col1:
        calc_items = calculations.get("items", [])
        total_items = sum(item.get("quantity", 1) for item in calc_items)
        st.metric("Total Items", total_items)

    with col2:
        time_info = calculations.get("time", {})
        st.metric("Total Time", f"{time_info.get('totalHours', 0):.2f} hrs")

    with col3:
        pricing = calculations.get("pricing", {})
        st.metric(
            "Total Price",
            f"${pricing.get('totalExpectedPriceMin', 0):.2f} - "
            f"${pricing.get('totalExpectedPriceMax', 0):.2f}",
        )

    st.markdown("---")

    if calculations:
        display_logistics_summary(calculations)

    if include_metrics:
        metrics = result.get("metrics", {})
        if metrics:
            st.markdown("---")
            st.markdown("### ⚙️ Engine & performance metrics")
            c1, c2 = st.columns(2)
            c1.metric("Model", metrics.get("model_name", "Unknown"))
            c2.metric("Processing Time", f"{metrics.get('total_processing_time_seconds', 0):.2f}s")
            display_metrics(metrics)


def render_result_time_breakdown_tab(result, *, widget_key_prefix: str = ""):
    """Original Time Breakdown tab layout."""
    calculations = result.get("calculations", {})
    current_items = calculations.get("items", [])

    if current_items:
        display_time_estimate(calculations, widget_key_prefix=widget_key_prefix)
        st.markdown("---")
        updated_items = display_interactive_breakdown(
            current_items,
            widget_key_prefix=widget_key_prefix,
        )
        if updated_items:
            st.session_state.detected_items = updated_items
            st.info("📝 Item changes saved. Click **Analyze Move** to refresh the quote.")
    else:
        st.info("No time breakdown available.")


def render_result_logistics_tab(result, *, widget_key_prefix: str = ""):
    """Original Logistics tab layout."""
    calculations = result.get("calculations", {})
    if not calculations:
        return

    material = calculations.get("material", {})
    current_workers = material.get("numberOfWorkers", 2)
    auto_workers = material.get("recommendedWorkers", current_workers)
    cab_seats = material.get("cabSeats", 3)

    slider_key = _streamlit_widget_key(widget_key_prefix, "forced_movers_slider") or "forced_movers_slider"

    st.markdown("#### 👷 Crew Size")
    slider_default = st.session_state.get(slider_key, min(current_workers, 6))
    selected_movers = st.slider(
        "Number of movers",
        min_value=2,
        max_value=6,
        value=int(slider_default),
        step=1,
        key=slider_key,
        help=f"Algorithm recommends {auto_workers} movers. Click Analyze Move to apply.",
    )
    if selected_movers != auto_workers:
        st.caption(f"✏️ Overriding recommendation — algorithm suggests **{auto_workers} movers**")
    else:
        st.caption(f"✅ Using recommended crew size of **{auto_workers} movers**")
    if selected_movers > cab_seats:
        st.caption(
            f"⚠️ {selected_movers} movers — {cab_seats} in truck, "
            f"{selected_movers - cab_seats} follow separately"
        )
    st.caption("Click **Analyze Move** in the sidebar to apply crew size to the quote.")

    st.markdown("---")
    display_logistics_summary(calculations)


def render_result_pricing_tab(result):
    """Original Pricing tab layout."""
    calculations = result.get("calculations", {})
    if calculations:
        display_pricing(calculations)


def format_minutes(value):
    """Format minutes as 'N min / X hr Y min'."""
    if value is None or value == "N/A":
        return "N/A"
    try:
        mins = float(value)
    except (TypeError, ValueError):
        return "N/A"
    hrs = int(mins // 60)
    rem = int(round(mins % 60))
    if hrs > 0:
        return f"{int(round(mins))} min / {hrs} hr {rem} min"
    return f"{int(round(mins))} min"


def format_money(value):
    """Format a numeric value as currency."""
    if value is None or value == "N/A":
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def format_number(value, decimals=1):
    """Format a number with optional decimals."""
    if value is None or value == "N/A":
        return "N/A"
    try:
        if decimals == 0:
            return f"{int(round(float(value))):,}"
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def safe_get(obj, path, default="N/A"):
    """Safely traverse nested dict/list paths like 'pricing.finalTotalExpectedPrice'."""
    if obj is None:
        return default
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError, TypeError):
                return default
        else:
            return default
        if current is None:
            return default
    return current if current is not None else default


def _escape_html(text):
    """Escape dynamic text before embedding in HTML blocks."""
    if text is None:
        return "N/A"
    return html.escape(str(text), quote=True)


def _streamlit_widget_key(widget_key_prefix: str, name: str) -> Optional[str]:
    """Build a unique Streamlit widget key for comparison sections."""
    if not widget_key_prefix:
        return None
    return f"{widget_key_prefix}{name}"


def _debug_expander(label: str, *, widget_key_prefix: str = "", key_name: str, expanded: bool = False):
    """Expander with optional source-prefixed key to avoid duplicate widget IDs."""
    kwargs = {"expanded": expanded}
    widget_key = _streamlit_widget_key(widget_key_prefix, key_name)
    if widget_key:
        kwargs["key"] = widget_key
    return st.expander(label, **kwargs)


def _debug_panel_styles():
    """Scoped CSS for Debug Panel cards and Quote Summary expandable cards."""
    return (
        "<style>"
        ".debug-metric-card{background:rgba(22,8,46,0.85);border:3px solid #00fff9;"
        "border-radius:2px;padding:0.65rem 0.75rem;margin:0.4rem 0;min-height:64px;"
        "box-shadow:inset 0 0 20px rgba(0,255,249,0.06),4px 4px 0 rgba(0,0,0,0.4);"
        "font-family:'VT323',monospace;}"
        ".debug-card-label{font-size:1.05rem;color:#8899aa;line-height:1.2;}"
        ".debug-card-value{font-size:1.5rem;color:#ffd93d;line-height:1.25;margin-top:2px;}"
        ".debug-card-note{font-size:0.9rem;color:#8899aa;margin-top:4px;}"
        ".debug-qs-card{margin:0.4rem 0;min-width:0;max-width:100%;}"
        ".debug-qs-card summary{list-style:none;cursor:pointer;margin:0;padding:0;}"
        ".debug-qs-card summary::-webkit-details-marker{display:none;}"
        ".debug-qs-card summary::marker{content:'';}"
        ".debug-qs-card .debug-qs-card-face{margin:0;}"
        ".debug-qs-card[open] .debug-qs-card-face{border-bottom:1px solid rgba(0,255,249,0.22);"
        "border-radius:2px 2px 0 0;}"
        ".debug-qs-card-body{padding:0.55rem 0.75rem 0.65rem;background:rgba(14,5,30,0.92);"
        "border:3px solid #00fff9;border-top:none;border-radius:0 0 2px 2px;"
        "font-family:'VT323',monospace;font-size:1rem;color:#e8f4ff;"
        "box-shadow:inset 0 0 16px rgba(0,255,249,0.04);"
        "min-width:0;max-width:100%;overflow-x:auto;box-sizing:border-box;}"
        ".qs-kv-wrap{max-width:100%;overflow-x:auto;}"
        ".qs-kv-table{width:100%;max-width:100%;table-layout:fixed;border-collapse:collapse;"
        "margin:0 0 0.45rem;font-size:0.98rem;}"
        ".qs-kv-table th,.qs-kv-table td{padding:3px 8px;border:1px solid rgba(0,255,249,0.18);"
        "text-align:left;white-space:normal;vertical-align:top;"
        "word-break:break-word;overflow-wrap:anywhere;}"
        ".qs-kv-table th:first-child,.qs-kv-table td:first-child{width:58%;}"
        ".qs-kv-table th:last-child,.qs-kv-table td:last-child{width:42%;}"
        ".qs-kv-table th{background:rgba(0,70,110,0.45);color:#00fff9;}"
        ".qs-detail-line{margin:0.2rem 0;line-height:1.35;white-space:normal;"
        "word-break:break-word;overflow-wrap:anywhere;}"
        ".qs-detail-line strong{font-weight:normal;color:#ffd93d;}"
        ".qs-detail-caption{margin:0.25rem 0;color:#8899aa;font-size:0.95rem;}"
        ".qs-warn-item{margin:0.15rem 0;color:#ffd93d;font-size:0.95rem;}"
        "</style>"
    )


def _debug_kv_table_html(rows):
    """HTML table version of _debug_kv_rows for expandable debug cards."""
    if not rows:
        return '<div class="qs-detail-caption">No values available.</div>'
    parts = [
        '<div class="qs-kv-wrap"><table class="qs-kv-table">'
        '<thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>'
    ]
    for label, value in rows:
        parts.append(
            f"<tr><td>{_escape_html(label)}</td><td>{_escape_html(value)}</td></tr>"
        )
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _debug_detail_line_html(text, bold=False):
    """One escaped detail line for Quote Summary card bodies."""
    safe = _escape_html(text)
    if bold:
        return f'<div class="qs-detail-line"><strong>{safe}</strong></div>'
    return f'<div class="qs-detail-line">{safe}</div>'


def _final_total_formula_html(base_before_gst, gst_amt, backend_total):
    rows = [
        ("Base price before GST", format_money(base_before_gst)),
        ("GST amount", format_money(gst_amt)),
        ("Final total", format_money(backend_total)),
    ]
    parts = [_debug_kv_table_html(rows), _debug_detail_line_html("Formula: Final total = base price before GST + GST", bold=True)]
    b, g, t = _to_float(base_before_gst), _to_float(gst_amt), _to_float(backend_total)
    if b is not None and g is not None and t is not None:
        parts.append(_debug_detail_line_html(
            f"Example: {format_money(b)} + {format_money(g)} = {format_money(t)}", bold=True
        ))
    else:
        parts.append('<div class="qs-detail-caption">N/A — some values missing.</div>')
    return "".join(parts)


def _price_range_formula_html(calc_pricing, price_min, price_max, min_hours, max_hours):
    base_min = calc_pricing.get("basePriceMin")
    base_max = calc_pricing.get("basePriceMax")
    gst_min = calc_pricing.get("GSTMin")
    gst_max = calc_pricing.get("GSTMax")
    rows = [
        ("basePriceMin", format_money(base_min)),
        ("basePriceMax", format_money(base_max)),
        ("GSTMin", format_money(gst_min)),
        ("GSTMax", format_money(gst_max)),
        ("totalExpectedPriceMin", format_money(price_min)),
        ("totalExpectedPriceMax", format_money(price_max)),
        ("Min hours", format_number(min_hours, 2) if min_hours != "N/A" else "N/A"),
        ("Max hours", format_number(max_hours, 2) if max_hours != "N/A" else "N/A"),
    ]
    parts = [
        _debug_kv_table_html(rows),
        _debug_detail_line_html("Minimum total = minimum base price + minimum GST", bold=True),
    ]
    bm, gm, pm = _to_float(base_min), _to_float(gst_min), _to_float(price_min)
    if bm is not None and gm is not None and pm is not None:
        parts.append(_debug_detail_line_html(
            f"Example: {format_money(bm)} + {format_money(gm)} = {format_money(pm)}", bold=True
        ))
    else:
        parts.append('<div class="qs-detail-caption">N/A — minimum values missing.</div>')
    parts.append(_debug_detail_line_html("Maximum total = maximum base price + maximum GST", bold=True))
    bx, gx, px = _to_float(base_max), _to_float(gst_max), _to_float(price_max)
    if bx is not None and gx is not None and px is not None:
        parts.append(_debug_detail_line_html(
            f"Example: {format_money(bx)} + {format_money(gx)} = {format_money(px)}", bold=True
        ))
    else:
        parts.append('<div class="qs-detail-caption">N/A — maximum values missing.</div>')
    if min_hours not in (None, "N/A") and max_hours not in (None, "N/A"):
        parts.append(
            '<div class="qs-detail-caption">'
            f'Price range is based on Python\'s min/max hour range: {min_hours} hr to {max_hours} hr'
            '</div>'
        )
    return "".join(parts)


def _total_time_formula_html(labor_min, pre_move, travel, total_time_min):
    rows = [
        ("Labor / job minutes", format_minutes(labor_min)),
        ("Pre-move travel", format_minutes(pre_move)),
        ("Travel between locations", format_minutes(travel)),
        ("Total time minutes", format_minutes(total_time_min)),
    ]
    parts = [
        _debug_kv_table_html(rows),
        _debug_detail_line_html(
            "Formula: Total time = labor time + pre-move travel + travel between locations", bold=True
        ),
    ]
    l, p, tr, tot = _to_float(labor_min), _to_float(pre_move), _to_float(travel), _to_float(total_time_min)
    if l is not None and p is not None and tr is not None and tot is not None:
        parts.append(_debug_detail_line_html(
            f"Example: {int(round(l))} min + {int(round(p))} min + {int(round(tr))} min "
            f"= {int(round(tot))} min / {format_minutes(tot)}",
            bold=True,
        ))
    else:
        parts.append('<div class="qs-detail-caption">N/A — some values missing.</div>')
    return "".join(parts)


def _labor_time_formula_html(algo, access, movers_used):
    rows = [
        ("totalLaborMinutes", format_minutes(algo.get("totalLaborMinutes"))),
        ("numTasks", format_number(algo.get("numTasks"), 0)),
        ("movers", format_number(algo.get("movers") or movers_used, 0)),
        ("effectiveTeams", format_number(access.get("effectiveTeams") or algo.get("effectiveTeams"), 2)),
        ("effectiveTeamsBeforeElevatorCap", format_number(algo.get("effectiveTeamsBeforeElevatorCap"), 2)),
        ("elevatorCappedTeams", str(algo.get("elevatorCappedTeams", access.get("elevatorCappedTeams", "N/A")))),
        ("bottleneckFactor", format_number(access.get("bottleneckFactor") or algo.get("bottleneckFactor"), 2)),
        ("parallelBaseMinutes", format_minutes(algo.get("parallelBaseMinutes"))),
        ("pickupStairDelta", format_number(access.get("pickupStairDelta") or algo.get("pickupStairDelta"), 3)),
        ("dropoffStairDelta", format_number(access.get("dropoffStairDelta") or algo.get("dropoffStairDelta"), 3)),
        ("stairFrictionMultiplier", format_number(access.get("stairFrictionMultiplier") or algo.get("stairFrictionMultiplier"), 3)),
        ("minutesAfterStairs", format_minutes(algo.get("minutesAfterStairs"))),
        ("elevatorMinutesPickup", format_minutes(access.get("elevatorMinutesPickup") or algo.get("elevatorMinutesPickup"))),
        ("elevatorMinutesDropoff", format_minutes(access.get("elevatorMinutesDropoff") or algo.get("elevatorMinutesDropoff"))),
        ("elevatorMinutesTotal", format_minutes(access.get("elevatorMinutesTotal") or algo.get("elevatorMinutesTotal"))),
        ("jobLaborMinutes", format_minutes(access.get("jobLaborMinutes") or algo.get("jobLaborMinutes"))),
    ]
    parts = [_debug_kv_table_html(rows), _debug_detail_line_html("Step formulas (Python values):", bold=True)]

    total_labor = _to_float(algo.get("totalLaborMinutes"))
    eff = _to_float(access.get("effectiveTeams") or algo.get("effectiveTeams"))
    bottleneck = _to_float(access.get("bottleneckFactor") or algo.get("bottleneckFactor"))
    parallel = _to_float(algo.get("parallelBaseMinutes"))
    stair_mult = _to_float(access.get("stairFrictionMultiplier") or algo.get("stairFrictionMultiplier"))
    after_stairs = _to_float(algo.get("minutesAfterStairs"))
    elev_pickup = _to_float(access.get("elevatorMinutesPickup") or algo.get("elevatorMinutesPickup"))
    elev_dropoff = _to_float(access.get("elevatorMinutesDropoff") or algo.get("elevatorMinutesDropoff"))
    job_labor = _to_float(access.get("jobLaborMinutes") or algo.get("jobLaborMinutes"))

    if total_labor is not None and eff is not None and bottleneck is not None and parallel is not None and eff > 0:
        parts.append(_debug_detail_line_html(
            "Parallel base minutes = total item labor minutes ÷ effective teams × bottleneck factor"
        ))
        parts.append(_debug_detail_line_html(
            f"Example: {format_minutes(total_labor)} ÷ {eff} × {bottleneck} ≈ {format_minutes(parallel)}",
            bold=True,
        ))
    if after_stairs is not None and parallel is not None and stair_mult is not None:
        parts.append(_debug_detail_line_html(
            "Minutes after stairs = parallel base minutes × stair friction multiplier"
        ))
        parts.append(_debug_detail_line_html(
            f"Example: {format_minutes(parallel)} × {stair_mult} ≈ {format_minutes(after_stairs)}",
            bold=True,
        ))
    if job_labor is not None and after_stairs is not None:
        ep = elev_pickup or 0
        ed = elev_dropoff or 0
        parts.append(_debug_detail_line_html(
            "Final labor time = minutes after stairs + pickup elevator minutes + dropoff elevator minutes"
        ))
        parts.append(_debug_detail_line_html(
            f"Example: {format_minutes(after_stairs)} + {int(round(ep))} min + {int(round(ed))} min "
            f"= {format_minutes(job_labor)}",
            bold=True,
        ))
    elif not any(v is not None for v in (total_labor, parallel, job_labor)):
        parts.append('<div class="qs-detail-caption">Some intermediate values are not available in debug data.</div>')
    return "".join(parts)


def render_debug_expandable_card(label, value, detail_html):
    """Render a boxed expandable debug card matching Cost Formula card style."""
    safe_label = _escape_html(label)
    safe_value = _escape_html(value)
    return (
        f'<details class="debug-qs-card">'
        f'<summary><div class="debug-metric-card debug-qs-card-face">'
        f'<div class="debug-card-label">{safe_label}</div>'
        f'<div class="debug-card-value">{safe_value}</div>'
        f'</div></summary>'
        f'<div class="debug-qs-card-body">{detail_html}</div>'
        f'</details>'
    )


def render_debug_card(label, value, note=None):
    """Render a compact debug summary card as one complete HTML block."""
    safe_label = _escape_html(label)
    safe_value = _escape_html(value)
    note_block = ""
    if note:
        note_block = f'<div class="debug-card-note">{_escape_html(note)}</div>'
    card_html = (
        f'<div class="debug-metric-card">'
        f'<div class="debug-card-label">{safe_label}</div>'
        f'<div class="debug-card-value">{safe_value}</div>'
        f'{note_block}'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _status_pill_kind(value, kind=None):
    if kind is not None:
        return kind
    if value in (True, "yes", "Yes", "YES"):
        return "yes"
    if value in (False, "no", "No", "NO"):
        return "no"
    if value in ("warning", "Warning", "fallback", "Fallback"):
        return "warning"
    return "neutral"


def render_status_pill(value, kind=None):
    """Return escaped status pill HTML for embedding in a full markdown block."""
    kind = _status_pill_kind(value, kind)
    colors = {
        "yes": ("#00ff88", "#003322"),
        "no": ("#8899aa", "#1a1030"),
        "warning": ("#ffd93d", "#332200"),
        "neutral": ("#00fff9", "#0a2040"),
    }
    fg, bg = colors.get(kind, colors["neutral"])
    display = str(value) if value not in (True, False) else ("Yes" if value else "No")
    safe_display = _escape_html(display)
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:2px;'
        f'background:{bg};color:{fg};border:1px solid {fg};font-size:0.95rem;">'
        f'{safe_display}</span>'
    )


def render_status_line(label, value, kind=None):
    """Render a label plus status pill in one complete HTML block."""
    safe_label = _escape_html(label)
    pill = render_status_pill(value, kind=kind)
    line_html = (
        f'<div style="margin:0.35rem 0;">'
        f'<span style="color:#8899aa;">{safe_label}:</span> {pill}'
        f'</div>'
    )
    st.markdown(line_html, unsafe_allow_html=True)


def _debug_kv_rows(rows):
    """Render key/value rows as a simple markdown table."""
    if not rows:
        st.caption("No values available.")
        return
    lines = ["| Field | Value |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    st.markdown("\n".join(lines))


def display_calculation_debug_panel(
    result,
    *,
    comparison_meta=None,
    enable_debug_simulation=True,
    widget_key_prefix: str = "",
):
    """Display read-only calculation debug panel with collapsible sections."""
    original_calculations = result.get("calculations", {}) if result else {}
    if (
        enable_debug_simulation
        and st.session_state.get("debug_simulation_active")
        and st.session_state.get("debug_simulation_calculations")
    ):
        calculations = st.session_state.debug_simulation_calculations
    else:
        calculations = original_calculations

    debug = calculations.get("calculationDebug")

    if not debug:
        st.info("No calculation debug data found for this result.")
        return

    pricing = debug.get("pricing", {})
    crew = debug.get("crew", {})
    vehicle = debug.get("vehicle", {})
    catalog = debug.get("catalog", {})
    access = debug.get("access", {})
    matching = debug.get("matching", [])
    item_times = debug.get("itemTimes", [])
    warnings = debug.get("warnings", [])
    calc_pricing = calculations.get("pricing", {})
    calc_material = calculations.get("material", {})
    algo = calculations.get("time", {}).get("algorithmBreakdown", {}) or {}
    metrics = result.get("metrics", {}) if result else {}

    backend_total = safe_get(pricing, "finalTotalExpectedPrice", None)
    if backend_total in (None, "N/A"):
        backend_total = calc_pricing.get("totalExpectedPrice")
    backend_movers = safe_get(crew, "finalMoversUsed", None)
    if backend_movers in (None, "N/A"):
        backend_movers = calc_material.get("numberOfWorkers")

    item_rows = len(matching)
    item_count = sum(int(m.get("quantity", 1)) for m in matching) if matching else 0
    if not item_count:
        calc_items = calculations.get("items", [])
        item_count = sum(int(i.get("quantity", 1)) for i in calc_items)

    total_time_min = safe_get(pricing, "totalTimeMinutes")
    labor_min = safe_get(pricing, "laborMinutes")
    price_min = safe_get(pricing, "totalExpectedPriceMin")
    price_max = safe_get(pricing, "totalExpectedPriceMax")
    vehicle_qty = safe_get(vehicle, "quantity", 0)
    vehicle_title = safe_get(vehicle, "vehicleTitle")
    wage_hr = safe_get(pricing, "wageRatePerHourPerMover")
    wage_min = safe_get(pricing, "wageRatePerMinute")
    movers_used = safe_get(pricing, "moversUsed")
    base_before_gst = safe_get(pricing, "basePriceBeforeGst")
    gst_amt = safe_get(pricing, "gstAmount")
    pre_move = safe_get(pricing, "preMoveTravel")
    travel = safe_get(pricing, "travelTime")
    billable = safe_get(pricing, "totalTimeMinutes")
    min_hours = safe_get(pricing, "minHours")
    max_hours = safe_get(pricing, "maxHours")

    st.markdown("## Quote breakdown debug panel")
    st.caption("Read-only calculation inspection. This does not affect the quote.")
    st.markdown(_debug_panel_styles(), unsafe_allow_html=True)

    if comparison_meta is None and result:
        comparison_meta = result.get("comparison_meta")

    if st.session_state.get("debug_simulation_active") and enable_debug_simulation:
        st.warning("Debug simulation active. This does not change the original quote tabs.")

    if enable_debug_simulation:
        _render_debug_recalc_controls(backend_movers, vehicle_title)

    with _debug_expander(
        "Quote Summary",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_quote_summary",
        expanded=True,
    ):
        q1, q2, q3, q4 = st.columns(4)
        with q1:
            st.markdown(
                render_debug_expandable_card(
                    "Final total",
                    format_money(backend_total),
                    _final_total_formula_html(base_before_gst, gst_amt, backend_total),
                ),
                unsafe_allow_html=True,
            )
        with q2:
            st.markdown(
                render_debug_expandable_card(
                    "Price range",
                    f"{format_money(price_min)} – {format_money(price_max)}",
                    _price_range_formula_html(calc_pricing, price_min, price_max, min_hours, max_hours),
                ),
                unsafe_allow_html=True,
            )
        with q3:
            st.markdown(
                render_debug_expandable_card(
                    "Total time",
                    format_minutes(total_time_min),
                    _total_time_formula_html(labor_min, pre_move, travel, total_time_min),
                ),
                unsafe_allow_html=True,
            )
        with q4:
            st.markdown(
                render_debug_expandable_card(
                    "Labor time",
                    format_minutes(labor_min),
                    _labor_time_formula_html(algo, access, movers_used),
                ),
                unsafe_allow_html=True,
            )

        q5, q6, q7, q8 = st.columns(4)
        with q5:
            movers_detail = (
                _debug_detail_line_html(f"Final movers used: {format_number(backend_movers, 0)}", bold=True)
                + _debug_detail_line_html(
                    f"Recommended movers: {format_number(safe_get(crew, 'autoRecommendedMovers'), 0)}",
                    bold=True,
                )
            )
            st.markdown(
                render_debug_expandable_card(
                    "Movers used",
                    format_number(backend_movers, 0),
                    movers_detail,
                ),
                unsafe_allow_html=True,
            )
        with q6:
            vehicles_detail = (
                _debug_detail_line_html(f"Vehicle quantity: {format_number(vehicle_qty, 0)}", bold=True)
                + _debug_detail_line_html(f"Selected: {vehicle_title}", bold=True)
            )
            st.markdown(
                render_debug_expandable_card(
                    "Vehicles selected",
                    format_number(vehicle_qty, 0),
                    vehicles_detail,
                ),
                unsafe_allow_html=True,
            )
        with q7:
            items_detail = (
                _debug_detail_line_html(f"Total item rows: {item_rows}", bold=True)
                + _debug_detail_line_html(f"Total quantity: {format_number(item_count, 0)}", bold=True)
            )
            st.markdown(
                render_debug_expandable_card(
                    "Item count",
                    format_number(item_count, 0),
                    items_detail,
                ),
                unsafe_allow_html=True,
            )
        with q8:
            if warnings:
                warn_parts = [
                    f'<div class="qs-warn-item">• {_escape_html(w)}</div>' for w in warnings[:5]
                ]
                if len(warnings) > 5:
                    warn_parts.append(
                        f'<div class="qs-detail-caption">… and {len(warnings) - 5} more (see Warnings section)</div>'
                    )
                warnings_detail = "".join(warn_parts)
            else:
                warnings_detail = '<div class="qs-detail-caption">No warnings.</div>'
            st.markdown(
                render_debug_expandable_card(
                    "Warning count",
                    format_number(len(warnings), 0),
                    warnings_detail,
                ),
                unsafe_allow_html=True,
            )

    render_labor_time_bridge_section(
        calculations,
        comparison_meta,
        widget_key_prefix=widget_key_prefix,
    )

    with _debug_expander(
        "Cost Formula",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_cost_formula",
        expanded=False,
    ):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_debug_card("Labor minutes", format_minutes(labor_min))
            render_debug_card("Pre-move travel", format_number(pre_move, 0))
        with c2:
            render_debug_card("Travel between locations", format_number(travel, 0))
            render_debug_card("Total billable minutes", format_minutes(billable))
        with c3:
            render_debug_card("Movers used", format_number(movers_used, 0))
            render_debug_card("Wage rate / hr / mover", format_money(wage_hr))
            render_debug_card("Wage rate / minute", format_money(wage_min))
        with c4:
            render_debug_card("Base price before GST", format_money(base_before_gst))
            render_debug_card("GST", format_money(gst_amt))
            render_debug_card("Final total", format_money(backend_total))
            render_debug_card("Min/max price range", f"{format_money(price_min)} – {format_money(price_max)}")

        with _debug_expander(
            "Show pricing equation",
            widget_key_prefix=widget_key_prefix,
            key_name="debug_pricing_equation",
            expanded=False,
        ):
            if all(v not in (None, "N/A") for v in (billable, movers_used, wage_hr)):
                st.write(
                    f"Base price = total billable minutes / 60 × movers × hourly mover rate "
                    f"({format_minutes(billable)} / 60 × {movers_used} × {format_money(wage_hr)})"
                )
            if base_before_gst not in (None, "N/A") and gst_amt not in (None, "N/A"):
                st.write(f"Final total = base price + GST ({format_money(base_before_gst)} + {format_money(gst_amt)})")

    with _debug_expander(
        "Vehicle / Truck",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_vehicle",
        expanded=False,
    ):
        v1, v2, v3 = st.columns(3)
        with v1:
            render_debug_card("Selected vehicle(s)", safe_get(vehicle, "vehicleTitle"))
            render_debug_card("Vehicle quantity", format_number(vehicle_qty, 0))
            render_debug_card("Vehicle id", safe_get(vehicle, "vehicleId"))
            render_debug_card("Cab seats", format_number(safe_get(vehicle, "cabSeats"), 0))
        with v2:
            render_debug_card("Total volume", f"{format_number(safe_get(vehicle, 'totalVolumeBeforeBuffer'))} cu ft")
            render_debug_card("Volume with buffer", f"{format_number(safe_get(vehicle, 'volumeWithBuffer'))} cu ft")
            render_debug_card("Volume capacity", f"{format_number(safe_get(vehicle, 'maxVolume'))} cu ft")
            render_debug_card("Volume utilization", f"{format_number(safe_get(vehicle, 'volumeUtilization'))}%")
        with v3:
            render_debug_card("Total weight", f"{format_number(safe_get(vehicle, 'totalWeightBeforeBuffer'))} lbs")
            render_debug_card("Weight with buffer", f"{format_number(safe_get(vehicle, 'weightWithBuffer'))} lbs")
            render_debug_card("Weight capacity", f"{format_number(safe_get(vehicle, 'maxWeight'))} lbs")
            render_debug_card("Weight utilization", f"{format_number(safe_get(vehicle, 'weightUtilization'))}%")
        st.caption(f"Vehicle reason: {safe_get(vehicle, 'vehicleReason')}")

    with _debug_expander(
        "Movers / Labor",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_movers_labor",
        expanded=False,
    ):
        m1, m2 = st.columns(2)
        with m1:
            render_debug_card("Final movers used", format_number(safe_get(crew, "finalMoversUsed"), 0))
            render_debug_card("Recommended movers", format_number(safe_get(crew, "autoRecommendedMovers"), 0))
            forced = safe_get(crew, "forcedMoversReceived", None)
            if forced not in (None, "N/A"):
                render_debug_card("Forced movers received", format_number(forced, 0))
            render_status_line("Forced override used", crew.get("forcedOverrideUsed"))
            render_status_line(
                "Final movers exceed cab seats",
                crew.get("finalMoversExceedCabSeats"),
                kind="warning" if crew.get("finalMoversExceedCabSeats") else "no",
            )
            render_debug_card("Cab seats", format_number(safe_get(vehicle, "cabSeats"), 0))
        with m2:
            render_debug_card("Effective teams", format_number(safe_get(access, "effectiveTeams"), 2))
            render_debug_card("Bottleneck factor", format_number(safe_get(access, "bottleneckFactor"), 2))
            render_debug_card("Job labor minutes", format_minutes(safe_get(access, "jobLaborMinutes")))
            render_debug_card("Baseline 2-mover time", format_minutes(safe_get(crew, "baseline2MoverTimeMinutes")))
            render_status_line("Small job flag", crew.get("smallJobFlag"))

        crew_evals = crew.get("autoMoverOptionsEvaluated") or []
        with _debug_expander(
            "Show mover evaluation",
            widget_key_prefix=widget_key_prefix,
            key_name="debug_mover_evaluation",
            expanded=False,
        ):
            if crew_evals:
                eval_df = pd.DataFrame([
                    {
                        "Movers": e.get("movers"),
                        "Labor minutes": e.get("laborMinutes"),
                        "Cost": e.get("laborCost"),
                        "Score": e.get("score"),
                    }
                    for e in crew_evals
                ])
                eval_df_kwargs = {"use_container_width": True, "hide_index": True}
                eval_df_key = _streamlit_widget_key(widget_key_prefix, "mover_eval_df")
                if eval_df_key:
                    eval_df_kwargs["key"] = eval_df_key
                st.dataframe(eval_df, **eval_df_kwargs)
            else:
                st.caption("No mover evaluation data available.")

    with _debug_expander(
        "Company / Catalog / Pricing",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_catalog_pricing",
        expanded=False,
    ):
        cat1, cat2 = st.columns(2)
        with cat1:
            render_debug_card("Catalog filename", safe_get(catalog, "filename"))
            render_debug_card("Category count", format_number(safe_get(catalog, "categoryCount"), 0))
            render_debug_card("Wage rate per mover", f"{format_money(wage_hr)}/hr")
        with cat2:
            render_debug_card("Pricing breakdown", safe_get(pricing, "pricingBreakdown"))
            if metrics.get("model_name"):
                render_debug_card("AI model", metrics.get("model_name"))
            if metrics.get("api_method"):
                render_debug_card("API method", metrics.get("api_method"))
        with _debug_expander(
            "Catalog full path",
            widget_key_prefix=widget_key_prefix,
            key_name="debug_catalog_path",
            expanded=False,
        ):
            st.code(safe_get(catalog, "itemsFilePath", "(unknown)"))

    with _debug_expander(
        "Item Breakdown",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_item_breakdown",
        expanded=False,
    ):
        st.markdown(f"**Total items:** {item_rows}")
        _render_item_breakdown_grid(
            matching, item_times, item_rows, widget_key_prefix=widget_key_prefix
        )

    with _debug_expander(
        "Warnings / Problems",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_warnings",
        expanded=bool(warnings),
    ):
        if warnings:
            for w in warnings:
                st.warning(w)
        else:
            st.success("No debug warnings found.")

    with _debug_expander(
        "Advanced: Raw calculationDebug JSON / Download",
        widget_key_prefix=widget_key_prefix,
        key_name="debug_raw_json",
        expanded=False,
    ):
        st.json(debug)
        download_key = _streamlit_widget_key(widget_key_prefix, "download_calc_debug")
        download_kwargs = {
            "label": "Download calculation_debug.json",
            "data": json.dumps(debug, indent=2),
            "file_name": f"{widget_key_prefix or ''}calculation_debug.json".replace("__", "_"),
            "mime": "application/json",
        }
        if download_key:
            download_kwargs["key"] = download_key
        st.download_button(**download_kwargs)


def display_performance_results(results):
    """Display performance analysis results"""
    st.markdown("## 🧪 Performance Analysis")
    st.caption("Analysis of 5 iterations to measure consistency and performance")
    
    # Extract KPIs from all 5 runs
    perf_data = []
    for i, run in enumerate(results, 1):
        calcs = run.get('calculations', {})
        pricing = calcs.get('pricing', {})
        time_info = calcs.get('time', {})
        metrics = run.get('metrics', {})
        items = calcs.get('items', [])
        
        perf_data.append({
            'Iteration': i,
            'Total Items': sum(item.get('quantity', 1) for item in items),
            'Total Time (hrs)': time_info.get('totalHours', 0),
            'Base Price ($)': pricing.get('basePrice', 0),
            'Total Price ($)': pricing.get('totalExpectedPrice', 0),
            'Processing Time (s)': metrics.get('total_processing_time_seconds', 0),
            'Number of Workers': calcs.get('material', {}).get('numberOfWorkers', 0)
        })
    
    df = pd.DataFrame(perf_data)
    
    # Statistical Summary
    st.markdown("### 📊 Statistical Summary")
    summary_df = pd.DataFrame({
        'Metric': ['Total Items', 'Total Time (hrs)', 'Base Price ($)', 'Total Price ($)', 'Processing Time (s)', 'Number of Workers'],
        'Mean': [
            df['Total Items'].mean(),
            df['Total Time (hrs)'].mean(),
            df['Base Price ($)'].mean(),
            df['Total Price ($)'].mean(),
            df['Processing Time (s)'].mean(),
            df['Number of Workers'].mean()
        ],
        'Std Dev': [
            df['Total Items'].std(),
            df['Total Time (hrs)'].std(),
            df['Base Price ($)'].std(),
            df['Total Price ($)'].std(),
            df['Processing Time (s)'].std(),
            df['Number of Workers'].std()
        ],
        'Min': [
            df['Total Items'].min(),
            df['Total Time (hrs)'].min(),
            df['Base Price ($)'].min(),
            df['Total Price ($)'].min(),
            df['Processing Time (s)'].min(),
            df['Number of Workers'].min()
        ],
        'Max': [
            df['Total Items'].max(),
            df['Total Time (hrs)'].max(),
            df['Base Price ($)'].max(),
            df['Total Price ($)'].max(),
            df['Processing Time (s)'].max(),
            df['Number of Workers'].max()
        ]
    })
    st.dataframe(summary_df, use_container_width=True)
    
    st.markdown("---")
    
    # Line charts for variations
    st.markdown("### 📈 KPI Variations Across Iterations")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Total Items Detected")
        st.line_chart(df.set_index('Iteration')['Total Items'])
        
        st.markdown("#### Base Price ($)")
        st.line_chart(df.set_index('Iteration')['Base Price ($)'])
        
        st.markdown("#### Processing Time (seconds)")
        st.line_chart(df.set_index('Iteration')['Processing Time (s)'])
    
    with col2:
        st.markdown("#### Total Time Required (hours)")
        st.line_chart(df.set_index('Iteration')['Total Time (hrs)'])
        
        st.markdown("#### Total Price ($)")
        st.line_chart(df.set_index('Iteration')['Total Price ($)'])
        
        st.markdown("#### Number of Workers")
        st.line_chart(df.set_index('Iteration')['Number of Workers'])
    
    st.markdown("---")
    
    # Raw data table
    st.markdown("### 📋 Raw Data")
    st.dataframe(df, use_container_width=True)
    
    # Download all performance results
    st.markdown("### 💾 Download Performance Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Download as JSON
        all_results_json = json.dumps(results, indent=2)
        st.download_button(
            label="📥 Download All Results (JSON)",
            data=all_results_json,
            file_name="performance_test_results.json",
            mime="application/json"
        )
    
    with col2:
        # Download statistics as CSV
        csv = summary_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Statistics (CSV)",
            data=csv,
            file_name="performance_statistics.csv",
            mime="text/csv"
        )

def main():
    """Main application"""
    
    # Resolve active version for header
    active_version = st.session_state.get('active_version', DEFAULT_VERSION)
    
    # Header
    st.markdown(f'<h1 class="main-header">Quotetron: {active_version}</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar for inputs
    with st.sidebar:
        st.markdown("## 📋 Moving Details")
        
        # Database selector
        st.markdown("### 🗄️ Item Database")
        db_idx = _item_db_files.index(st.session_state.selected_db) if st.session_state.selected_db in _item_db_files else 0
        selected_db = st.selectbox(
            "Item Database",
            _item_db_files,
            index=db_idx,
            help="Select which item pricing/time database to use for calculations"
        )
        if selected_db != st.session_state.selected_db:
            st.session_state.selected_db = selected_db
            st.session_state.analyzer = None
            clear_analysis_cache()
            st.rerun()

        st.markdown("---")

        # Set default model (no user selection)
        selected_model = 'gemini-2.5-flash'
        
        # File upload (images and/or videos)
        st.markdown("### 📤 Upload Media Files")
        st.caption("Upload images and/or videos of rooms and items")
        
        uploaded_files = st.file_uploader(
            "Drag and drop files here",
            type=['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'heic', 'heif', 'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv', 'm4v'],
            accept_multiple_files=True,
            help="Upload images (.jpg, .png, .heic, etc.) and/or videos (.mp4, .mov, etc.)"
        )
        
        if uploaded_files:
            # Separate images and videos
            image_files = []
            video_files = []
            
            for file in uploaded_files:
                file_ext = os.path.splitext(file.name)[1].lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif']:
                    image_files.append(file)
                elif file_ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']:
                    video_files.append(file)
            
            st.success(f"✅ {len(image_files)} image(s) + {len(video_files)} video(s) uploaded")
            
            # Display image thumbnails
            if image_files:
                st.markdown("**Images:**")
                cols = st.columns(3)
                for idx, uploaded_file in enumerate(image_files):
                    with cols[idx % 3]:
                        try:
                            image = Image.open(uploaded_file)
                        except Exception:
                            # Fallback for HEIC if Image.open fails on stream
                            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                            if file_ext in ['.heic', '.heif'] and 'pillow_heif' in globals():
                                try:
                                    uploaded_file.seek(0)
                                    heif_file = pillow_heif.read_heif(uploaded_file)
                                    image = Image.frombytes(
                                        heif_file.mode,
                                        heif_file.size,
                                        heif_file.data,
                                        "raw",
                                    )
                                except Exception:
                                    st.error(f"Error loading {uploaded_file.name}")
                                    continue
                            else:
                                st.error(f"Error loading {uploaded_file.name}")
                                continue
                                
                        st_image_compat(image, caption=uploaded_file.name)
            
            # Display video info
            if video_files:
                st.markdown("**Videos:**")
                for video_file in video_files:
                    file_size = len(video_file.getvalue()) / (1024 * 1024)  # Size in MB
                    st.info(f"📹 {video_file.name} ({file_size:.2f} MB)")
        
        st.markdown("---")
        
        # Pickup location
        st.markdown("### 🏠 Pickup Location")
        pickup_type = st.selectbox(
            "Access Type",
            options=['ground', 'stairs', 'elevator'],
            key='pickup_type'
        )
        
        pickup_floors = 0
        if pickup_type in ['stairs', 'elevator']:
            pickup_floors = st.number_input(
                "Number of Floors",
                min_value=0,
                max_value=50,
                value=0,
                key='pickup_floors'
            )
        
        st.markdown("---")
        
        # Dropoff location
        st.markdown("### 🏢 Dropoff Location")
        dropoff_type = st.selectbox(
            "Access Type",
            options=['ground', 'stairs', 'elevator'],
            key='dropoff_type'
        )
        
        dropoff_floors = 0
        if dropoff_type in ['stairs', 'elevator']:
            dropoff_floors = st.number_input(
                "Number of Floors",
                min_value=0,
                max_value=50,
                value=0,
                key='dropoff_floors'
            )
        
        st.markdown("---")
        
        # Travel time
        st.markdown("### 🚗 Travel Time")
        st.caption("Enter the driving time between the pickup and dropoff addresses.")
        travel_time = st.number_input(
            "Driving Time (minutes)",
            min_value=5,
            max_value=300,
            value=30,
            key='travel_time',
            help="Estimated driving time between pickup and dropoff locations only."
        )
        
        st.markdown("---")
        
        # Pre-Move Travel
        st.markdown("### 🏁 Pre-Move Travel")
        st.caption("Time for movers to travel from their depot to the pickup location.")
        pre_move_travel = st.number_input(
            "Pre-Move Travel (minutes)",
            min_value=0,
            max_value=180,
            value=30,
            key='pre_move_travel',
            help="One-way travel time from the mover's depot to the pickup address."
        )
        
        st.markdown("---")
        
        # Performance testing settings
        st.markdown("### 🧪 Performance Testing")
        enable_performance_test = st.checkbox(
            "Enable Performance Mode",
            value=st.session_state.enable_performance_test,
            help="Run multiple iterations to gather performance metrics"
        )
        st.session_state.enable_performance_test = enable_performance_test
        
        if enable_performance_test:
            # Dropdown for iterations
            iterations = st.selectbox(
                "Number of Iterations",
                options=[5, 10, 20],
                index=0, # Default to 5
                key='perf_iterations'
            )
            st.session_state.performance_iterations = iterations
            st.warning(f"⚠️ Analysis will run {iterations} times. This will take longer but provides robust metrics.")
        else:
            # Default to 1 if disabled (though logic handled elsewhere)
            st.session_state.performance_iterations = 1
        
        st.markdown("---")
        
        # Analyze button
        analyze_button = st.button("🔍 Analyze Move", use_container_width=True)
    
    tab_analyze, tab_vision_prompt = st.tabs(["Analyze move", "Vision prompt"])

    with tab_vision_prompt:
        display_vision_prompt_tab(active_version, selected_model)

    with tab_analyze:
        _render_analyze_tab(
            active_version=active_version,
            selected_model=selected_model,
            uploaded_files=uploaded_files,
            analyze_button=analyze_button,
            pickup_type=pickup_type,
            pickup_floors=pickup_floors,
            dropoff_type=dropoff_type,
            dropoff_floors=dropoff_floors,
            travel_time=travel_time,
            pre_move_travel=pre_move_travel,
        )


def _render_analyze_tab(
    *,
    active_version: str,
    selected_model: str,
    uploaded_files,
    analyze_button: bool,
    pickup_type: str,
    pickup_floors: int,
    dropoff_type: str,
    dropoff_floors: int,
    travel_time: int,
    pre_move_travel: int,
) -> None:
    """Main quote workflow (uploads and results)."""
    if st.session_state.analyzer is None:
        selected_db_path = resolve_item_database_path(st.session_state.selected_db)
        with st.spinner(f"Initializing {active_version} analyzer with Gemini 2.5 Flash..."):
            if not initialize_analyzer(active_version, selected_model, items_file=selected_db_path):
                st.stop()

    if not uploaded_files and st.session_state.vision_result:
        clear_analysis_cache()

    if analyze_button and uploaded_files:
        import shutil
        upload_fingerprint = hash_uploaded_files(uploaded_files)
        st.session_state.upload_fingerprint = upload_fingerprint

        temp_dir = tempfile.mkdtemp()
        file_paths = []
        try:
            for uploaded_file in uploaded_files:
                file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(file_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                file_paths.append(file_path)

            forced_movers = st.session_state.get('forced_movers_slider')
            logistics_params = build_logistics_params(
                pickup_type, pickup_floors, dropoff_type, dropoff_floors,
                travel_time, pre_move_travel, forced_movers=forced_movers,
            )

            need_vision = will_need_vision(
                upload_fingerprint,
                force_vision=st.session_state.enable_performance_test,
            )
            load_ctx = vision_loading_panel() if need_vision else st.spinner(LOGISTICS_SPINNER_MSG)

            with load_ctx:
                analysis_start_time = time.time()
                analyzer = st.session_state.analyzer

                if st.session_state.enable_performance_test:
                    num_iterations = st.session_state.get('performance_iterations', 5)
                    st.info(f"🧪 Performance Test Mode: Running {num_iterations} iterations...")
                    performance_results = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for iteration in range(num_iterations):
                        status_text.text(f"Running iteration {iteration + 1} of {num_iterations}...")
                        bundle, used_vision = run_analyze_move(
                            analyzer,
                            file_paths,
                            logistics_params,
                            upload_fingerprint=upload_fingerprint,
                            force_vision=(iteration == 0),
                        )
                        if bundle:
                            bundle['metrics']['total_elapsed_time'] = time.time() - analysis_start_time
                            bundle['iteration'] = iteration + 1
                            bundle['used_vision'] = used_vision
                            performance_results.append(bundle)
                        progress_bar.progress((iteration + 1) / num_iterations)

                    status_text.text(f"✅ All {num_iterations} iterations completed!")
                    st.session_state.performance_test_results = performance_results
                    if performance_results:
                        st.session_state.analysis_result = performance_results[0]
                        _store_comparison_results(
                            st.session_state.detected_items,
                            logistics_params,
                            st.session_state.vision_result,
                            performance_results[0].get("metrics"),
                        )
                else:
                    bundle, used_vision = run_analyze_move(
                        analyzer,
                        file_paths,
                        logistics_params,
                        upload_fingerprint=upload_fingerprint,
                    )
                    elapsed_time = time.time() - analysis_start_time
                    if bundle:
                        bundle['metrics']['total_elapsed_time'] = elapsed_time
                        st.session_state.analysis_result = bundle
                        st.session_state.performance_test_results = []
                        if not used_vision:
                            st.session_state.last_run_logistics_only = True
                        _store_comparison_results(
                            st.session_state.detected_items,
                            logistics_params,
                            st.session_state.vision_result,
                            bundle.get("metrics"),
                        )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    elif uploaded_files:
        st.session_state.upload_fingerprint = hash_uploaded_files(uploaded_files)

    # Settings changed banner (no auto-recalc until Analyze Move)
    if st.session_state.logistics_result and st.session_state.logistics_params:
        current_params = build_logistics_params(
            pickup_type, pickup_floors, dropoff_type, dropoff_floors,
            travel_time, pre_move_travel,
            forced_movers=st.session_state.get('forced_movers_slider'),
        )
        if logistics_params_differ(current_params, st.session_state.logistics_params):
            st.warning("⚙️ Settings changed — click **Analyze Move** to update the quote.")

    # Display results
    if st.session_state.analysis_result:
        result = st.session_state.analysis_result
        
        st.markdown('<div class="success-box">✅ Analysis completed successfully!</div>', unsafe_allow_html=True)
        if st.session_state.get('last_run_logistics_only'):
            st.caption("Used cached item detection; Gemini was not called.")
            st.session_state.last_run_logistics_only = False
        
        # Temporary CSV vs JSON comparison panel (see csv_json_compare_panel.py)
        json_comparison = st.session_state.get("json_comparison_result")
        spreadsheet_comparison = st.session_state.get("spreadsheet_comparison_result")
        if json_comparison is None or spreadsheet_comparison is None:
            _store_comparison_results(
                st.session_state.detected_items,
                st.session_state.logistics_params or build_logistics_params(
                    pickup_type, pickup_floors, dropoff_type, dropoff_floors,
                    travel_time, pre_move_travel,
                    forced_movers=st.session_state.get('forced_movers_slider'),
                ),
                st.session_state.vision_result,
                result.get("metrics"),
            )
            json_comparison = st.session_state.json_comparison_result
            spreadsheet_comparison = st.session_state.spreadsheet_comparison_result

        render_csv_json_comparison_sections(
            json_comparison,
            spreadsheet_comparison,
            show_performance=bool(st.session_state.performance_test_results),
            performance_results=st.session_state.performance_test_results,
        )

        st.markdown("---")
            
        # Download results
        st.markdown("### 💾 Download Results")
        
        json_str = json.dumps(result, indent=2)
        st.download_button(
            label="📥 Download JSON Report",
            data=json_str,
            file_name="moving_analysis_result.json",
            mime="application/json"
        )
        

    
    elif not uploaded_files:
        # Show welcome message
        st.info("👈 Upload images/videos and fill in the moving details in the sidebar to begin analysis")
        
        st.markdown("""
        ### 🚀 How to Use:
        
        1. **Upload Media Files**: Drag and drop images and/or videos of the items you want to move
           - **Images**: .jpg, .png, .gif, .bmp, .webp, .tiff, .heic, .heif
           - **Videos**: .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v
        2. **Pickup Location**: Specify access type and number of floors
        3. **Dropoff Location**: Specify access type and number of floors
        4. **Travel Time**: Enter the estimated travel time between locations
        5. **Analyze**: Click the "Analyze Move" button to get your estimate
        
        ### ✨ Features:
        
        - 🤖 AI-powered item detection using Gemini 2.5 Flash with File API
        - 📹 **Video support** - Upload walkthrough videos of rooms
        - 📊 Single API call for all images and videos (efficient and fast)
        - 🚛 Automatic vehicle and crew size recommendations
        - 💰 Comprehensive pricing breakdown
        - 📈 Performance metrics tracking
        - 🎯 Optimized for speed and accuracy

        ### 📹 Video Tips:
        
        - Record 30-60 second walkthroughs of each room
        - Keep camera steady and pan slowly
        - Ensure good lighting for best results
        - MP4 format recommended for fastest processing
        - Mix images and videos for best coverage
        """)

if __name__ == "__main__":
    main()
