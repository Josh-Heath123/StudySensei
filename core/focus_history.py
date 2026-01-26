"""Focus history management with sliding window."""

from collections import deque
from utils.constants import WINDOW_SIZE, TARGET_FPS
from typing import Optional

# Global focus history (for PyQt compatibility)
_focus_history: Optional[deque] = None
_focus_pct_60s: float = 0.0


def get_focus_history() -> deque:
    """Get or create focus history deque."""
    global _focus_history
    if _focus_history is None:
        _focus_history = deque(maxlen=WINDOW_SIZE * TARGET_FPS)
    return _focus_history


def get_focus_pct_60s() -> float:
    """Get current 60-second focus percentage."""
    return _focus_pct_60s


def reset_focus_history() -> None:
    """Reset focus history (for new session)."""
    global _focus_history, _focus_pct_60s
    _focus_history = None
    _focus_pct_60s = 0.0


def update_focus_history(focused: bool, timestamp: float) -> float:
    """
    Update focus history with sliding window.
    
    Args:
        focused: Whether user was focused
        timestamp: Current timestamp
    
    Returns:
        Current 60-second focus percentage (0-100)
    """
    global _focus_pct_60s
    
    # Try Streamlit first (for backward compatibility)
    try:
        import streamlit as st
        # Check if Streamlit is actually running (has runtime context)
        # This prevents warnings when Streamlit is imported but not running
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            if get_script_run_ctx() is None:
                # Streamlit imported but not running (PyQt mode)
                raise RuntimeError("Streamlit not running")
        except (ImportError, RuntimeError, AttributeError):
            # No runtime context - use PyQt mode
            raise RuntimeError("Streamlit not running")
        
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
            _focus_pct_60s = st.session_state.focus_pct_60s
        else:
            st.session_state.focus_pct_60s = 0.0
            _focus_pct_60s = 0.0
        
        return _focus_pct_60s
    except (ImportError, RuntimeError, AttributeError):
        # PyQt mode - use global state
        focus_history = get_focus_history()
        focus_history.append((timestamp, focused))
        
        # Calculate 60-second focus percentage
        cutoff = timestamp - WINDOW_SIZE
        valid_samples = [(t, f) for t, f in focus_history if t >= cutoff]
        
        if valid_samples:
            total_frames = len(valid_samples)
            focused_frames = sum(1 for _, f in valid_samples if f)
            _focus_pct_60s = (focused_frames / total_frames) * 100.0
        else:
            _focus_pct_60s = 0.0
        
        return _focus_pct_60s
