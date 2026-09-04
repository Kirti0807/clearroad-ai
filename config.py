"""
Central configuration for ClearRoad AI.
Keep tunable values here so you're not hunting through the codebase
when calibrating CLAHE strength, detection thresholds, etc.
"""

import os

# --- Video source ---
# 0 = default webcam (this is the default for native/VS Code runs).
# Can also be a file path ("foggy_test.mp4") or a network stream URL
# (e.g. "http://host.docker.internal:5000/video_feed" for a live feed
# bridged into the Docker container -- see host_camera_server.py and the
# README's Docker Compose section).
# CLEARROAD_VIDEO_SOURCE env var overrides this if set -- docker-compose.yml
# sets it to the camera stream URL, so the container uses that instead of
# trying (and failing) to open a local webcam device.
_env_video_source = os.environ.get("CLEARROAD_VIDEO_SOURCE")
VIDEO_SOURCE = _env_video_source if _env_video_source else 0

# --- CLAHE (fog / haze enhancement) ---
CLAHE_CLIP_LIMIT = 2.5      # Higher = stronger local contrast boost, but more noise/artifacts.
CLAHE_TILE_GRID_SIZE = (8, 8)  # Smaller tiles = more local adaptation, can look patchy if too small.

# --- YOLOv8 detection ---
YOLO_MODEL_PATH = "yolov8n.pt"   # Auto-downloads on first run if not present locally.
YOLO_CONFIDENCE_THRESHOLD = 0.35  # Lower = more detections (more false positives too).
YOLO_TARGET_CLASSES = {
    "person": "pedestrian",
    "car": "car",
    "truck": "truck",
    "bus": "bus",
    "motorcycle": "motorcycle",
    "bicycle": "cyclist",
}

# --- Hazard alert logic ---
# A detection is treated as "close" (alert-worthy) if its bounding box
# height exceeds this fraction of the frame height. Bigger box = closer object.
HAZARD_PROXIMITY_HEIGHT_RATIO = 0.25
ALERT_COOLDOWN_SECONDS = 4  # Minimum gap between repeated voice alerts for the same class.

# --- GUI ---
WINDOW_TITLE = "ClearRoad AI"
WINDOW_SIZE = "1000x700"
VIDEO_DISPLAY_SIZE = (800, 450)  # Resize frames to this before showing in the GUI.

# --- Frame processing ---
TARGET_FPS = 15  # Cap processing rate; real-time doesn't need every raw camera frame.