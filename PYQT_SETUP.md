# PyQt5 StudySensei Conversion Setup

## Installation

### Step 1: Install Dependencies

```bash
pip install -r requirements_pyqt.txt
```

Or install individually:
```bash
pip install PyQt5 opencv-python mediapipe numpy scikit-learn joblib fer pandas
```

### Step 2: Project Structure

```
StudySensei/
├── main.py                 # PyQt5 application entry point
├── ui/
│   ├── __init__.py
│   ├── main_window.py      # QMainWindow skeleton
│   └── components.py        # Streamlit components (legacy)
├── core/                    # Business logic (unchanged)
│   └── focus_history.py
├── vision/                  # Computer vision (unchanged)
│   ├── gaze.py
│   ├── posture.py
│   ├── emotion.py
│   └── frame_processor.py
├── services/                # Services (unchanged)
│   ├── video_processor.py
│   └── state_manager.py
├── analytics/               # Analytics (unchanged)
│   └── ...
└── utils/                   # Utilities (unchanged)
    └── ...
```

## Running the Application

### PyQt5 Version
```bash
python main.py
```

### Streamlit Version (Legacy)
```bash
streamlit run app.py
```

## Implementation Status

### ✅ Completed
- [x] Project structure setup
- [x] main.py entry point
- [x] ui/main_window.py skeleton
- [x] Basic UI layout (header, controls, metrics placeholders)

### 🚧 To Be Implemented
- [ ] Video capture integration
- [ ] Focus metrics display
- [ ] Posture metrics display
- [ ] Camera preview widget
- [ ] Analytics dashboard
- [ ] Session management
- [ ] Data persistence

## Architecture Notes

- **Core logic unchanged**: All business logic in `core/`, `vision/`, `services/`, `analytics/` remains the same
- **UI layer only**: Only the UI layer is being converted from Streamlit to PyQt5
- **Separation of concerns**: UI components are separate from business logic

## Next Steps

1. Integrate `services/video_processor.py` with QMainWindow
2. Create custom QWidget for camera preview
3. Create custom QWidget for metrics display
4. Integrate analytics dashboard
5. Add session management UI
