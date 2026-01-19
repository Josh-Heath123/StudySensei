# StudySensei

## Project description
StudySensei is a lightweight **focus-tracking prototype** that estimates whether you’re looking at the screen using **MediaPipe FaceMesh** landmarks. It computes a **real-time focus percentage** over a **sliding 60-second window** and presents it in a clean, minimalist Streamlit UI.

## Week 1 accomplishments
- **Webcam + FaceMesh integration**: MediaPipe FaceMesh runs on webcam frames and extracts face landmarks.
- **Focus heuristic**: Simple “focused vs distracted” decision from eye-related landmarks.
- **Real-time tracking**: Sliding window focus percentage over the **last 60 seconds**.
- **Minimalist UI**: Monochrome dashboard with a circular focus ring, status text, session timer, and optional preview.
- **Stability improvements**: Avoids complex Streamlit webcam components that can cause React/ScriptRunContext errors.

## Installation
### Prerequisites
- **Python 3.10+** recommended
- A webcam

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

3. Install dependencies:

```bash
pip install -r requirements.txt
```

> Note: `requirements.txt` currently includes some legacy dependencies (`streamlit-webrtc`, `av`) from earlier iterations. The current app uses Streamlit’s built-in camera capture and may not require them, but they are safe to leave installed.

## Usage
Start the app:

```bash
streamlit run app.py
```

In the app:
- Click **Start** to begin the session and enable webcam processing.
- The **focus %** represents the fraction of “focused” samples in the **last 60 seconds**.
- Click **Stop** to end/reset the session.
- Toggle **Show Preview** to show/hide the webcam preview.
- Toggle **Mesh** to enable/disable FaceMesh landmark drawing in the preview.