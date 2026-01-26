"""
Main window for StudySensei PyQt5 application.
QMainWindow skeleton - UI implementation to follow.
"""

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QGraphicsOpacityEffect,
)
from PyQt5.QtCore import Qt, pyqtSlot, QPropertyAnimation, QEasingCurve, QEvent
from PyQt5.QtGui import QFont
import numpy as np

from .video_widget import VideoWidget
from .focus_circle_widget import FocusCircleWidget
from .metrics_panel import MetricsPanel
from .analytics_widget import AnalyticsWidget
from .apple_styler import AppleStyler
from .sidebar_widget import AppleSidebar
from .sidebar_toggle_button import SidebarToggleButton
from services.studysensei_engine import StudySenseiEngine


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        print("🔍 MainWindow.__init__() started")
        
        self.setWindowTitle("StudySensei - Focus & Posture Tracking")
        self.setMinimumSize(1200, 800)
        
        # DEBUG: Temporarily disable stylesheet to eliminate styling issues
        print("🔍 Loading stylesheet...")
        # self._load_stylesheet()  # TEMPORARILY DISABLED FOR DEBUGGING
        
        # DEBUG: Add visible borders to all widgets
        self.setStyleSheet("""
            QWidget {
                border: 2px solid cyan;
            }
            QMainWindow {
                background-color: #1a1a1a;
            }
        """)
        
        # Create main container widget
        # CRITICAL: Store as instance variable to prevent garbage collection
        self.main_container = QWidget(self)  # Explicit parent to MainWindow
        self.setCentralWidget(self.main_container)
        print(f"🔍 MainWindow: Created main_container, id={id(self.main_container)}, parent={self.main_container.parent()}")
        main_container_layout = QHBoxLayout(self.main_container)
        main_container_layout.setContentsMargins(0, 0, 0, 0)
        main_container_layout.setSpacing(0)
        
        # Create sidebar
        self.sidebar = AppleSidebar(self)
        self.sidebar.main_clicked.connect(self._on_sidebar_main_clicked)
        self.sidebar.analytics_clicked.connect(self._on_sidebar_analytics_clicked)
        main_container_layout.addWidget(self.sidebar)
        
        # Create content area (right side)
        # CRITICAL: Store as instance variable to prevent garbage collection
        self.content_widget = QWidget(self.main_container)  # Explicit parent to main_container
        content_widget_parent = self.content_widget.parent()
        print(f"🔍 MainWindow: Created content_widget, id={id(self.content_widget)}, parent={content_widget_parent}, parent_id={id(content_widget_parent) if content_widget_parent else None}")
        
        # CRITICAL: Verify parent is set correctly
        if content_widget_parent is None:
            print("❌ CRITICAL: content_widget has no parent! Fixing by reparenting to main_container...")
            self.content_widget.setParent(self.main_container)
            print(f"✅ Reparented content_widget, new parent: {self.content_widget.parent()}")
        elif content_widget_parent != self.main_container:
            print(f"⚠️ WARNING: content_widget parent mismatch! Expected main_container, got {content_widget_parent}")
            self.content_widget.setParent(self.main_container)
            print(f"✅ Reparented content_widget to main_container")
        
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Top bar with toggle button
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(16, 16, 16, 16)
        top_bar_layout.setSpacing(12)
        
        # Toggle button (vertically centered)
        self.sidebar_toggle = SidebarToggleButton()
        self.sidebar_toggle.clicked.connect(self.sidebar.toggle)
        top_bar_layout.addWidget(self.sidebar_toggle)
        top_bar_layout.addStretch()
        
        content_layout.addWidget(top_bar)
        
        # Main layout - Apple spacing system
        # CRITICAL: Store as instance variable to prevent garbage collection
        self.main_layout = QVBoxLayout()
        AppleStyler.apply_spacing(self.main_layout, size="medium", margins="large")
        
        # Header
        self._setup_header(self.main_layout)
        
        # Controls section
        self._setup_controls(self.main_layout)
        
        # Content area (replaces tab widget - sidebar handles navigation)
        # CRITICAL: Store as instance variable with explicit parent
        self.content_stack = QWidget(self.content_widget)  # Parent to content_widget
        content_stack_parent = self.content_stack.parent()
        print(f"🔍 MainWindow: Created content_stack, id={id(self.content_stack)}, parent={content_stack_parent}, parent_id={id(content_stack_parent) if content_stack_parent else None}")
        
        # CRITICAL: Verify parent is set correctly
        if content_stack_parent is None:
            print("❌ CRITICAL: content_stack has no parent! Fixing by reparenting to content_widget...")
            self.content_stack.setParent(self.content_widget)
            print(f"✅ Reparented content_stack, new parent: {self.content_stack.parent()}")
        elif content_stack_parent != self.content_widget:
            print(f"⚠️ WARNING: content_stack parent mismatch! Expected content_widget, got {content_stack_parent}")
            self.content_stack.setParent(self.content_widget)
            print(f"✅ Reparented content_stack to content_widget")
        
        self.content_stack_layout = QVBoxLayout(self.content_stack)
        self.content_stack_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main content widget
        # CRITICAL: This widget must persist for the window's lifetime
        # Parent to content_stack (which is parented to content_widget -> main_container -> MainWindow)
        self.main_content = QWidget(self.content_stack)  # Explicit parent chain
        main_content_parent = self.main_content.parent()
        print(f"🔍 MainWindow: Created main_content widget, id={id(self.main_content)}, parent={main_content_parent}, parent_id={id(main_content_parent) if main_content_parent else None}")
        
        # CRITICAL: Verify parent is set correctly
        if main_content_parent is None:
            print("❌ CRITICAL: main_content has no parent! Fixing by reparenting to content_stack...")
            self.main_content.setParent(self.content_stack)
            print(f"✅ Reparented main_content, new parent: {self.main_content.parent()}")
        elif main_content_parent != self.content_stack:
            print(f"⚠️ WARNING: main_content parent mismatch! Expected content_stack, got {main_content_parent}")
            self.main_content.setParent(self.content_stack)
            print(f"✅ Reparented main_content to content_stack")
        
        main_content_layout = QVBoxLayout(self.main_content)
        AppleStyler.apply_spacing(main_content_layout, size="medium", margins="large")
        
        # Metrics section
        self._setup_metrics(main_content_layout)
        
        # Preview section
        self._setup_preview(main_content_layout)
        
        # Note: VideoWidget reference is already stored in _widget_references during _setup_ui()
        
        # Analytics widget
        # CRITICAL: Analytics widget must also have explicit parent
        self.analytics_widget = AnalyticsWidget(parent=self)  # Explicit parent
        print(f"🔍 MainWindow: Created analytics_widget, id={id(self.analytics_widget)}, parent={self.analytics_widget.parent()}")
        
        # Add both to stack (we'll show/hide them)
        self.content_stack_layout.addWidget(self.main_content)
        self.content_stack_layout.addWidget(self.analytics_widget)
        self.analytics_widget.hide()  # Hidden by default
        
        self.main_layout.addWidget(self.content_stack, stretch=1)
        
        # Add main layout to content widget
        # CRITICAL: This widget must persist for the window's lifetime
        # MUST be stored as instance variable BEFORE any references
        self.content_widget_inner = QWidget(self.content_widget)  # Explicit parent to content_widget
        content_widget_inner_parent = self.content_widget_inner.parent()
        print(f"🔍 MainWindow: Created content_widget_inner, id={id(self.content_widget_inner)}, parent={content_widget_inner_parent}, parent_id={id(content_widget_inner_parent) if content_widget_inner_parent else None}")
        
        # CRITICAL: Verify parent is set correctly
        if content_widget_inner_parent is None:
            print("❌ CRITICAL: content_widget_inner has no parent! Fixing by reparenting to content_widget...")
            self.content_widget_inner.setParent(self.content_widget)
            print(f"✅ Reparented content_widget_inner, new parent: {self.content_widget_inner.parent()}")
        elif content_widget_inner_parent != self.content_widget:
            print(f"⚠️ WARNING: content_widget_inner parent mismatch! Expected content_widget, got {content_widget_inner_parent}")
            self.content_widget_inner.setParent(self.content_widget)
            print(f"✅ Reparented content_widget_inner to content_widget")
        
        self.content_widget_inner.setLayout(self.main_layout)
        content_layout.addWidget(self.content_widget_inner, stretch=1)
        
        print(f"🔍 MainWindow: Content widget size: {self.content_widget_inner.width()}x{self.content_widget_inner.height()}")
        print(f"🔍 MainWindow: Central widget size: {self.centralWidget().width()}x{self.centralWidget().height()}")
        
        # CRITICAL: Verify main_content persists and is not replaced
        print(f"🔍 MainWindow: Verifying widget hierarchy:")
        print(f"   main_content: id={id(self.main_content)}, parent={self.main_content.parent()}, parent_id={id(self.main_content.parent()) if self.main_content.parent() else None}")
        print(f"   content_stack: id={id(self.content_stack)}, parent={self.content_stack.parent()}")
        print(f"   content_widget: id={id(self.content_widget)}, parent={self.content_widget.parent()}")
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        print("🔍 MainWindow.__init__() completed")
        
        # CRITICAL: Verify all persistent widgets exist and are properly parented
        print("🔍 MainWindow: Verifying widget hierarchy at end of __init__:")
        
        # Verify main_container
        if hasattr(self, 'main_container'):
            try:
                print(f"✅ main_container: id={id(self.main_container)}, parent={self.main_container.parent()}")
            except RuntimeError as e:
                print(f"❌ CRITICAL: main_container C++ object deleted! Error: {e}")
        
        # Verify content_widget
        if hasattr(self, 'content_widget') and self.content_widget is not None:
            try:
                content_widget_parent = self.content_widget.parent()
                print(f"✅ content_widget: id={id(self.content_widget)}, parent={content_widget_parent}, parent_id={id(content_widget_parent) if content_widget_parent else None}")
                if content_widget_parent is None:
                    print("❌ CRITICAL: content_widget has no parent!")
            except RuntimeError as e:
                print(f"❌ CRITICAL: content_widget C++ object deleted! Error: {e}")
        
        # Verify content_stack
        if hasattr(self, 'content_stack') and self.content_stack is not None:
            try:
                content_stack_parent = self.content_stack.parent()
                print(f"✅ content_stack: id={id(self.content_stack)}, parent={content_stack_parent}, parent_id={id(content_stack_parent) if content_stack_parent else None}")
            except RuntimeError as e:
                print(f"❌ CRITICAL: content_stack C++ object deleted! Error: {e}")
        
        # Verify main_content
        if hasattr(self, 'main_content') and self.main_content is not None:
            try:
                main_content_id = id(self.main_content)
                main_content_parent = self.main_content.parent()
                main_content_parent_id = id(main_content_parent) if main_content_parent else None
                print(f"✅ main_content: id={main_content_id}, parent={main_content_parent}, parent_id={main_content_parent_id}")
                
                if main_content_parent is None:
                    print("❌ CRITICAL: main_content has no parent! This will cause VideoWidget deletion!")
                elif main_content_parent != self.content_stack:
                    print(f"⚠️ WARNING: main_content parent is {main_content_parent}, expected content_stack")
            except RuntimeError as e:
                print(f"❌ CRITICAL: main_content C++ object deleted! Error: {e}")
        else:
            print("❌ CRITICAL: main_content missing!")
        
        # Verify content_widget_inner
        if hasattr(self, 'content_widget_inner') and self.content_widget_inner is not None:
            try:
                inner_parent = self.content_widget_inner.parent()
                print(f"✅ content_widget_inner: id={id(self.content_widget_inner)}, parent={inner_parent}, parent_id={id(inner_parent) if inner_parent else None}")
            except RuntimeError as e:
                print(f"❌ CRITICAL: content_widget_inner C++ object deleted! Error: {e}")
        else:
            print("❌ CRITICAL: content_widget_inner missing!")
        
        # Verify video_widget
        if hasattr(self, 'video_widget') and self.video_widget is not None:
            try:
                widget_id = id(self.video_widget)
                widget_parent = self.video_widget.parent()
                widget_parent_id = id(widget_parent) if widget_parent else None
                print(f"✅ VideoWidget: id={widget_id}, parent={widget_parent}, parent_id={widget_parent_id}")
                
                # Verify parent is main_content
                if widget_parent is None:
                    print("❌ CRITICAL: VideoWidget has no parent at end of __init__!")
                elif widget_parent == self.main_content:
                    print(f"✅ VideoWidget parent is main_content (correct, id={id(self.main_content)})")
                else:
                    print(f"⚠️ WARNING: VideoWidget parent is {widget_parent}, expected main_content (id={id(self.main_content)})")
                
                # Verify complete parent chain to MainWindow
                current = self.video_widget
                chain = []
                depth = 0
                while current is not None and depth < 10:
                    chain.append(f"{type(current).__name__}(id={id(current)})")
                    if current == self:
                        chain.append("✅ REACHED MAINWINDOW")
                        break
                    current = current.parent()
                    depth += 1
                print(f"🔍 VideoWidget parent chain: {' -> '.join(chain)}")
                if current != self:
                    print("❌ CRITICAL: VideoWidget parent chain does NOT lead to MainWindow!")
            except RuntimeError as e:
                print(f"❌ CRITICAL: VideoWidget C++ object deleted before __init__ completes! Error: {e}")
        else:
            print("❌ CRITICAL: VideoWidget missing at end of __init__!")
        
        # Note: Test frame is scheduled in _setup_preview() using QTimer.singleShot(100, ...)
        # This ensures it runs after Qt's initialization is complete and widget hierarchy is stable
        
        # Set initial active button
        self.sidebar.set_active_button("main")
        
        # Register UI components with memory manager
        from utils.pyqt_memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
        memory_manager.register_widget(self.focus_circle)
        memory_manager.register_widget(self.metrics_panel)
        memory_manager.register_widget(self.video_widget)
        memory_manager.register_widget(self.analytics_widget)
        
        # StudySensei engine (adapter for existing logic)
        print("🔍 MainWindow: Creating StudySenseiEngine...")
        self.engine = StudySenseiEngine(self)
        print(f"🔍 MainWindow: Engine created, engine object: {self.engine}")
        
        # Connect engine signals to UI slots
        print("🔍 MainWindow: Connecting engine signals...")
        self.engine.frame_processed.connect(self._on_frame_processed)
        self.engine.frame_ready.connect(self._on_frame_ready)
        self.engine.error_occurred.connect(self._on_error)
        print("🔍 MainWindow: Signals connected")
        
        # IMMEDIATE CAMERA TEST: Test camera directly after engine creation
        print("🔍 MainWindow: Testing camera directly with OpenCV...")
        # Use QTimer to test after window is shown
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, self._test_camera_directly)  # 1 second delay
        
        # Setup memory monitoring timer (update status bar every 60 seconds)
        from PyQt5.QtCore import QTimer
        self.memory_timer = QTimer(self)
        self.memory_timer.timeout.connect(self._update_memory_status)
        self.memory_timer.start(60000)  # Every 60 seconds
        memory_manager.register_timer(self.memory_timer)
    
    def _setup_button_hover_effect(self, button: QPushButton) -> None:
        """
        Setup button hover opacity effect (Apple-inspired).
        Uses QGraphicsOpacityEffect for smooth opacity transitions.
        """
        opacity_effect = QGraphicsOpacityEffect(button)
        opacity_effect.setOpacity(1.0)
        button.setGraphicsEffect(opacity_effect)
        
        # Animation for opacity on hover
        opacity_animation = QPropertyAnimation(opacity_effect, b"opacity")
        opacity_animation.setDuration(200)  # Fast, Apple-like
        opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Store animation in button for access
        button._opacity_effect = opacity_effect
        button._opacity_animation = opacity_animation
        
        # Install event filter to catch hover events
        button.installEventFilter(self)
    
    def eventFilter(self, obj, event) -> bool:
        """Event filter for button hover effects."""
        if isinstance(obj, QPushButton) and hasattr(obj, '_opacity_animation'):
            if event.type() == QEvent.Enter:
                # Hover enter - reduce opacity slightly
                obj._opacity_animation.setStartValue(obj._opacity_effect.opacity())
                obj._opacity_animation.setEndValue(0.8)  # Slight fade on hover
                obj._opacity_animation.start()
            elif event.type() == QEvent.Leave:
                # Hover leave - restore full opacity
                obj._opacity_animation.setStartValue(obj._opacity_effect.opacity())
                obj._opacity_animation.setEndValue(1.0)  # Full opacity
                obj._opacity_animation.start()
        return super().eventFilter(obj, event)
    
    def _setup_header(self, parent_layout):
        """Setup header section with Apple typography - minimal, clean."""
        # Minimal header - Apple style (can be removed for even more minimal design)
        header_label = QLabel("StudySensei")
        title_font = AppleStyler.get_title_font()
        header_font = QFont()
        header_font.setPointSize(title_font["size"])
        header_font.setWeight(title_font["weight"])
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setProperty("class", "header")
        header_label.setObjectName("title")
        
        # Optional subtitle - can be hidden for ultra-minimal design
        subtitle_label = QLabel("Focus & Posture Tracking")
        body_font = AppleStyler.get_body_font()
        subtitle_font = QFont()
        subtitle_font.setPointSize(body_font["size"])
        subtitle_font.setWeight(body_font["weight"])
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setProperty("class", "body")
        subtitle_label.setObjectName("subtitle")
        
        parent_layout.addWidget(header_label)
        parent_layout.addWidget(subtitle_label)
    
    def _setup_controls(self, parent_layout):
        """Setup control buttons section."""
        controls_layout = QHBoxLayout()
        AppleStyler.apply_spacing(controls_layout, size="medium", margins="tiny")
        
        # Start button with hover opacity effect
        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumHeight(45)
        self.start_btn.setObjectName("start_btn")
        self._setup_button_hover_effect(self.start_btn)
        self.start_btn.clicked.connect(self._on_start_clicked)
        
        # Stop button with hover opacity effect
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMinimumHeight(45)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setObjectName("stop_btn")
        self._setup_button_hover_effect(self.stop_btn)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        
        # Toggle Mesh button with hover opacity effect
        self.toggle_mesh_btn = QPushButton("Toggle Mesh")
        self.toggle_mesh_btn.setMinimumHeight(45)
        self.toggle_mesh_btn.setObjectName("toggle_mesh_btn")
        self._setup_button_hover_effect(self.toggle_mesh_btn)
        self.toggle_mesh_btn.clicked.connect(self._on_toggle_mesh_clicked)
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.toggle_mesh_btn)
        controls_layout.addStretch()
        
        parent_layout.addLayout(controls_layout)
    
    def _setup_metrics(self, parent_layout):
        """
        Setup metrics display section with FocusCircleWidget as HERO element.
        Apple design: Big focus circle (hero), smaller metrics (supporting).
        """
        metrics_widget = QWidget()
        metrics_layout = QHBoxLayout(metrics_widget)
        AppleStyler.apply_spacing(metrics_layout, size="large", margins="tiny")
        
        # HERO: Focus circle widget (centered, prominent)
        # CRITICAL: Explicit parent to ensure persistence
        self.focus_circle = FocusCircleWidget(parent=self.main_content)
        print(f"🔍 MainWindow: Created focus_circle, id={id(self.focus_circle)}, parent={self.focus_circle.parent()}")
        # Make focus circle larger for hero treatment
        self.focus_circle.setMinimumSize(300, 320)  # Larger than default
        
        # Register animations with memory manager
        from utils.pyqt_memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
        if hasattr(self.focus_circle, '_focus_animation'):
            memory_manager.register_animation(self.focus_circle._focus_animation)
        if hasattr(self.focus_circle, '_circle_animation'):
            memory_manager.register_animation(self.focus_circle._circle_animation)
        
        metrics_layout.addWidget(self.focus_circle, alignment=Qt.AlignCenter, stretch=2)
        
        # Supporting: Metrics panel (smaller, secondary)
        # CRITICAL: Explicit parent to ensure persistence
        self.metrics_panel = MetricsPanel(parent=self.main_content)
        print(f"🔍 MainWindow: Created metrics_panel, id={id(self.metrics_panel)}, parent={self.metrics_panel.parent()}")
        metrics_layout.addWidget(self.metrics_panel, stretch=1)
        
        parent_layout.addWidget(metrics_widget, stretch=1)  # Give metrics section priority
    
    def _setup_preview(self, parent_layout):
        """Setup preview section with VideoWidget."""
        print("🔍 MainWindow._setup_preview() called")
        print(f"🔍 parent_layout: {parent_layout}, parent widget: {parent_layout.parent()}")
        
        # CRITICAL: Get the persistent parent widget (main_content)
        # main_content is stored as self.main_content and parented to content_stack -> content_widget -> main_container -> MainWindow
        parent_widget = parent_layout.parent()  # Should be self.main_content
        if parent_widget is None:
            print("❌ CRITICAL: parent_layout has no parent widget!")
            print("   Using self.main_content as VideoWidget parent")
            parent_widget = self.main_content
        elif parent_widget != self.main_content:
            print(f"⚠️ WARNING: parent_layout parent ({parent_widget}) != self.main_content ({self.main_content})")
            print(f"   Using self.main_content as VideoWidget parent instead")
            parent_widget = self.main_content
        
        # CRITICAL: Verify main_content still exists and has proper parent
        try:
            main_content_id = id(self.main_content)
            main_content_parent = self.main_content.parent()
            main_content_parent_id = id(main_content_parent) if main_content_parent else None
            print(f"🔍 main_content verification: id={main_content_id}, parent={main_content_parent}, parent_id={main_content_parent_id}")
            
            # CRITICAL: Verify parent chain leads to MainWindow
            if main_content_parent is None:
                print("❌ CRITICAL: main_content has no parent! This will cause VideoWidget to be deleted!")
                print("   Fixing by reparenting to content_stack...")
                if hasattr(self, 'content_stack'):
                    self.main_content.setParent(self.content_stack)
                    print(f"✅ Reparented main_content to content_stack, new parent: {self.main_content.parent()}")
                else:
                    print("❌ CRITICAL: content_stack doesn't exist! Reparenting to MainWindow as last resort...")
                    self.main_content.setParent(self)
                    print(f"✅ Reparented main_content to MainWindow, new parent: {self.main_content.parent()}")
                parent_widget = self.main_content  # Update parent_widget after reparenting
            else:
                # Verify parent chain
                current = self.main_content
                chain = []
                depth = 0
                while current is not None and depth < 10:
                    chain.append(f"{type(current).__name__}(id={id(current)})")
                    if current == self:
                        chain.append("✅ REACHED MAINWINDOW")
                        break
                    current = current.parent()
                    depth += 1
                print(f"🔍 main_content parent chain: {' -> '.join(chain)}")
                if current != self:
                    print("⚠️ WARNING: main_content parent chain does NOT lead to MainWindow!")
        except RuntimeError as e:
            print(f"❌ CRITICAL: main_content C++ object deleted! Error: {e}")
            print("   This should never happen - main_content is stored as instance variable")
            print("   Recreating main_content as last resort...")
            # Recreate main_content with proper parent
            self.main_content = QWidget(self.content_stack if hasattr(self, 'content_stack') else self)
            parent_widget = self.main_content
        
        print(f"🔍 Creating VideoWidget with parent={parent_widget}, parent_id={id(parent_widget)}, parent_type={type(parent_widget).__name__}")
        
        # CRITICAL: Create VideoWidget with explicit parent to persistent widget
        # Parent to main_content (which is parented to content_stack -> content_widget -> MainWindow)
        self.video_widget = VideoWidget(parent=parent_widget)
        print(f"🔍 VideoWidget created: id={id(self.video_widget)}, parent={self.video_widget.parent()}, parent_id={id(self.video_widget.parent())}")
        
        # Verify parent chain is correct
        current = self.video_widget
        chain = []
        depth = 0
        while current is not None and depth < 10:  # Prevent infinite loop
            chain.append(f"{type(current).__name__}(id={id(current)})")
            current = current.parent()
            depth += 1
        print(f"🔍 VideoWidget parent chain: {' -> '.join(chain)}")
        
        # CRITICAL: Verify parent is main_content
        if self.video_widget.parent() != self.main_content:
            print(f"⚠️ WARNING: VideoWidget parent mismatch!")
            print(f"   Expected: main_content (id={id(self.main_content)})")
            print(f"   Actual: {self.video_widget.parent()} (id={id(self.video_widget.parent())})")
        
        self.video_widget.setMinimumHeight(400)
        self.video_widget.setMinimumWidth(640)
        
        # DEBUG: Add visible debug styling - bright border to confirm position
        self.video_widget.setStyleSheet("background-color: red; border: 5px solid yellow;")
        print(f"🔍 VideoWidget configured, size: {self.video_widget.width()}x{self.video_widget.height()}")
        
        # CRITICAL: Add to layout (this also keeps a reference and establishes parent-child relationship)
        parent_layout.addWidget(self.video_widget, stretch=1)
        print(f"🔍 VideoWidget added to layout")
        
        # CRITICAL: Verify widget is still alive and parent is correct
        try:
            widget_id = id(self.video_widget)
            widget_parent = self.video_widget.parent()
            widget_parent_id = id(widget_parent) if widget_parent else None
            print(f"✅ VideoWidget verified: id={widget_id}, parent={widget_parent}, parent_id={widget_parent_id}")
            
            # Verify parent is main_content (persistent)
            if widget_parent is None:
                print("❌ CRITICAL: VideoWidget has no parent!")
            elif widget_parent == self.main_content:
                print(f"✅ VideoWidget parent is main_content (persistent, id={id(self.main_content)})")
            elif widget_parent == self:
                print("✅ VideoWidget parent is MainWindow (persistent)")
            else:
                print(f"⚠️ WARNING: VideoWidget parent is {widget_parent} (id={id(widget_parent)}), expected main_content (id={id(self.main_content)})")
        except RuntimeError as e:
            print(f"❌ CRITICAL: VideoWidget C++ object already deleted! Error: {e}")
        
        # CRITICAL: Schedule test frame AFTER Qt's initialization is complete
        # Use QTimer.singleShot(100, ...) to delay and ensure widget hierarchy is stable
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._send_test_frame_to_widget)  # 100ms delay for stability
    
    
    def _test_camera_directly(self):
        """Test camera directly with OpenCV to verify it works."""
        print("🔍 MainWindow._test_camera_directly() called")
        import cv2
        
        test_cap = cv2.VideoCapture(0)
        if test_cap.isOpened():
            print("✅ Camera opened successfully")
            ret, test_frame = test_cap.read()
            if ret and test_frame is not None:
                print(f"✅ Camera test successful! Frame shape: {test_frame.shape}, dtype: {test_frame.dtype}")
                # Send test frame to widget immediately
                if hasattr(self, 'video_widget') and self.video_widget:
                    print("🔍 Sending camera test frame to VideoWidget...")
                    self.video_widget.update_frame(test_frame)
                    self.video_widget.update()
            else:
                print("❌ Camera test failed: Could not read frame")
            test_cap.release()
        else:
            print("❌ Camera test failed: Could not open camera")
    
    def _on_start_clicked(self):
        """Handle start button click."""
        print("🔍 MainWindow._on_start_clicked() called")
        
        # Test camera directly with OpenCV first
        self._test_camera_directly()
        
        # Start StudySensei engine
        print("🔍 Starting StudySensei engine...")
        success = self.engine.start(camera_index=0)
        
        print(f"🔍 Engine start result: {success}")
        print(f"🔍 Engine running: {self.engine.is_running()}")
        print(f"🔍 Engine cap: {self.engine.cap}")
        if self.engine.cap:
            print(f"🔍 Engine cap isOpened: {self.engine.cap.isOpened()}")
        
        if success:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.statusBar().showMessage("Session started - Processing frames")
            
            # Update UI with initial values
            self.focus_circle.set_focus_score(0.0, "WAITING")
            self.metrics_panel.set_posture_score(0.0)
            self.metrics_panel.set_fps(0.0)
            self.metrics_panel.set_session_time(0.0)
            
            # Reset analytics widget
            self.analytics_widget.reset()
            
            print("✅ Session started successfully")
        else:
            self.statusBar().showMessage("Error: Could not start camera")
            print("❌ Failed to start session")
    
    def _on_stop_clicked(self):
        """Handle stop button click."""
        # Stop StudySensei engine
        self.engine.stop()
        
        # Clear video widget (but don't delete it!)
        if self.video_widget is not None:
            try:
                self.video_widget.clear()
            except RuntimeError:
                # Widget already deleted, ignore
                pass
        
        # Reset UI
        self.focus_circle.set_focus_score(0.0, "WAITING")
        self.metrics_panel.reset()
        self.analytics_widget.reset()
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.statusBar().showMessage("Session stopped")
    
    def _on_toggle_mesh_clicked(self):
        """Handle toggle mesh button click."""
        self.engine.toggle_landmarks()
        status = "enabled" if self.engine.draw_pose else "disabled"
        self.statusBar().showMessage(f"Face mesh {status}")
    
    @pyqtSlot(dict)
    def _on_frame_processed(self, result: dict):
        """Handle frame processing result (connected to engine signal)."""
        # Update focus circle
        focus_score = result.get("score", 0.0)
        focused = result.get("focused", False)
        status_text = "FOCUSED" if focused else "DISTRACTED"
        self.focus_circle.set_focus_score(focus_score, status_text)
        
        # Update posture score
        posture_score = 0.0
        if result.get("posture"):
            posture_score = result["posture"].get("score", 0.0)
            self.metrics_panel.set_posture_score(posture_score)
        
        # Update FPS
        fps = result.get("fps", 0.0)
        self.metrics_panel.set_fps(fps)
        
        # Update session timer
        session_duration = self.engine.get_session_duration()
        self.metrics_panel.set_session_time(session_duration)
        
        # Add data points to analytics (sample every 2 seconds)
        timestamp = result.get("timestamp", 0.0)
        if int(timestamp) % 2 == 0:  # Sample every 2 seconds
            self.analytics_widget.add_focus_data_point(timestamp, focus_score)
            if posture_score > 0:
                self.analytics_widget.add_posture_data_point(timestamp, posture_score)
        
        # Update status bar
        self.statusBar().showMessage(
            f"Session active - FPS: {fps:.1f} | Focus: {focus_score:.0f}% | Posture: {posture_score:.0f}%"
        )
    
    @pyqtSlot(np.ndarray)
    def _on_frame_ready(self, frame: np.ndarray):
        """Handle frame ready for preview (connected to engine signal)."""
        if not hasattr(self, '_frame_received_count'):
            self._frame_received_count = 0
        self._frame_received_count += 1
        
        if self._frame_received_count == 1 or self._frame_received_count % 30 == 0:
            print(f"📥 MainWindow._on_frame_ready(): Received frame #{self._frame_received_count}, "
                  f"Shape: {frame.shape if frame is not None else None}, "
                  f"Type: {type(frame)}")
        
        if self.video_widget is not None:
            print(f"🔍 MainWindow._on_frame_ready(): Updating video_widget with frame")
            self.video_widget.update_frame(frame)
            # CRITICAL: Force immediate synchronous repaint
            print(f"🔍 MainWindow._on_frame_ready(): Forcing repaint() on video_widget...")
            self.video_widget.repaint()
            print(f"✅ MainWindow._on_frame_ready(): repaint() completed")
            # Also call update() for async repaint
            self.video_widget.update()
        else:
            print("❌ MainWindow._on_frame_ready(): video_widget is None!")
    
    @pyqtSlot(str)
    def _on_error(self, error_message: str):
        """Handle error from engine (connected to engine signal)."""
        self.statusBar().showMessage(f"Error: {error_message}")
    
    def _on_sidebar_main_clicked(self):
        """Handle sidebar Main button click."""
        self.sidebar.set_active_button("main")
        self.main_content.show()
        self.analytics_widget.hide()
    
    def _on_sidebar_analytics_clicked(self):
        """Handle sidebar Analytics button click."""
        self.sidebar.set_active_button("analytics")
        self.main_content.hide()
        self.analytics_widget.show()
    
    def _send_test_frame_to_widget(self):
        """Send test frame to VideoWidget to verify rendering pipeline."""
        print("🔍 MainWindow._send_test_frame_to_widget() called")
        print(f"🔍 Called from event loop, window visible: {self.isVisible()}")
        
        # CRITICAL: Verify main_content still exists first
        if not hasattr(self, 'main_content'):
            print("❌ CRITICAL: main_content attribute missing!")
            return
        
        try:
            main_content_id = id(self.main_content)
            main_content_parent = self.main_content.parent()
            print(f"🔍 main_content verification: id={main_content_id}, parent={main_content_parent}")
        except RuntimeError as e:
            print(f"❌ CRITICAL: main_content C++ object deleted! Error: {e}")
            print("   This explains why VideoWidget was deleted - its parent was destroyed!")
            return
        
        # CRITICAL: Check if widget still exists and is valid
        if not hasattr(self, 'video_widget'):
            print("❌ CRITICAL: video_widget attribute missing!")
            return
        
        if self.video_widget is None:
            print("❌ CRITICAL: video_widget is None!")
            return
        
        # CRITICAL: Check if C++ object is still alive and parent chain is intact
        try:
            widget_id = id(self.video_widget)
            widget_parent = self.video_widget.parent()
            widget_parent_id = id(widget_parent) if widget_parent else None
            widget_size = self.video_widget.width(), self.video_widget.height()
            widget_visible = self.video_widget.isVisible()
            
            print(f"✅ VideoWidget is alive: id={widget_id}, parent={widget_parent}, parent_id={widget_parent_id}")
            print(f"   size={widget_size}, visible={widget_visible}")
            
            # CRITICAL: Verify parent is still main_content
            if widget_parent is None:
                print("❌ CRITICAL: VideoWidget has no parent! C++ object may be orphaned.")
                return
            elif widget_parent != self.main_content:
                print(f"❌ CRITICAL: VideoWidget parent changed!")
                print(f"   Expected: main_content (id={id(self.main_content)})")
                print(f"   Actual: {widget_parent} (id={widget_parent_id})")
                print("   This indicates main_content was replaced or deleted!")
                return
            else:
                print(f"✅ VideoWidget parent is still main_content (id={id(self.main_content)})")
            
            # Verify parent chain is still intact
            current = self.video_widget
            chain = []
            depth = 0
            while current is not None and depth < 10:  # Prevent infinite loop
                chain.append(f"{type(current).__name__}(id={id(current)})")
                current = current.parent()
                depth += 1
            print(f"🔍 VideoWidget parent chain: {' -> '.join(chain)}")
            
        except RuntimeError as e:
            print(f"❌ CRITICAL: VideoWidget C++ object deleted! Error: {e}")
            print("   This means the widget was garbage collected or its parent was deleted.")
            print(f"   main_content status: id={id(self.main_content) if hasattr(self, 'main_content') else 'MISSING'}")
            if hasattr(self, 'main_content'):
                try:
                    main_content_alive = self.main_content.parent() is not None
                    print(f"   main_content alive: {main_content_alive}")
                except RuntimeError:
                    print("   main_content C++ object also deleted!")
            return
        
        import numpy as np
        import cv2
        
        # Create bright test frame
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_frame[:, :] = [0, 255, 0]  # Bright green (BGR)
        
        # Add diagnostic text
        cv2.putText(test_frame, "TEST FRAME", (180, 220), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
        cv2.putText(test_frame, "Widget rendering test", (150, 260),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(test_frame, f"Size: {widget_size[0]}x{widget_size[1]}", 
                   (150, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Send to widget with error handling
        try:
            self.video_widget.update_frame(test_frame)
            self.video_widget.update()  # Force repaint
            print(f"✅ MainWindow: Test frame sent successfully, widget size: {widget_size}")
        except RuntimeError as e:
            print(f"❌ CRITICAL: Failed to update VideoWidget! Error: {e}")
            print("   Widget was deleted between check and update.")
    
    def _update_memory_status(self):
        """Update status bar with memory information."""
        from utils.pyqt_memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
        stats = memory_manager.get_memory_stats()
        
        if stats["current_mb"] > 0:
            leak_indicator = " ⚠️" if stats["leak_detected"] else ""
            self.statusBar().showMessage(
                f"Memory: {stats['current_mb']:.1f}MB (avg: {stats['avg_mb']:.1f}MB){leak_indicator}",
                5000  # Show for 5 seconds
            )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop StudySensei engine
        if self.engine.is_running():
            self.engine.stop()
        
        # Clear video widget
        self.video_widget.clear()
        
        # Cleanup memory
        from utils.pyqt_memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
        memory_manager.cleanup()
        
        # Get final memory stats
        stats = memory_manager.get_memory_stats()
        print(f"📊 Final memory: {stats['current_mb']:.1f}MB "
              f"(avg: {stats['avg_mb']:.1f}MB, "
              f"min: {stats['min_mb']:.1f}MB, "
              f"max: {stats['max_mb']:.1f}MB)")
        
        # TODO: Save session data
        event.accept()
    
    def _load_stylesheet(self) -> None:
        """Load Apple Dark QSS stylesheet from file."""
        try:
            import os
            stylesheet_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "styles",
                "apple_dark.qss"
            )
            if os.path.exists(stylesheet_path):
                with open(stylesheet_path, 'r', encoding='utf-8') as f:
                    self.setStyleSheet(f.read())
            else:
                # Fallback to original stylesheet
                fallback_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "styles",
                    "app_styles.qss"
                )
                if os.path.exists(fallback_path):
                    with open(fallback_path, 'r', encoding='utf-8') as f:
                        self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Could not load stylesheet: {e}")
