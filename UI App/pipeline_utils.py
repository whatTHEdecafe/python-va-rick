"""Shared helpers for the Streamlit pipeline (no Streamlit import required)."""

import hashlib
from typing import Any, Sequence


def hash_uploaded_files(uploaded_files: Sequence[Any]) -> str:
    """
    Stable fingerprint from upload name + byte length + content hash.
    Ignores temp path and mtime so re-saving the same uploads does not re-trigger Gemini.
    """
    parts = []
    for uf in sorted(uploaded_files, key=lambda f: f.name):
        data = uf.getvalue()
        parts.append(f"{uf.name}:{len(data)}:{hashlib.sha256(data).hexdigest()}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def will_need_vision(upload_fingerprint: str, *, force_vision: bool = False) -> bool:
    """Whether the next analyze run should call Gemini (requires session_state)."""
    import streamlit as st

    return (
        force_vision
        or not st.session_state.get("vision_result")
        or upload_fingerprint != st.session_state.get("media_fingerprint")
    )
