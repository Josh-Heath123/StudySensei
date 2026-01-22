# StudySensei

## Project Description
StudySensei is a real-time focus and posture tracking application that uses computer vision to monitor study sessions. It combines MediaPipe FaceMesh for focus detection and MediaPipe Pose for posture analysis, providing comprehensive analytics and behavior modeling.

## Features

### Core Functionality
- **Real-time Focus Tracking**: Iris-based gaze confidence and blink-rate fatigue detection
- **Posture Detection**: Forward head ratio and shoulder-ear alignment monitoring
- **Session Analytics**: Time-series analysis with sliding windows (1min, 5min, 10min)
- **Behavior Modeling**: Pattern detection, session phase identification, and break recommendations
- **Machine Learning**: Optional focus drop prediction using Random Forest
- **SQLite Persistence**: Local, privacy-first data storage

### Advanced Features
- **Posture Calibration**: Set your baseline posture for personalized detection
- **Interactive Analytics Dashboard**: Real-time charts with throttled updates (5-second intervals)
- **Emotion Detection** (Experimental): Optional FER-based emotion recognition
- **Performance Optimized**: Frame skipping, lightweight charts, auto-disable for low FPS

### UI Design
- **Apple-style Minimalist**: Clean, calm interface with neutral colors
- **Real-time Metrics**: Live focus percentage, posture score, session duration
- **Responsive**: Optimized for standard laptops (target: >15 FPS)

## Installation

### Prerequisites
- **Python 3.10+** recommended
- A webcam
- Windows, macOS, or Linux

### Setup
1. Clone/download this repository.

2. Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows (PowerShell):
```bash
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Start the app:
```bash
streamlit run app.py
```

### Basic Workflow
1. Click **Start** to begin a session and enable webcam processing
2. The **focus %** shows the fraction of "focused" samples in the last 60 seconds
3. **Posture score** displays real-time posture quality (0-100%)
4. Click **Calibrate Posture** to set your baseline (recommended on first use)
5. Click **Stop** to end/reset the session

### Controls
- **Show Preview**: Toggle webcam feed display
- **Posture Detection**: Enable/disable posture monitoring
- **Draw Pose**: Visualize pose landmarks on preview
- **Emotion Detection** (Experimental): Optional emotion recognition
- **Toggle Mesh**: Show/hide FaceMesh landmarks

### Analytics
- **Focus Trend**: Line chart showing focus over time (updates every 5 seconds)
- **Posture Trend**: Posture score visualization
- **Session Phase**: Automatic detection (warm-up, peak, fatigue, recovery)
- **Break Suggestions**: Intelligent recommendations based on focus decay

## Architecture

### Modules
- `app.py`: Main Streamlit application and UI
- `posture.py`: Posture detection with calibration support
- `emotion_detection.py`: Experimental emotion recognition (optional)
- `analytics/`: Advanced analytics engine
  - `time_series.py`: Sliding window analysis
  - `behavior_model.py`: Pattern detection and phase identification
  - `session_store.py`: SQLite persistence
  - `break_logic.py`: Break recommendations
  - `ml_predictor.py`: Focus drop prediction

### Performance
- **Frame Processing**: Every 3rd frame (FRAME_SKIP_N=3)
- **Chart Updates**: Throttled to 5-second intervals
- **Data Storage**: Last 100 data points for charts
- **Auto-optimization**: Charts disabled if FPS < 15

## Data Storage

- **SQLite Database**: `studysensei.db` (local, privacy-first)
- **Calibration**: `posture_calibration.json` (user baseline)
- **ML Models**: `focus_predictor_model.joblib` (optional)

## Requirements

See `requirements.txt` for complete list. Key dependencies:
- `opencv-python>=4.9.0.0`
- `mediapipe>=0.10.0`
- `streamlit>=1.32.0`
- `numpy>=1.24.0,<2.0.0`
- `scikit-learn>=1.3.0`
- `pandas>=2.0.0`
- `plotly>=5.18.0` (optional, for advanced charts)

## Notes

- **Emotion Detection**: Experimental feature, accuracy varies by lighting
- **Performance**: Optimized for laptops; may need adjustment for lower-end devices
- **Privacy**: All data stored locally, no cloud services

## License

[Add your license here]
