# StudySensei Refactoring Summary

## New Directory Structure

The project has been refactored to enforce clear separation of concerns:

```
StudySensei/
├── core/              # Business logic and computations
│   ├── __init__.py
│   └── focus_history.py    # Focus history management
│
├── vision/            # All computer vision code
│   ├── __init__.py
│   ├── gaze.py              # Gaze detection and focus computation
│   ├── frame_processor.py   # Frame processing pipeline
│   ├── mediapipe_setup.py   # MediaPipe initialization
│   ├── posture.py           # Posture detection (moved from root)
│   └── emotion.py           # Emotion detection (moved from root)
│
├── ui/               # Streamlit UI components
│   ├── __init__.py
│   └── components.py        # All render functions
│
├── styles/           # UI styling
│   ├── __init__.py
│   └── theme.py              # Apple-style CSS theme
│
├── services/         # Orchestration and state management
│   ├── __init__.py
│   ├── video_processor.py    # Video processing service
│   └── state_manager.py      # Session state initialization
│
├── utils/            # Shared helpers and constants
│   ├── __init__.py
│   ├── constants.py          # Configuration constants
│   └── helpers.py            # Utility functions
│
├── analytics/        # Analytics modules (existing)
│   └── ...
│
└── app.py            # Thin entry point (refactored)
```

## Separation of Concerns

### Core (`core/`)
- **Business logic only**: Focus scoring rules, history management
- **No UI code**: Pure computation functions
- **No CV logic**: No MediaPipe or image processing

### Vision (`vision/`)
- **Computer vision only**: MediaPipe, gaze detection, posture, emotion
- **No UI code**: Pure CV processing functions
- **No business logic**: No focus scoring rules or analytics

### UI (`ui/`)
- **Streamlit components only**: All render functions, layout
- **No CV logic**: No MediaPipe or image processing
- **No business logic**: No focus scoring or analytics computation

### Styles (`styles/`)
- **CSS/theme only**: All styling code
- **No logic**: Pure presentation

### Services (`services/`)
- **Orchestration**: VideoProcessor, state management
- **Pipelines**: Coordinates between vision, core, and UI
- **No direct UI rendering**: Uses UI components

### Utils (`utils/`)
- **Shared constants**: Configuration values
- **Helper functions**: Formatting, utilities
- **No dependencies**: Minimal imports

### App (`app.py`)
- **Thin entry point**: Only wires components together
- **No business logic**: Delegates to services
- **No UI code**: Uses UI components
- **No CV code**: Uses vision modules

## Import Rules

1. **No circular dependencies**: Each module has clear dependencies
2. **Explicit imports**: No wildcard imports
3. **Layer hierarchy**: 
   - `app.py` → `services/`, `ui/`, `styles/`
   - `services/` → `vision/`, `core/`, `utils/`
   - `ui/` → `utils/` (for helpers)
   - `vision/` → `utils/` (for constants)
   - `core/` → `utils/` (for constants)

## Migration Notes

- Original `app.py` backed up as `app_old.py`
- `posture.py` moved to `vision/posture.py`
- `emotion_detection.py` moved to `vision/emotion.py`
- All render functions moved to `ui/components.py`
- CSS styles moved to `styles/theme.py`
- VideoProcessor moved to `services/video_processor.py`
- Constants moved to `utils/constants.py`
- Helper functions moved to `utils/helpers.py`

## Testing

After refactoring, verify:
1. All imports resolve correctly
2. Application runs without errors
3. All features work as before
4. No functionality lost

## Next Steps

1. Test the refactored application
2. Fix any import errors
3. Update documentation if needed
4. Remove `app_old.py` after verification
