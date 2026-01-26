"""
PyQt Memory Manager - Memory leak prevention and monitoring for StudySensei.

Features:
- Memory leak detection
- Periodic cleanup
- Resource tracking
- Environment safety
"""

import gc
import os
import time
import weakref
from typing import List, Optional, Dict, Any
from collections import deque

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Memory monitoring will be limited.")


class MemoryMonitor:
    """Monitor memory usage and detect leaks."""
    
    def __init__(self, sample_size: int = 100):
        """
        Initialize memory monitor.
        
        Args:
            sample_size: Number of memory samples to keep
        """
        self.sample_size = sample_size
        self.memory_samples: deque = deque(maxlen=sample_size)
        self.timestamps: deque = deque(maxlen=sample_size)
        
        if _PSUTIL_AVAILABLE:
            self.process = psutil.Process(os.getpid())
        else:
            self.process = None
        
        self.leak_threshold_pct = 50.0  # 50% increase indicates leak
        self.leak_detected = False
    
    def check_memory(self) -> Optional[float]:
        """
        Check current memory usage.
        
        Returns:
            Current memory usage in MB, or None if psutil unavailable
        """
        if not _PSUTIL_AVAILABLE or self.process is None:
            return None
        
        try:
            current_mb = self.process.memory_info().rss / 1024 / 1024
            self.memory_samples.append(current_mb)
            self.timestamps.append(time.time())
            return current_mb
        except Exception:
            return None
    
    def check_memory_leak(self) -> bool:
        """
        Monitor memory usage over time and detect leaks.
        
        Returns:
            True if memory leak detected, False otherwise
        """
        if len(self.memory_samples) < 50:
            return False
        
        # Compare first half vs second half of samples
        first_half = list(self.memory_samples)[:25]
        second_half = list(self.memory_samples)[-25:]
        
        if len(first_half) < 25 or len(second_half) < 25:
            return False
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        if first_avg == 0:
            return False
        
        increase_pct = ((second_avg - first_avg) / first_avg) * 100
        
        if increase_pct > self.leak_threshold_pct:
            if not self.leak_detected:
                print(f"⚠️ MEMORY LEAK DETECTED: {increase_pct:.1f}% increase "
                      f"({first_avg:.1f}MB → {second_avg:.1f}MB)")
                self.leak_detected = True
            return True
        
        return False
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get current memory statistics.
        
        Returns:
            Dictionary with memory statistics
        """
        if not self.memory_samples:
            return {
                "current_mb": 0.0,
                "avg_mb": 0.0,
                "min_mb": 0.0,
                "max_mb": 0.0,
                "samples": 0,
                "leak_detected": False
            }
        
        samples = list(self.memory_samples)
        return {
            "current_mb": samples[-1] if samples else 0.0,
            "avg_mb": sum(samples) / len(samples) if samples else 0.0,
            "min_mb": min(samples) if samples else 0.0,
            "max_mb": max(samples) if samples else 0.0,
            "samples": len(samples),
            "leak_detected": self.leak_detected
        }


class ResourceTracker:
    """Track and cleanup PyQt/OpenCV resources."""
    
    def __init__(self):
        """Initialize resource tracker."""
        self.video_captures: List[weakref.ref] = []
        self.timers: List[weakref.ref] = []
        self.animations: List[weakref.ref] = []
        self.widgets: List[weakref.ref] = []
    
    def register_video_capture(self, capture):
        """Register a video capture object for tracking."""
        if capture is not None:
            self.video_captures.append(weakref.ref(capture))
    
    def register_timer(self, timer):
        """Register a timer for tracking."""
        if timer is not None:
            self.timers.append(weakref.ref(timer))
    
    def register_animation(self, animation):
        """Register an animation for tracking."""
        if animation is not None:
            self.animations.append(weakref.ref(animation))
    
    def register_widget(self, widget):
        """Register a widget for tracking."""
        if widget is not None:
            self.widgets.append(weakref.ref(widget))
    
    def cleanup_resources(self) -> Dict[str, int]:
        """
        Cleanup tracked resources.
        
        Returns:
            Dictionary with cleanup statistics
        """
        stats = {
            "video_captures": 0,
            "timers": 0,
            "animations": 0,
            "widgets": 0
        }
        
        # Cleanup video captures
        for ref in self.video_captures[:]:
            obj = ref()
            if obj is not None:
                try:
                    if hasattr(obj, 'release'):
                        obj.release()
                    stats["video_captures"] += 1
                except Exception:
                    pass
            self.video_captures.remove(ref)
        
        # Cleanup timers
        for ref in self.timers[:]:
            obj = ref()
            if obj is not None:
                try:
                    if hasattr(obj, 'stop'):
                        obj.stop()
                    stats["timers"] += 1
                except Exception:
                    pass
            self.timers.remove(ref)
        
        # Cleanup animations
        for ref in self.animations[:]:
            obj = ref()
            if obj is not None:
                try:
                    if hasattr(obj, 'stop'):
                        obj.stop()
                    stats["animations"] += 1
                except Exception:
                    pass
            self.animations.remove(ref)
        
        # Widgets are cleaned up by Qt automatically, but we can track them
        self.widgets.clear()
        
        return stats


class PyQtMemoryManager:
    """Main memory manager for PyQt application."""
    
    def __init__(self, check_interval: int = 30):
        """
        Initialize PyQt memory manager.
        
        Args:
            check_interval: Memory check interval in seconds
        """
        self.check_interval = check_interval
        self.last_check_time = time.time()
        self.last_cleanup_time = time.time()
        self.cleanup_interval = 60  # Cleanup every 60 seconds
        
        self.monitor = MemoryMonitor()
        self.tracker = ResourceTracker()
        
        self.cleanup_count = 0
        self.force_gc_threshold = 100  # Force GC every N frames
    
    def check_memory(self) -> Optional[float]:
        """
        Check memory usage and detect leaks.
        
        Returns:
            Current memory usage in MB, or None
        """
        current_time = time.time()
        
        # Check memory periodically
        if current_time - self.last_check_time >= self.check_interval:
            self.last_check_time = current_time
            
            memory_mb = self.monitor.check_memory()
            
            # Check for leaks
            if self.monitor.check_memory_leak():
                # Trigger aggressive cleanup
                self.force_cleanup()
            
            return memory_mb
        
        return None
    
    def periodic_cleanup(self) -> None:
        """Perform periodic cleanup of resources."""
        current_time = time.time()
        
        if current_time - self.last_cleanup_time >= self.cleanup_interval:
            self.last_cleanup_time = current_time
            self.cleanup()
    
    def cleanup(self) -> Dict[str, int]:
        """
        Cleanup resources and force garbage collection.
        
        Returns:
            Dictionary with cleanup statistics
        """
        # Cleanup tracked resources
        stats = self.tracker.cleanup_resources()
        
        # Force garbage collection
        collected = gc.collect()
        stats["gc_collected"] = collected
        
        self.cleanup_count += 1
        
        if self.cleanup_count % 10 == 0:  # Log every 10th cleanup
            memory_stats = self.monitor.get_memory_stats()
            print(f"🧹 Cleanup #{self.cleanup_count}: "
                  f"Memory: {memory_stats['current_mb']:.1f}MB, "
                  f"GC collected: {collected} objects")
        
        return stats
    
    def force_cleanup(self) -> Dict[str, int]:
        """
        Force aggressive cleanup (called when leak detected).
        
        Returns:
            Dictionary with cleanup statistics
        """
        print("🔧 Force cleanup triggered due to memory leak detection")
        
        # Multiple GC passes
        collected = 0
        for _ in range(3):
            collected += gc.collect()
        
        # Cleanup resources
        stats = self.tracker.cleanup_resources()
        stats["gc_collected"] = collected
        
        return stats
    
    def register_video_capture(self, capture):
        """Register a video capture for tracking."""
        self.tracker.register_video_capture(capture)
    
    def register_timer(self, timer):
        """Register a timer for tracking."""
        self.tracker.register_timer(timer)
    
    def register_animation(self, animation):
        """Register an animation for tracking."""
        self.tracker.register_animation(animation)
    
    def register_widget(self, widget):
        """Register a widget for tracking."""
        self.tracker.register_widget(widget)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory statistics."""
        return self.monitor.get_memory_stats()
    
    def shutdown(self) -> None:
        """Shutdown memory manager and cleanup all resources."""
        print("🛑 Shutting down memory manager...")
        
        # Final cleanup
        stats = self.force_cleanup()
        
        memory_stats = self.monitor.get_memory_stats()
        print(f"📊 Final memory stats: {memory_stats['current_mb']:.1f}MB")
        print(f"🧹 Cleanup stats: {stats}")


# Global memory manager instance
_memory_manager: Optional[PyQtMemoryManager] = None


def get_memory_manager() -> PyQtMemoryManager:
    """Get or create global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = PyQtMemoryManager()
    return _memory_manager


def initialize_memory_manager(check_interval: int = 30) -> PyQtMemoryManager:
    """
    Initialize global memory manager.
    
    Args:
        check_interval: Memory check interval in seconds
        
    Returns:
        Memory manager instance
    """
    global _memory_manager
    _memory_manager = PyQtMemoryManager(check_interval=check_interval)
    return _memory_manager


def cleanup_memory() -> Dict[str, int]:
    """
    Cleanup memory (convenience function).
    
    Returns:
        Cleanup statistics
    """
    manager = get_memory_manager()
    return manager.cleanup()


def shutdown_memory_manager() -> None:
    """Shutdown global memory manager."""
    global _memory_manager
    if _memory_manager is not None:
        _memory_manager.shutdown()
        _memory_manager = None
