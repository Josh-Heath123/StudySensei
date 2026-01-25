"""
Safe image display utilities for Streamlit to prevent MediaFileStorageError.
Handles proper image format conversion, validation, and error handling.
"""

import cv2
import numpy as np
import streamlit as st
from typing import Optional, Tuple


def safe_display_image(
    frame: Optional[np.ndarray],
    placeholder=None,
    width: str = "stretch",
    channels: str = "BGR",
    output_format: str = "JPEG"
) -> bool:
    """
    Safely display an image in Streamlit with proper error handling.
    
    This function prevents MediaFileStorageError by:
    1. Validating the image before display
    2. Converting BGR to RGB if needed
    3. Creating a copy to prevent reference issues
    4. Handling all exceptions gracefully
    
    Args:
        frame: Image as numpy array (BGR or RGB)
        placeholder: st.empty() placeholder to display in (optional)
        width: Display width ("stretch" or number)
        channels: Input channels ("BGR" or "RGB")
        output_format: Output format ("JPEG" or "PNG")
    
    Returns:
        True if image displayed successfully, False otherwise
    """
    if frame is None:
        if placeholder:
            placeholder.empty()
        return False
    
    # Validate frame is numpy array
    if not isinstance(frame, np.ndarray):
        if placeholder:
            placeholder.empty()
        return False
    
    # Validate shape
    if len(frame.shape) < 2 or frame.shape[0] == 0 or frame.shape[1] == 0:
        if placeholder:
            placeholder.empty()
        return False
    
    # Check for invalid values
    if np.any(np.isnan(frame)) or np.any(np.isinf(frame)):
        if placeholder:
            placeholder.empty()
        return False
    
    try:
        # Create a copy to prevent reference issues with Streamlit's cache
        frame_copy = frame.copy()
        
        # Convert BGR to RGB if needed (Streamlit expects RGB)
        if channels == "BGR" and len(frame_copy.shape) == 3 and frame_copy.shape[2] == 3:
            frame_rgb = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2RGB)
        elif channels == "RGB" or len(frame_copy.shape) == 2:
            frame_rgb = frame_copy
        else:
            # Unknown format, try to convert
            frame_rgb = frame_copy
        
        # Ensure uint8 format (required by Streamlit)
        if frame_rgb.dtype != np.uint8:
            # Normalize to 0-255 range
            if frame_rgb.max() > 1.0:
                frame_rgb = np.clip(frame_rgb, 0, 255).astype(np.uint8)
            else:
                frame_rgb = (frame_rgb * 255).astype(np.uint8)
        
        # Display image with error handling
        if placeholder:
            try:
                placeholder.image(
                    frame_rgb,
                    width=width,
                    output_format=output_format
                )
                return True
            except Exception as e:
                # Clear placeholder on error
                try:
                    placeholder.empty()
                except Exception:
                    pass
                # Log error but don't crash
                if hasattr(st.session_state, 'ui_error_count'):
                    st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
                    if st.session_state.ui_error_count <= 3:
                        print(f"Image display error (non-critical): {e}")
                return False
        else:
            # No placeholder, use st.image directly
            try:
                st.image(
                    frame_rgb,
                    width=width,
                    output_format=output_format
                )
                return True
            except Exception as e:
                if hasattr(st.session_state, 'ui_error_count'):
                    st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
                    if st.session_state.ui_error_count <= 3:
                        print(f"Image display error (non-critical): {e}")
                return False
                
    except Exception as e:
        # Catch any unexpected errors
        if placeholder:
            try:
                placeholder.empty()
            except Exception:
                pass
        if hasattr(st.session_state, 'ui_error_count'):
            st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
            if st.session_state.ui_error_count <= 3:
                print(f"Image processing error (non-critical): {e}")
        return False


def validate_image(frame: Optional[np.ndarray]) -> bool:
    """
    Validate that an image frame is safe to display.
    
    Args:
        frame: Image as numpy array
    
    Returns:
        True if image is valid, False otherwise
    """
    if frame is None:
        return False
    
    if not isinstance(frame, np.ndarray):
        return False
    
    if len(frame.shape) < 2:
        return False
    
    if frame.shape[0] == 0 or frame.shape[1] == 0:
        return False
    
    if frame.size == 0:
        return False
    
    if np.any(np.isnan(frame)) or np.any(np.isinf(frame)):
        return False
    
    return True


def cleanup_image_cache() -> None:
    """
    Clean up old image references from session_state to prevent storage leaks.
    
    This should be called periodically to prevent MediaFileStorageError from
    stale image references.
    """
    try:
        # List of keys to keep (current/active images)
        keep_keys = {"preview_image", "latest_frame"}
        
        # Find all image-related keys
        image_keys = [
            k for k in st.session_state.keys()
            if any(term in k.lower() for term in ['frame', 'image', 'preview', 'camera'])
            and k not in keep_keys
        ]
        
        # Remove old image references
        for key in image_keys:
            try:
                value = st.session_state.get(key)
                # Only remove if it's an image (numpy array) or None
                if value is None or isinstance(value, np.ndarray):
                    del st.session_state[key]
            except (KeyError, AttributeError):
                pass  # Key might have been deleted already
                
    except Exception as e:
        # Don't crash on cleanup errors
        if hasattr(st.session_state, 'ui_error_count'):
            st.session_state.ui_error_count = st.session_state.get("ui_error_count", 0) + 1
            if st.session_state.ui_error_count <= 3:
                print(f"Image cache cleanup error (non-critical): {e}")
