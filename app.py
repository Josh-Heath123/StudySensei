import cv2
import time
from typing import Optional

import mediapipe as mp

# Prefer the canonical API: mediapipe as mp; mp.solutions.<...>
# Some environments expose solutions under mediapipe.python.solutions; we fall back to that.
if not hasattr(mp, "solutions"):
    try:
        import mediapipe.python.solutions as _solutions  # type: ignore
    except Exception as exc:
        raise ImportError(
            "MediaPipe 'solutions' module was not found. "
            "Your 'mediapipe' install may be broken or shadowed by another package.\n"
            "Try: pip uninstall -y mediapipe && pip install mediapipe"
        ) from exc
    mp.solutions = _solutions  # type: ignore[attr-defined]

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_face_mesh = mp.solutions.face_mesh

LEFT_EYE_LANDMARKS = (33, 133)   # outer, inner corner (MediaPipe FaceMesh)
RIGHT_EYE_LANDMARKS = (362, 263) # outer, inner corner (MediaPipe FaceMesh)


def _lm_to_px(landmarks, idx: int, width: int, height: int) -> tuple[int, int]:
    lm = landmarks.landmark[idx]
    return int(lm.x * width), int(lm.y * height)


def is_user_focused(face_landmarks, frame_width: int, frame_height: int) -> bool:
    """
    Heuristic 'gaze' / attention estimate using only eye-corner landmarks.

    With only two points per eye, we can't truly estimate gaze direction; instead we
    approximate "looking at screen" as "face is mostly frontal":
    - left/right eye widths are similar (low yaw)
    - the eye midpoints are roughly level (low roll)
    """
    l0 = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[0], frame_width, frame_height)
    l1 = _lm_to_px(face_landmarks, LEFT_EYE_LANDMARKS[1], frame_width, frame_height)
    r0 = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[0], frame_width, frame_height)
    r1 = _lm_to_px(face_landmarks, RIGHT_EYE_LANDMARKS[1], frame_width, frame_height)

    left_w = ((l0[0] - l1[0]) ** 2 + (l0[1] - l1[1]) ** 2) ** 0.5
    right_w = ((r0[0] - r1[0]) ** 2 + (r0[1] - r1[1]) ** 2) ** 0.5

    # If the face is too small / detection unstable, avoid declaring focused.
    if left_w < 8 or right_w < 8:
        return False

    width_ratio = left_w / right_w if right_w > 0 else 0.0

    left_mid_y = (l0[1] + l1[1]) / 2.0
    right_mid_y = (r0[1] + r1[1]) / 2.0
    eye_line_delta = abs(left_mid_y - right_mid_y)

    # Tuned to be simple + fast; adjust if needed for your webcam angle.
    yaw_ok = 0.75 <= width_ratio <= 1.33
    roll_ok = eye_line_delta <= 12
    return yaw_ok and roll_ok


def open_camera(device_index: int = 0) -> Optional[cv2.VideoCapture]:
    """
    Try to open a webcam device.

    :param device_index: Index of the webcam (0 is usually the default camera).
    :return: An opened cv2.VideoCapture instance, or None if it cannot be opened.
    """
    cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)

    # Lower resolution to help ensure 15+ FPS on typical hardware.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)

    if not cap.isOpened():
        cap.release()
        return None

    return cap


def run_webcam_face_mesh_viewer(
    device_index: int = 0,
    window_title: str = "FaceMesh - Press Q to quit",
) -> None:
    """
    Open the webcam, display the live feed with MediaPipe FaceMesh, and overlay FPS.

    Press 'q' to exit the viewer.
    """
    cap = open_camera(device_index)

    if cap is None:
        print(
            f"[ERROR] Could not open webcam with index {device_index}. "
            f"Please check that a camera is connected and not used by another application."
        )
        return

    prev_time = time.time()
    fps = 0.0

    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    # FaceMesh configuration tuned for real-time performance.
    with mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,  # turning this on looks nicer but is heavier
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as face_mesh:
        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    print("[ERROR] Failed to read frame from webcam. Stopping.")
                    break

                # Convert the BGR frame from OpenCV to RGB for MediaPipe.
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_frame.flags.writeable = False
                results = face_mesh.process(rgb_frame)
                rgb_frame.flags.writeable = True

                # Draw face mesh landmarks if detected.
                focused = False
                if results.multi_face_landmarks:
                    for face_landmarks in results.multi_face_landmarks:
                        focused = is_user_focused(face_landmarks, frame.shape[1], frame.shape[0])
                        mp_drawing.draw_landmarks(
                            image=frame,
                            landmark_list=face_landmarks,
                            connections=mp_face_mesh.FACEMESH_TESSELATION,
                            landmark_drawing_spec=None,
                            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style(),
                        )
                        mp_drawing.draw_landmarks(
                            image=frame,
                            landmark_list=face_landmarks,
                            connections=mp_face_mesh.FACEMESH_CONTOURS,
                            landmark_drawing_spec=None,
                            connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_contours_style(),
                        )

                # FPS computation (smoothed).
                current_time = time.time()
                elapsed = current_time - prev_time
                prev_time = current_time

                if elapsed > 0:
                    instant_fps = 1.0 / elapsed
                    fps = 0.9 * fps + 0.1 * instant_fps if fps > 0 else instant_fps

                fps_text = f"FPS: {fps:.1f}"
                cv2.putText(
                    frame,
                    fps_text,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

                status_text = "FOCUSED" if focused else "NOT FOCUSED"
                status_color = (0, 200, 0) if focused else (0, 0, 255)
                cv2.putText(
                    frame,
                    status_text,
                    (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    status_color,
                    2,
                    cv2.LINE_AA,
                )

                cv2.imshow(window_title, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q") or key == ord("Q"):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()


def main() -> None:
    """Entry point for running the webcam + MediaPipe FaceMesh viewer."""
    run_webcam_face_mesh_viewer(device_index=0)


if __name__ == "__main__":
    main()
