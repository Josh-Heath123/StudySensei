"""
Memory leak prevention and management for StudySensei.
Handles Streamlit session state cleanup, image cache management, and resource cleanup.
"""

import gc
import time
import streamlit as st
import numpy as np
from typing import List, Set, Optional
from collections import deque

# Optional: psutil for memory monitoring (graceful fallback if not available)
try:
    import psutil
    import os
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# Essential keys that should never be deleted
ESSENTIAL_KEYS: Set[str] = {
    "session_start_time",
    "focus_history",
    "posture_history",
    "video_processor",
    "session_store",
    "analyzer",
    "decay_detector",
    "session_stats",
    "behavior_modeler",
    "break_recommender",
    "ml_predictor",
    "current_session_id",
    "focus_metrics_placeholder",
    "posture_metrics_placeholder",
    "analytics_placeholder",
    "preview_placeholder",
    "preview_caption_placeholder",
    "calibration_placeholder",
    "emotion_placeholder",
    "analytics_section_placeholder",
    "calibration_message_placeholder",
    "enable_analytics_dashboard",
    "last_ui_update",
    "ui_update_interval",
    "ui_error_count",
    "last_image_cleanup",
    "memory_tracker",
    "gc_counter",
    "last_memory_cleanup",
}


def cleanup_session_state(max_items: int = 50) -> int:
    """
    Periodically clean session_state to prevent bloat.
    
    Removes old, non-essential items while preserving critical state.
    
    Args:
        max_items: Maximum number of items to keep in session_state
    
    Returns:
        Number of items removed
    """
    if len(st.session_state) <= max_items:
        return 0
    
    # Initialize memory tracker if needed
    if "memory_tracker" not in st.session_state:
        st.session_state.memory_tracker = {
            "recent": [],
            "last_cleanup": time.time()
        }
    
    # Track recent keys (items accessed in last cleanup cycle)
    tracker = st.session_state.memory_tracker
    current_keys = set(st.session_state.keys())
    
    # Identify old keys to remove (not essential, not recent)
    old_keys = [
        k for k in st.session_state.keys()
        if k not in ESSENTIAL_KEYS
        and k not in tracker.get("recent", [])
        and not k.startswith("_")  # Don't remove private keys
    ]
    
    # Sort by key name (simple heuristic - could be improved with timestamps)
    old_keys.sort()
    
    # Remove oldest items (limit to 10 at a time to avoid disruption)
    items_to_remove = min(10, len(old_keys), len(st.session_state) - max_items)
    removed_count = 0
    
    for key in old_keys[:items_to_remove]:
        try:
            # Check if it's a large object (numpy array, list, etc.)
            value = st.session_state.get(key)
            if isinstance(value, (np.ndarray, list, deque)):
                # Large objects - definitely remove
                del st.session_state[key]
                removed_count += 1
            elif isinstance(value, dict) and len(value) > 100:
                # Large dictionaries - remove
                del st.session_state[key]
                removed_count += 1
            elif value is None:
                # None values - safe to remove
                del st.session_state[key]
                removed_count += 1
        except (KeyError, AttributeError):
            # Key might have been deleted already
            pass
    
    # Update tracker
    tracker["recent"] = list(current_keys - set(old_keys[:items_to_remove]))
    tracker["last_cleanup"] = time.time()
    
    return removed_count


def manage_frame_memory() -> int:
    """
    Prevent frame memory accumulation by clearing old frames.
    
    Returns:
        Number of frames/images cleared
    """
    cleared_count = 0
    
    # Find all frame/image related keys
    frame_keys = [
        k for k in st.session_state.keys()
        if any(term in k.lower() for term in ['frame', 'image', 'preview', 'camera'])
        and k not in ESSENTIAL_KEYS
    ]
    
    # Keep only the current preview_image, clear others
    for key in frame_keys:
        if key != "preview_image":  # Keep current preview
            try:
                value = st.session_state.get(key)
                if isinstance(value, np.ndarray):
                    # Large numpy array - clear it
                    del st.session_state[key]
                    cleared_count += 1
            except (KeyError, AttributeError):
                pass
    
    return cleared_count


def force_garbage_collection(threshold: int = 100) -> bool:
    """
    Force garbage collection periodically to free memory.
    
    Args:
        threshold: Number of calls before triggering GC
    
    Returns:
        True if GC was triggered, False otherwise
    """
    if "gc_counter" not in st.session_state:
        st.session_state.gc_counter = 0
    
    st.session_state.gc_counter += 1
    
    if st.session_state.gc_counter >= threshold:
        # Force garbage collection
        collected = gc.collect()
        st.session_state.gc_counter = 0
        
        # Log if significant memory was freed
        if collected > 0:
            if hasattr(st.session_state, 'ui_error_count'):
                if st.session_state.ui_error_count <= 3:
                    print(f"🧹 Garbage collection: {collected} objects freed")
        
        return True
    
    return False


def monitor_memory_usage() -> Optional[float]:
    """
    Track and log memory usage.
    
    Returns:
        Memory usage in MB, or None if psutil not available
    """
    if not _PSUTIL_AVAILABLE:
        return None
    
    try:
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        # Log warning if memory high
        if memory_mb > 500:  # 500MB threshold
            if hasattr(st.session_state, 'ui_error_count'):
                if st.session_state.ui_error_count <= 3:
                    print(f"⚠️ High memory usage: {memory_mb:.1f}MB - triggering cleanup")
            
            # Trigger aggressive cleanup
            cleanup_session_state(max_items=30)  # More aggressive
            manage_frame_memory()
            force_garbage_collection(threshold=1)  # Force immediate GC
        
        return memory_mb
    except Exception:
        # Don't crash if monitoring fails
        return None


def cleanup_streamlit_cache() -> None:
    """
    Clear Streamlit's internal cache to prevent image/file storage leaks.
    
    Note: This uses Streamlit's cache clearing API if available.
    """
    try:
        # Try to clear Streamlit's cache
        if hasattr(st, 'cache_data'):
            # Clear all cached data
            try:
                st.cache_data.clear()
            except Exception:
                pass  # Cache clearing might not be available in all Streamlit versions
    except Exception:
        pass  # Don't crash on cache clearing errors


def cleanup_video_resources(video_processor) -> None:
    """
    Clean up video processor resources to prevent leaks.
    
    Args:
        video_processor: VideoProcessor instance to clean up
    """
    try:
        if video_processor is None:
            return
        
        # Release video capture if not running
        if hasattr(video_processor, 'cap') and video_processor.cap is not None:
            if not getattr(video_processor, 'running', False):
                try:
                    video_processor.cap.release()
                except Exception:
                    pass
        
        # Clear large data structures
        if hasattr(video_processor, 'ear_history'):
            if isinstance(video_processor.ear_history, deque):
                video_processor.ear_history.clear()
        
        if hasattr(video_processor, 'blink_timestamps'):
            if isinstance(video_processor.blink_timestamps, deque):
                video_processor.blink_timestamps.clear()
        
        # Clear latest result if it contains large data
        if hasattr(video_processor, 'latest_result'):
            result = video_processor.latest_result
            if result and isinstance(result, dict):
                # Remove large preview frames from result
                if 'preview' in result:
                    result['preview'] = None
    except Exception:
        pass  # Don't crash on cleanup errors


def comprehensive_cleanup(video_processor=None, aggressive: bool = False) -> dict:
    """
    Perform comprehensive memory cleanup.
    
    Args:
        video_processor: Optional VideoProcessor instance to clean up
        aggressive: If True, perform more aggressive cleanup
    
    Returns:
        Dictionary with cleanup statistics
    """
    stats = {
        "session_state_removed": 0,
        "frames_cleared": 0,
        "gc_triggered": False,
        "memory_mb": None,
        "video_resources_cleaned": False
    }
    
    try:
        # Clean session state
        max_items = 30 if aggressive else 50
        stats["session_state_removed"] = cleanup_session_state(max_items=max_items)
        
        # Clear frame memory
        stats["frames_cleared"] = manage_frame_memory()
        
        # Force garbage collection
        threshold = 1 if aggressive else 50
        stats["gc_triggered"] = force_garbage_collection(threshold=threshold)
        
        # Monitor memory
        stats["memory_mb"] = monitor_memory_usage()
        
        # Clean video resources
        if video_processor is not None:
            cleanup_video_resources(video_processor)
            stats["video_resources_cleaned"] = True
        
        # Clear Streamlit cache periodically (less frequent)
        if aggressive or (time.time() - st.session_state.get("last_cache_cleanup", 0) > 300):
            cleanup_streamlit_cache()
            st.session_state.last_cache_cleanup = time.time()
        
    except Exception as e:
        # Log error but don't crash
        if hasattr(st.session_state, 'ui_error_count'):
            if st.session_state.ui_error_count <= 3:
                print(f"Memory cleanup error (non-critical): {e}")
    
    return stats


def initialize_memory_tracking() -> None:
    """Initialize memory tracking in session_state."""
    if "memory_tracker" not in st.session_state:
        st.session_state.memory_tracker = {
            "recent": [],
            "last_cleanup": time.time(),
            "cleanup_count": 0
        }
    
    if "gc_counter" not in st.session_state:
        st.session_state.gc_counter = 0
    
    if "last_memory_cleanup" not in st.session_state:
        st.session_state.last_memory_cleanup = 0.0
    
    if "last_cache_cleanup" not in st.session_state:
        st.session_state.last_cache_cleanup = 0.0
