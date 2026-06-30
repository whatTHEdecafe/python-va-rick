"""
Data contracts for the Version 9 analysis pipeline.

Stages 1-2 (vision): Gemini detects items — no weight/volume/baseTime from the model.
Stage 3 (enrichment): catalog attaches weight, volume, baseTime, category.
Stage 4 (logistics): calculator produces times, crew, trucks, pricing.
"""

from typing import Any, Dict, List, Optional, TypedDict


class VisionResult(TypedDict, total=False):
    """Output of analyze_media (stages 1-2)."""
    items: List[Dict[str, Any]]
    summary: Dict[str, Any]
    metrics: Dict[str, Any]


class LogisticsParams(TypedDict, total=False):
    """Inputs for compute_logistics (stage 4)."""
    pickup_access: Dict[str, Any]
    dropoff_access: Dict[str, Any]
    travel_time: int
    pre_move_travel: int
    forced_movers: Optional[int]


class AnalysisSnapshot(TypedDict, total=False):
    """Full cached state for UI / export."""
    vision_result: VisionResult
    enriched_items: List[Dict[str, Any]]
    logistics_result: Dict[str, Any]
    logistics_params: LogisticsParams
    media_fingerprint: str
