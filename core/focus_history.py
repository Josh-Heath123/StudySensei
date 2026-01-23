"""Focus history management with sliding window."""

from collections import deque
from utils.constants import WINDOW_SIZE, TARGET_FPS
import streamlit as st


def update_focus_history(focused: bool, timestamp: float) -> None:
    """
    Update focus history with sliding window.
    
    Args:
        focused: Whether user was focused
        timestamp: Current timestamp
    """
    if "focus_history" not in st.session_state:
        st.session_state.focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    
    st.session_state.focus_history.append((timestamp, focused))
    
    # Calculate 60-second focus percentage
    cutoff = timestamp - WINDOW_SIZE
    valid_samples = [(t, f) for t, f in st.session_state.focus_history if t >= cutoff]
    
    if valid_samples:
        total_frames = len(valid_samples)
        focused_frames = sum(1 for _, f in valid_samples if f)
        st.session_state.focus_pct_60s = (focused_frames / total_frames) * 100.0
    else:
        st.session_state.focus_pct_60s = 0.0
