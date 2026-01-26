"""
StudySensei - PyQt5 Application Entry Point
Converts Streamlit app to native desktop application.
"""

import sys
import warnings
import logging
import os

# Suppress Streamlit warnings when running in PyQt mode
# These warnings occur because Streamlit modules are imported but Streamlit isn't running
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
warnings.filterwarnings("ignore", message=".*ScriptRunContext.*")
warnings.filterwarnings("ignore", message=".*Session state.*")

# Suppress Streamlit logging completely
logging.getLogger("streamlit").setLevel(logging.CRITICAL)
logging.getLogger("streamlit.runtime").setLevel(logging.CRITICAL)
logging.getLogger("streamlit.runtime.scriptrunner_utils").setLevel(logging.CRITICAL)
logging.getLogger("streamlit.runtime.state").setLevel(logging.CRITICAL)

# Also suppress via environment variable
os.environ["STREAMLIT_LOGGER_LEVEL"] = "error"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
import atexit

from ui.main_window import MainWindow
from utils.pyqt_memory_manager import initialize_memory_manager, shutdown_memory_manager


def apply_apple_style(app):
    """Apply Apple dark theme stylesheet to the application."""
    try:
        stylesheet_path = os.path.join(
            os.path.dirname(__file__),
            "styles",
            "apple_dark.qss"
        )
        if os.path.exists(stylesheet_path):
            with open(stylesheet_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        else:
            print(f"Warning: Stylesheet not found at {stylesheet_path}")
    except Exception as e:
        print(f"Error loading stylesheet: {e}")


def main():
    """Main application entry point."""
    # Enable high DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Initialize memory manager
    memory_manager = initialize_memory_manager(check_interval=30)
    
    # Register cleanup on exit
    atexit.register(shutdown_memory_manager)
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("StudySensei")
    app.setOrganizationName("StudySensei")
    
    # Apply Apple dark theme
    apply_apple_style(app)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    exit_code = app.exec_()
    
    # Cleanup before exit
    shutdown_memory_manager()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
