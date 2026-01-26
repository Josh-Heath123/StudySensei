"""
AppleStyler - Apple Design System utilities for StudySensei.

Apple Design Principles:
- Minimal: Remove everything non-essential
- Hierarchical: Big focus circle, smaller metrics
- Consistent: One font, limited color palette
- Spacious: Generous whitespace
"""

from PyQt5.QtWidgets import QLayout
from typing import Dict


class AppleStyler:
    """Apple design system constants and utilities."""
    
    # Apple Spacing System
    SPACING: Dict[str, int] = {
        "large": 24,      # Between major sections
        "medium": 16,    # Between related elements
        "small": 8,      # Between tight elements
        "tiny": 4,       # Minimal spacing
    }
    
    # Apple Color Palette
    COLORS: Dict[str, str] = {
        "background": "#000000",           # Pure black
        "card": "rgba(28, 28, 30, 0.8)",   # Translucent card
        "blue": "#007AFF",                  # Apple blue
        "blue_hover": "#0A84FF",            # Apple blue hover
        "white": "#ffffff",                 # Pure white
        "white_80": "rgba(255, 255, 255, 0.8)",  # 80% white
        "white_60": "rgba(255, 255, 255, 0.6)",  # 60% white
        "white_20": "rgba(255, 255, 255, 0.2)",  # 20% white
        "white_10": "rgba(255, 255, 255, 0.1)",  # 10% white
        "border": "rgba(255, 255, 255, 0.08)",   # Subtle border
    }
    
    # Apple Typography
    TYPOGRAPHY: Dict[str, Dict[str, any]] = {
        "hero": {
            "size": 48,
            "weight": 700,  # Bold
            "letter_spacing": -1,
        },
        "title": {
            "size": 17,
            "weight": 600,  # Semibold
        },
        "body": {
            "size": 13,
            "weight": 400,  # Regular
        },
        "caption": {
            "size": 11,
            "weight": 400,  # Regular
        },
        "metric_label": {
            "size": 11,
            "weight": 400,
            "transform": "uppercase",
            "letter_spacing": 0.5,
        },
    }
    
    @staticmethod
    def apply_spacing(layout: QLayout, size: str = "medium", margins: str = "large") -> None:
        """
        Apply Apple spacing to a layout.
        
        Args:
            layout: QLayout to apply spacing to
            size: Spacing size ("large", "medium", "small", "tiny")
            margins: Margin size ("large", "medium", "small", "tiny")
        """
        if layout is None:
            return
        
        layout.setSpacing(AppleStyler.SPACING.get(size, 16))
        
        margin_value = AppleStyler.SPACING.get(margins, 24)
        layout.setContentsMargins(margin_value, margin_value, margin_value, margin_value)
    
    @staticmethod
    def get_hero_font() -> Dict[str, any]:
        """Get font settings for hero text (focus circle percentage)."""
        return AppleStyler.TYPOGRAPHY["hero"]
    
    @staticmethod
    def get_title_font() -> Dict[str, any]:
        """Get font settings for titles."""
        return AppleStyler.TYPOGRAPHY["title"]
    
    @staticmethod
    def get_body_font() -> Dict[str, any]:
        """Get font settings for body text."""
        return AppleStyler.TYPOGRAPHY["body"]
    
    @staticmethod
    def get_caption_font() -> Dict[str, any]:
        """Get font settings for captions."""
        return AppleStyler.TYPOGRAPHY["caption"]
    
    @staticmethod
    def get_metric_label_font() -> Dict[str, any]:
        """Get font settings for metric labels."""
        return AppleStyler.TYPOGRAPHY["metric_label"]
